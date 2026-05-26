package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

// JSON request log record written once per completed request when --requests-jsonl is set.
type requestLogRow struct {
	Time              time.Time `json:"time"`
	Path              string    `json:"path"`
	AssignedDelayMS   float64   `json:"assigned_delay_ms"`
	QueueWaitMS       float64   `json:"queue_wait_ms"`
	ServerLatencyMS   float64   `json:"server_latency_ms"`
	InFlightAtService int64     `json:"in_flight_at_service"`
	QueueDepthArrival int64     `json:"queue_depth_arrival"`
}

type requestLogger struct {
	mu     sync.Mutex
	file   *os.File
	writer *bufio.Writer
	enc    *json.Encoder
}

func newRequestLogger(path string) *requestLogger {
	if path == "" {
		return nil
	}

	file, err := os.Create(path)
	if err != nil {
		log.Fatalf("create requests jsonl: %v", err)
	}

	writer := bufio.NewWriter(file)
	return &requestLogger{
		file:   file,
		writer: writer,
		enc:    json.NewEncoder(writer),
	}
}

func (l *requestLogger) Close() {
	if l == nil {
		return
	}
	if err := l.writer.Flush(); err != nil {
		log.Printf("flush requests jsonl: %v", err)
	}
	if err := l.file.Close(); err != nil {
		log.Printf("close requests jsonl: %v", err)
	}
}

func (l *requestLogger) Write(row requestLogRow) {
	if l == nil {
		return
	}

	l.mu.Lock()
	defer l.mu.Unlock()

	if err := l.enc.Encode(row); err != nil {
		log.Printf("write requests jsonl: %v", err)
		return
	}
	if err := l.writer.Flush(); err != nil {
		log.Printf("flush requests jsonl: %v", err)
	}
}

// JSON response returned to each caller.
type response struct {
	Path              string        `json:"path"`
	Delay             time.Duration `json:"delay"`
	QueueWait         time.Duration `json:"queue_wait"`
	ArrivedAt         time.Time     `json:"arrived_at"`
	CompletedAt       time.Time     `json:"completed_at"`
	InFlightAtService int64         `json:"in_flight_at_service"`
	QueueDepthArrival int64         `json:"queue_depth_arrival"`
}

func main() {
	addr      := flag.String("addr", "127.0.0.1:8080", "listen address")
	connLimit := flag.Int("conn-limit", 50, "max concurrent requests being served (0 = unlimited)")

	// The four delay tiers the TA describes
	d1 := flag.Duration("delay-1", 10*time.Millisecond,   "tier-1 delay (fast)")
	d2 := flag.Duration("delay-2", 50*time.Millisecond,   "tier-2 delay")
	d3 := flag.Duration("delay-3", 100*time.Millisecond,  "tier-3 delay")
	d4 := flag.Duration("delay-4", 4000*time.Millisecond, "tier-4 delay (tail)")

	// Relative weights — defaults give equal probability to each tier.
	// Lower w4 (e.g. 0.05) produces a gentler tail; higher w4 saturates faster.
	w1 := flag.Float64("weight-1", 1.0, "relative weight for tier-1")
	w2 := flag.Float64("weight-2", 1.0, "relative weight for tier-2")
	w3 := flag.Float64("weight-3", 1.0, "relative weight for tier-3")
	w4 := flag.Float64("weight-4", 1.0, "relative weight for tier-4 (tail)")

	seed         := flag.Int64("seed", 1, "random seed")
	requestsPath := flag.String("requests-jsonl", "", "per-request server latency JSONL path")
	flag.Parse()

	// Build cumulative CDF thresholds from the four weights.
	total := *w1 + *w2 + *w3 + *w4
	thresholds := [4]float64{
		*w1 / total,
		(*w1 + *w2) / total,
		(*w1 + *w2 + *w3) / total,
		1.0,
	}
	delays := [4]time.Duration{*d1, *d2, *d3, *d4}
	names  := [4]string{"10ms", "50ms", "100ms", "4000ms"}

	requestLog := newRequestLogger(*requestsPath)
	defer requestLog.Close()

	rng := rand.New(rand.NewSource(*seed))
	var rngMu sync.Mutex

	// A buffered channel acts as a counting semaphore: acquiring a slot means
	// sending into the channel (blocks when full), releasing means receiving.
	// When the channel is full, arriving goroutines queue here — this is the
	// mechanism that turns unlucky clusters of 4 s requests into visible
	// head-of-line blocking and breaks Vegeta's open-loop assumption.
	var sem chan struct{}
	if *connLimit > 0 {
		sem = make(chan struct{}, *connLimit)
	}

	var inFlight int64 // requests currently holding a semaphore slot
	var waiting int64  // requests queued for a slot

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		arrivedAt := time.Now()

		// Sample the delay tier before queuing; the assignment is independent of
		// queue state, matching realistic server behavior.
		rngMu.Lock()
		u := rng.Float64()
		rngMu.Unlock()

		var delay time.Duration
		var path string
		for i, thresh := range thresholds {
			if u < thresh {
				delay = delays[i]
				path = names[i]
				break
			}
		}

		// Record how many peers are already queued when this request arrives.
		queueDepthAtArrival := atomic.AddInt64(&waiting, 1) - 1

		// Block here until a processing slot opens up.
		queueStart := time.Now()
		if sem != nil {
			select {
			case sem <- struct{}{}:
			case <-r.Context().Done():
				atomic.AddInt64(&waiting, -1)
				return
			}
		}
		queueWait := time.Since(queueStart)
		atomic.AddInt64(&waiting, -1)

		inFlightAtService := atomic.AddInt64(&inFlight, 1)
		defer func() {
			atomic.AddInt64(&inFlight, -1)
			if sem != nil {
				<-sem
			}
		}()

		// Serve the request — this is the "real" work the server performs.
		select {
		case <-time.After(delay):
		case <-r.Context().Done():
			return
		}

		completedAt := time.Now()
		serverLatencyMS := float64(completedAt.Sub(arrivedAt)) / float64(time.Millisecond)

		requestLog.Write(requestLogRow{
			Time:              completedAt.UTC(),
			Path:              path,
			AssignedDelayMS:   float64(delay) / float64(time.Millisecond),
			QueueWaitMS:       float64(queueWait) / float64(time.Millisecond),
			ServerLatencyMS:   serverLatencyMS,
			InFlightAtService: inFlightAtService,
			QueueDepthArrival: queueDepthAtArrival,
		})

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response{
			Path:              path,
			Delay:             delay,
			QueueWait:         queueWait,
			ArrivedAt:         arrivedAt,
			CompletedAt:       completedAt,
			InFlightAtService: inFlightAtService,
			QueueDepthArrival: queueDepthAtArrival,
		})
	})

	log.Printf("Server listening on %s | conn-limit=%d delays=[%s,%s,%s,%s] weights=[%.2f,%.2f,%.2f,%.2f]",
		*addr, *connLimit, *d1, *d2, *d3, *d4, *w1, *w2, *w3, *w4)
	log.Fatal(http.ListenAndServe(*addr, mux))
}
