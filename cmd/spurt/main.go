package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"flag"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

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

type response struct {
	Now          time.Time     `json:"now"`           // when the request was received
	Phase        string        `json:"phase"`         // current phase of the server (fast or slow)
	AppliedDelay time.Duration `json:"applied_delay"` // delay applied to the request
	TotalCount   uint64        `json:"total_count"`   // total number of requests served
}

// csvRecord holds the data we want to write to the CSV file (one row)
type csvRecord struct {
	ID             uint64
	ArrivalUnixMs  int64
	ProcessingMs   int64
	Phase          string
}

func main() {
	// command-line flags to configure the server behavior
	addr := flag.String("addr", ":8080", "listen address")
	fastDelay := flag.Duration("fast-delay", 10*time.Millisecond, "delay outside the spike window")
	slowDelay := flag.Duration("slow-delay", 400*time.Millisecond, "delay inside the spike window")
	cycle := flag.Duration("cycle", 4*time.Second, "full duration of the repeating latency pattern")
	spike := flag.Duration("spike", 1500*time.Millisecond, "time spent in the slow phase within each cycle")
	csvPath := flag.String("csv", "spurt_data.csv", "path to save the request data CSV")
	requestsPath := flag.String("requests-jsonl", "", "per-request server latency JSONL path")
	phasePath := flag.String("phase-csv", "phase_log.csv", "path to save the independent phase telemetry")
	flag.Parse()

	if *cycle <= 0 {
		log.Fatal("cycle must be > 0")
	}
	if *spike < 0 || *spike > *cycle {
		log.Fatal("spike must be between 0 and cycle")
	}

	// Set up the JSONL logger
	requestLog := newRequestLogger(*requestsPath)
	defer requestLog.Close()

	// Set up the CSV file and async writer
	csvFile, err := os.Create(*csvPath)
	if err != nil {
		log.Fatalf("failed to create csv file: %v", err)
	}
	defer csvFile.Close()

	csvWriter := csv.NewWriter(csvFile)
	// Write the header row
	_ = csvWriter.Write([]string{"request_id", "arrival_time_unix_ms", "processing_time_ms", "phase"})
	csvWriter.Flush()

	// Channel to send records from the HTTP handlers to the background CSV writer
	recordsChan := make(chan csvRecord, 10000)

	// Background goroutine to write CSV records asynchronously
	go func() {
		flushTicker := time.NewTicker(time.Second)
		defer flushTicker.Stop()

		for {
			select {
			case r := <-recordsChan:
				_ = csvWriter.Write([]string{
					strconv.FormatUint(r.ID, 10),
					strconv.FormatInt(r.ArrivalUnixMs, 10),
					strconv.FormatInt(r.ProcessingMs, 10),
					r.Phase,
				})
			case <-flushTicker.C:
				csvWriter.Flush()
			}
		}
	}()

	// Set up the independent phase logger
	phaseFile, err := os.Create(*phasePath)
	if err != nil {
		log.Fatalf("failed to create phase log: %v", err)
	}
	defer phaseFile.Close()
	phaseWriter := csv.NewWriter(phaseFile)
	_ = phaseWriter.Write([]string{"timestamp_unix_ms", "phase"})
	phaseWriter.Flush()

	// Variables to handle lazy initialization on the first request
	var start time.Time
	var startOnce sync.Once

	// Separate counters for accurate tracking
	var totalArrivals uint64
	var totalServed uint64
	var inFlight int64

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Only executes once, precisely when the very first request arrives
		startOnce.Do(func() {
			start = time.Now()
			log.Println("First request received. Starting the latency cycle and telemetry...")

			// Background telemetry loop: records the true SUT phase every 50ms
			// This is completely immune to the HTTP listen queue overflowing
			go func() {
				ticker := time.NewTicker(50 * time.Millisecond)
				defer ticker.Stop()

				for now := range ticker.C {
					elapsed := now.Sub(start)
					offset := elapsed % *cycle

					phase := "fast"
					// Shift the slow phase to the end of the cycle
					if offset >= (*cycle - *spike) {
						phase = "slow"
					}

					_ = phaseWriter.Write([]string{
						strconv.FormatInt(now.UnixMilli(), 10),
						phase,
					})
					// Flush frequently so we don't lose the tail end of data when the test stops
					phaseWriter.Flush()
				}
			}()
		})

		arrivedAt := time.Now()
		elapsed := arrivedAt.Sub(start)

		atomic.AddInt64(&inFlight, 1)
		defer atomic.AddInt64(&inFlight, -1)

		// position within the current cycle determines the delay applied to this request
		offset := elapsed % *cycle

		// start with fast delay
		delay := *fastDelay
		phase := "fast"

		// Shift the slow phase to the end of the cycle
		if offset >= (*cycle - *spike) {
			delay = *slowDelay
			phase = "slow"
		}

		// increment the total count of arrivals immediately
		count := atomic.AddUint64(&totalArrivals, 1)

		// Send data to the CSV writer channel
		select {
		case recordsChan <- csvRecord{
			ID:            count,
			ArrivalUnixMs: arrivedAt.UnixMilli(),
			ProcessingMs:  delay.Milliseconds(),
			Phase:         phase,
		}:
		default:
			// If the channel buffer fills up, we drop the record rather than blocking the server
			log.Println("warning: csv record buffer full, dropping data point")
		}

		time.Sleep(delay)

		// increment the served count after the delay is finished
		atomic.AddUint64(&totalServed, 1)

		// Record the completion time and latencies for JSONL
		completedAt := time.Now()
		totalInFlight := atomic.LoadInt64(&inFlight)
		serverLatencyMS := float64(completedAt.Sub(arrivedAt)) / float64(time.Millisecond)

		requestLog.Write(requestLogRow{
			Time:            completedAt.UTC(),
			Path:            phase, // Maps to the phase in spurt context
			AssignedDelayMS: float64(delay) / float64(time.Millisecond),
			ServerLatencyMS: serverLatencyMS,
			TotalInFlight:   totalInFlight,
		})

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response{
			Now:          arrivedAt,
			Phase:        phase,
			AppliedDelay: delay,
			TotalCount:   count, // returning the arrival number to maintain previous behavior
		})
	})

	log.Printf("listening on %s fast=%s slow=%s cycle=%s spike=%s csv=%s jsonl=%s\n",
		*addr, *fastDelay, *slowDelay, *cycle, *spike, *csvPath, *requestsPath)
	log.Fatal(http.ListenAndServe(*addr, mux))
}