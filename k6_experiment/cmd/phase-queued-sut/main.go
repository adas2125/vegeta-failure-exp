package main

import (
	"crypto/tls"
	"encoding/csv"
	"flag"
	"fmt"
	"log"
	mrand "math/rand"
	"net/http"
	"os"
	"path/filepath" // Added for path joining
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const defaultPhaseSchedule = "0:70,20,8,2;5:64,23,10,3;8:20,20,20,30;9:64,23,10,3;14:70,20,8,2"

type phase struct {
	Start      time.Duration
	Weights    [4]float64
	Thresholds [4]float64
}

type phaseSchedule struct {
	phases []phase
}

type serviceChooser struct {
	delays   [4]time.Duration
	schedule phaseSchedule
}

func (c serviceChooser) serviceTime(phaseElapsed time.Duration) time.Duration {
	active := c.schedule.phaseAt(phaseElapsed)
	unit := mrand.Float64()

	for i, thresh := range active.Thresholds {
		if unit < thresh {
			return c.delays[i]
		}
	}
	return c.delays[3]
}

func (s phaseSchedule) phaseAt(elapsed time.Duration) phase {
	active := s.phases[0]
	for _, candidate := range s.phases[1:] {
		if elapsed < candidate.Start {
			break
		}
		active = candidate
	}
	return active
}

func parsePhaseSchedule(value string) (phaseSchedule, error) {
	parts := strings.Split(value, ";")
	phases := make([]phase, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		pieces := strings.SplitN(part, ":", 2)
		if len(pieces) != 2 {
			return phaseSchedule{}, fmt.Errorf("invalid phase %q", part)
		}

		start, err := parsePhaseStart(strings.TrimSpace(pieces[0]))
		if err != nil {
			return phaseSchedule{}, err
		}

		weights, err := parseWeights(strings.TrimSpace(pieces[1]))
		if err != nil {
			return phaseSchedule{}, err
		}
		phases = append(phases, newPhase(start, weights))
	}

	sort.Slice(phases, func(i, j int) bool { return phases[i].Start < phases[j].Start })
	return phaseSchedule{phases: phases}, nil
}

func parsePhaseStart(value string) (time.Duration, error) {
	if strings.ContainsAny(value, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZµ") {
		return time.ParseDuration(value)
	}
	seconds, err := strconv.ParseFloat(value, 64)
	return time.Duration(seconds * float64(time.Second)), err
}

func parseWeights(value string) ([4]float64, error) {
	parts := strings.Split(value, ",")
	if len(parts) != 4 {
		return [4]float64{}, fmt.Errorf("expected four weights, got %d", len(parts))
	}

	var weights [4]float64
	for i, part := range parts {
		weight, err := strconv.ParseFloat(strings.TrimSpace(part), 64)
		if err != nil {
			return [4]float64{}, err
		}
		weights[i] = weight
	}
	return weights, nil
}

func newPhase(start time.Duration, weights [4]float64) phase {
	total := weights[0] + weights[1] + weights[2] + weights[3]
	return phase{
		Start:   start,
		Weights: weights,
		Thresholds: [4]float64{
			weights[0] / total,
			(weights[0] + weights[1]) / total,
			(weights[0] + weights[1] + weights[2]) / total,
			1,
		},
	}
}

func (s phaseSchedule) String() string {
	parts := make([]string, 0, len(s.phases))
	for _, phase := range s.phases {
		parts = append(parts, fmt.Sprintf("%g:[%.2f,%.2f,%.2f,%.2f]", float64(phase.Start)/float64(time.Second), phase.Weights[0], phase.Weights[1], phase.Weights[2], phase.Weights[3]))
	}
	return strings.Join(parts, ";")
}

type requestLogEntry struct {
	Timestamp time.Time
	DelayMS   float64
}

type closeConnectionWindow struct {
	Enabled bool
	Start   time.Duration
	End     time.Duration
}

func newCloseConnectionWindow(start, end time.Duration) (closeConnectionWindow, error) {
	if start == 0 && end == 0 {
		return closeConnectionWindow{}, nil
	}
	if end <= start {
		return closeConnectionWindow{}, fmt.Errorf("close connection window end must be greater than start")
	}
	return closeConnectionWindow{Enabled: true, Start: start, End: end}, nil
}

func (w closeConnectionWindow) contains(elapsed time.Duration) bool {
	return w.Enabled && elapsed >= w.Start && elapsed < w.End
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8080", "listen address")
	d1 := flag.Duration("delay-1", 10*time.Millisecond, "tier-1 delay")
	d2 := flag.Duration("delay-2", 50*time.Millisecond, "tier-2 delay")
	d3 := flag.Duration("delay-3", 100*time.Millisecond, "tier-3 delay")
	d4 := flag.Duration("delay-4", 4000*time.Millisecond, "tier-4 delay")
	phaseScheduleValue := flag.String("phase-schedule", defaultPhaseSchedule, "semicolon-separated phase schedule")
	closeConnectionsAfter := flag.Duration("close-connections-after", 0, "start closing response connections")
	closeConnectionsUntil := flag.Duration("close-connections-until", 0, "stop closing response connections")
	enableHTTPS := flag.Bool("https", false, "serve HTTPS instead of HTTP")
	arrivalsDir := flag.String("arrivals-dir", ".", "directory to save arrivals.csv") // Added flag
	flag.Parse()

	schedule, err := parsePhaseSchedule(*phaseScheduleValue)
	if err != nil {
		log.Fatal(err)
	}

	closeWindow, err := newCloseConnectionWindow(*closeConnectionsAfter, *closeConnectionsUntil)
	if err != nil {
		log.Fatal(err)
	}

	delays := [4]time.Duration{*d1, *d2, *d3, *d4}
	chooser := serviceChooser{delays: delays, schedule: schedule}

	logChan := make(chan requestLogEntry, 100000)

	// logs the arrival time and assigned delay
	go func() {
		// Ensure the directory exists before trying to create the file inside it
		if err := os.MkdirAll(*arrivalsDir, 0755); err != nil {
			log.Fatalf("failed to create arrivals directory: %v", err)
		}

		csvPath := filepath.Join(*arrivalsDir, "arrivals.csv") // Construct the full path
		file, err := os.Create(csvPath)
		if err != nil {
			log.Fatalf("failed to create arrivals.csv: %v", err)
		}
		defer file.Close()

		writer := csv.NewWriter(file)
		writer.Write([]string{"Timestamp", "Assigned_Delay_MS"}) // Removed Request_ID
		writer.Flush()
		file.Sync()

		ticker := time.NewTicker(1 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case entry := <-logChan:
				writer.Write([]string{
					entry.Timestamp.Format(time.RFC3339Nano),
					strconv.FormatFloat(entry.DelayMS, 'f', 2, 64),
				})
			case <-ticker.C:
				writer.Flush()
				file.Sync()
			}
		}
	}()

	var firstArrivalMu sync.Mutex
	var firstArrival time.Time

	phaseElapsedFor := func(arrivedAt time.Time) time.Duration {
		firstArrivalMu.Lock()
		defer firstArrivalMu.Unlock()
		if firstArrival.IsZero() {
			firstArrival = arrivedAt
			return 0
		}
		return arrivedAt.Sub(firstArrival)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		arrivedAt := time.Now()

		delay := chooser.serviceTime(phaseElapsedFor(arrivedAt))
		delayMS := float64(delay) / float64(time.Millisecond)

		logChan <- requestLogEntry{
			Timestamp: arrivedAt,
			DelayMS:   delayMS,
		}

		time.Sleep(delay)
		completedAt := time.Now()

		if closeWindow.contains(phaseElapsedFor(completedAt)) {
			w.Header().Set("Connection", "close")
		}

		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("OK\n"))
	})

	server := &http.Server{Addr: *addr, Handler: mux}

	log.Printf("phase queued SUT listening on %s delays=[%s,%s,%s,%s] schedule=%s close_window=[%s,%s) https=%t arrivals_dir=%s",
		*addr, delays[0], delays[1], delays[2], delays[3], schedule.String(), closeWindow.Start, closeWindow.End, *enableHTTPS, *arrivalsDir)

	if *enableHTTPS {
		// Force HTTP/1.1
		server.TLSConfig = &tls.Config{
			NextProtos: []string{"http/1.1"},
		}
		log.Fatal(server.ListenAndServeTLS("cert.pem", "key.pem"))
	}

	log.Fatal(server.ListenAndServe())
}