package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

type counters struct {
	// current total requests being handled by the server
	inFlight int64
}

// JSON request log record written once per completed request when --requests-jsonl is set.
type requestLogRow struct {
	Time            time.Time `json:"time"`
	Path            string    `json:"path"`
	AssignedDelayMS float64   `json:"assigned_delay_ms"`
	ServerLatencyMS float64   `json:"server_latency_ms"`
	TotalInFlight   int64     `json:"total_in_flight"`
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

// JSON response for each request to the server.
type response struct {
	Path          string        `json:"path"`
	Delay         time.Duration `json:"delay"`
	ArrivedAt     time.Time     `json:"arrived_at"`
	CompletedAt   time.Time     `json:"completed_at"`
	TotalInFlight int64         `json:"total_in_flight"`
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8080", "listen address")
	dist := flag.String("dist", "binary", "delay distribution: 'binary', 'uniform', or 'longtail'")
	
	// Binary distribution flags
	fastDelay := flag.Duration("fast-delay", 10*time.Millisecond, "fast path delay (binary)")
	slowDelay := flag.Duration("slow-delay", 400*time.Millisecond, "slow path delay (binary)")
	slowProb := flag.Float64("slow-prob", 0.05, "probability that a request takes the slow path (binary)")
	
	// Uniform & Long-tail distribution flags
	minDelay := flag.Duration("min-delay", 10*time.Millisecond, "minimum delay (uniform, longtail)")
	maxDelay := flag.Duration("max-delay", 400*time.Millisecond, "maximum delay (uniform, longtail)")
	tailAlpha := flag.Float64("tail-alpha", 1.5, "alpha shape parameter for longtail. Lower = heavier tail (longtail)")
	
	seed := flag.Int64("seed", 1, "random seed for path assignment")
	requestsPath := flag.String("requests-jsonl", "", "per-request server latency JSONL path")
	flag.Parse()

	var counts counters

	// create the request logger at the requested path
	requestLog := newRequestLogger(*requestsPath)
	defer requestLog.Close()

	// random number
	rng := rand.New(rand.NewSource(*seed))
	var rngMu sync.Mutex

	mux := http.NewServeMux()

	// main endpoint
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		arrivedAt := time.Now()
		atomic.AddInt64(&counts.inFlight, 1)
		defer atomic.AddInt64(&counts.inFlight, -1)

		// generate a random number in a thread-safe manner
		rngMu.Lock()
		u := rng.Float64()
		rngMu.Unlock()

		var path string
		var delay time.Duration

		switch *dist {
		case "uniform":
			path = "uniform"
			min := float64(*minDelay)
			max := float64(*maxDelay)
			// U(min, max)
			delay = time.Duration(min + u*(max-min))

		case "longtail":
			path = "longtail"
			// Prevent division by zero
			if u == 0 {
				u = math.SmallestNonzeroFloat64
			}
			min := float64(*minDelay)
			// Pareto Inverse Transform Sampling
			delay = time.Duration(min / math.Pow(u, 1.0/(*tailAlpha)))

			// cap the delay to maxDelay
            if delay > *maxDelay {
                delay = *maxDelay
            }

		default: // "binary"
			if u < *slowProb {
				path = "slow"
				delay = *slowDelay
			} else {
				path = "fast"
				delay = *fastDelay
			}
		}
		
		// wait for the assigned delay
		select {
		case <-time.After(delay):
		case <-r.Context().Done():
			return
		}

		// record the completion time
		completedAt := time.Now()
		totalInFlight := atomic.LoadInt64(&counts.inFlight)
		serverLatencyMS := float64(completedAt.Sub(arrivedAt)) / float64(time.Millisecond)
		
		// write the request log row if logging is enabled
		requestLog.Write(requestLogRow{
			Time:            completedAt.UTC(),
			Path:            path,
			AssignedDelayMS: float64(delay) / float64(time.Millisecond),
			ServerLatencyMS: serverLatencyMS,
			TotalInFlight:   totalInFlight,
		})
		
		// write the JSON response
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response{
			Path:          path,
			Delay:         delay,
			ArrivedAt:     arrivedAt,
			CompletedAt:   completedAt,
			TotalInFlight: totalInFlight,
		})
	})

	log.Printf("Server listening on %s | dist=%s", *addr, *dist)
	log.Fatal(http.ListenAndServe(*addr, mux))
}