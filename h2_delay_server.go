package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
)

// logEntry records per-request timing for ground-truth analysis
type logEntry struct {
	RequestID       uint64  `json:"request_id"`
	ArrivedAt       float64 `json:"arrived_at_s"`       // seconds since server start
	AdmittedAt      float64 `json:"admitted_at_s"`      // when it got a worker slot
	CompletedAt     float64 `json:"completed_at_s"`     // when processing finished
	QueueWaitMS     float64 `json:"queue_wait_ms"`      // time waiting for a slot
	ProcessingMS    float64 `json:"processing_ms"`      // always ~delay
	TotalLatencyMS  float64 `json:"total_latency_ms"`   // queue + processing
}

func main() {
	addr        := flag.String("addr",        "0.0.0.0:8080", "listen address")
	delay       := flag.Duration("delay",     10*time.Second, "fixed processing delay per request")
	concurrency := flag.Int("concurrency",    0,             "max concurrent requests (0 = unlimited)")
	logPath     := flag.String("log",         "server_arrivals.jsonl", "path to per-request JSONL log")
	flag.Parse()

	// open log file
	lf, err := os.Create(*logPath)
	if err != nil {
		log.Fatalf("cannot open log file: %v", err)
	}
	defer lf.Close()
	var logMu sync.Mutex
	enc := json.NewEncoder(lf)

	// worker slots — nil means unlimited concurrency
	var slots chan struct{}
	if *concurrency > 0 {
		slots = make(chan struct{}, *concurrency)
	}

	// server start time for relative timestamps
	serverStart := time.Now()

	// atomic request counter for unique IDs
	var reqCounter uint64

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		arrivedAt := time.Now()
		id := atomic.AddUint64(&reqCounter, 1)

		// acquire a worker slot if concurrency is limited
		if slots != nil {
			slots <- struct{}{}
		}
		admittedAt := time.Now()

		// fixed processing delay
		time.Sleep(*delay)
		completedAt := time.Now()

		// release slot
		if slots != nil {
			<-slots
		}

		// compute timings
		entry := logEntry{
			RequestID:      id,
			ArrivedAt:      arrivedAt.Sub(serverStart).Seconds(),
			AdmittedAt:     admittedAt.Sub(serverStart).Seconds(),
			CompletedAt:    completedAt.Sub(serverStart).Seconds(),
			QueueWaitMS:    float64(admittedAt.Sub(arrivedAt)) / float64(time.Millisecond),
			ProcessingMS:   float64(completedAt.Sub(admittedAt)) / float64(time.Millisecond),
			TotalLatencyMS: float64(completedAt.Sub(arrivedAt)) / float64(time.Millisecond),
		}

		// write log entry (thread-safe)
		logMu.Lock()
		_ = enc.Encode(entry)
		logMu.Unlock()

		// respond
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"ok":true,"request_id":%d,"total_latency_ms":%.2f}`, id, entry.TotalLatencyMS)
	})

	// wrap with h2c so h2load can connect without TLS
	h2Server  := &http2.Server{}
	h2cHandler := h2c.NewHandler(mux, h2Server)

	srv := &http.Server{
		Addr:    *addr,
		Handler: h2cHandler,
	}

	concurrencyStr := "unlimited"
	if *concurrency > 0 {
		concurrencyStr = fmt.Sprintf("%d", *concurrency)
	}
	log.Printf("h2 delay server | addr=%s delay=%s concurrency=%s log=%s",
		*addr, *delay, concurrencyStr, *logPath)
	log.Fatal(srv.ListenAndServe())
}