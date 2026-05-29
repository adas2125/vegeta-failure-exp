package main

import (
    "encoding/json"
    "flag"
    "fmt"
    "log"
    "net/http"
    "sort"
    "strconv"
    "strings"
    "sync"
    "time"
)

/*
Requests are given assigned times the moment they arrives at the SUT;
Could simulate a realistic scenario where a SUT periodically uses and assigns
requests immediately to either a slow or fast path
*/

// default phase schedule (0-5 sec. 5-8 sec. 8-11 sec. 11-14 each having 4 tiers of service with different weights)
const defaultPhaseSchedule = "0:70,20,8,2;5:64,23,10,3;8:20,20,20,30;9:64,23,10,3;14:70,20,8,2"

// simple response type for the SUT to return
type response struct {
    OK bool `json:"ok"`
}

// phase represents a single phase of SUT's service time distirbution w/ start time, weights, thresholds
type phase struct {
    Start      time.Duration
    Weights    [4]float64
    Thresholds [4]float64
}

// phaseSchedule represents a series of phases for the SUT's service time distribution
type phaseSchedule struct {
    phases []phase
}

// determines which phase is active at a given elapsed time
type serviceChooser struct {
    delays   [4]time.Duration
    schedule phaseSchedule
    seed     uint64
}

// determines service time for a request based on its ID and the elapsed time since the first request arrived
func (c serviceChooser) serviceTime(id uint64, phaseElapsed time.Duration) time.Duration {
    active := c.schedule.phaseAt(phaseElapsed)

    // determine the service time for the request based on its ID, the seed, and the active phase's thresholds
    unit := hashUnit(id, c.seed)

    // looping through the thresholds of the active phase to find the appropriate delay for the request
    for i, thresh := range active.Thresholds {
        if unit < thresh {
            return c.delays[i]
        }
    }
    return c.delays[3]
}

// returns the active phase based on the elapsed time since the first request arrived
func (s phaseSchedule) phaseAt(elapsed time.Duration) phase {
    active := s.phases[0]

    // loop through the phases to find the active phase based on the elapsed time
    for _, candidate := range s.phases[1:] {
        if elapsed < candidate.Start {
            break
        }
        active = candidate
    }
    return active
}

// parses a semicolon-separated phase schedule string into a phaseSchedule struct
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

// helper for parsePhaseSchedule
func parsePhaseStart(value string) (time.Duration, error) {
    if strings.ContainsAny(value, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZµ") {
        return time.ParseDuration(value)
    }
    seconds, err := strconv.ParseFloat(value, 64)
    return time.Duration(seconds * float64(time.Second)), err
}

// helper for parsePhaseSchedule
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

// creates a new phase with the given start time and weights, calculating thresholds based on weights
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

// for debugging
func (s phaseSchedule) String() string {
    parts := make([]string, 0, len(s.phases))
    for _, phase := range s.phases {
        parts = append(parts, fmt.Sprintf("%g:[%.2f,%.2f,%.2f,%.2f]", float64(phase.Start)/float64(time.Second), phase.Weights[0], phase.Weights[1], phase.Weights[2], phase.Weights[3]))
    }
    return strings.Join(parts, ";")
}

// hash functions, also used in python script for offline creation of the GT
func hashUnit(id, seed uint64) float64 {
    x := splitmix64(id ^ (seed + 0x9e3779b97f4a7c15))
    return float64(x>>11) / float64(uint64(1)<<53)
}

func splitmix64(x uint64) uint64 {
    x += 0x9e3779b97f4a7c15
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9
    x = (x ^ (x >> 27)) * 0x94d049bb133111eb
    return x ^ (x >> 31)
}

func main() {
    addr := flag.String("addr", "127.0.0.1:8080", "listen address")
    concurrency := flag.Int("concurrency", 50, "number of concurrent server-side workers")
    // the different processing delays for the four tiers of service, in milliseconds
    d1 := flag.Duration("delay-1", 10*time.Millisecond, "tier-1 delay")
    d2 := flag.Duration("delay-2", 50*time.Millisecond, "tier-2 delay")
    d3 := flag.Duration("delay-3", 100*time.Millisecond, "tier-3 delay")
    d4 := flag.Duration("delay-4", 4000*time.Millisecond, "tier-4 delay")
    // the phase schedule, different phases for SUT operation
    phaseScheduleValue := flag.String("phase-schedule", defaultPhaseSchedule, "semicolon-separated phase schedule, e.g. 0:70,20,8,2;5:64,23,10,3")
    seed := flag.Uint64("seed", 1, "deterministic seed for request id hashing")
    flag.Parse()

    // parses the schedule of phases for the SUT's service time distribution
    schedule, err := parsePhaseSchedule(*phaseScheduleValue)
    if err != nil {
        log.Fatal(err)
    }
    
    delays := [4]time.Duration{*d1, *d2, *d3, *d4}
    chooser := serviceChooser{delays: delays, schedule: schedule, seed: *seed}

    // creating a channel to model worker slots for the SUT, limiting concurrency
    slots := make(chan struct{}, *concurrency)
    var firstArrivalMu sync.Mutex
    var firstArrival time.Time

    phaseElapsedFor := func(arrivedAt time.Time) time.Duration {
        firstArrivalMu.Lock()
        defer firstArrivalMu.Unlock()
        if firstArrival.IsZero() {
            // first arrival, set the firstArrival time and return 0 for elapsed time
            firstArrival = arrivedAt
            return 0
        }
        // subsequent arrivals, calculate elapsed time since first arrival
        return arrivedAt.Sub(firstArrival)
    }

    mux := http.NewServeMux()
    mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        // record the arrival time of the request
        arrivedAt := time.Now()

        // obtain the request ID from the query parameters and parse it as an unsigned integer
        id, err := strconv.ParseUint(r.URL.Query().Get("id"), 10, 64)
        if err != nil {
            http.Error(w, err.Error(), http.StatusBadRequest)
            return
        }

        // determine the service time for the request based on its ID and the elapsed time
        delay := chooser.serviceTime(id, phaseElapsedFor(arrivedAt))

        // try to acquire a slot for processing
        slots <- struct{}{}
        // sleep for the specified delay to simulate processing time
        time.Sleep(delay)
        // release the slot after processing is complete
        <-slots

        // respond with a JSON indicating successful processing
        w.Header().Set("Content-Type", "application/json")
        _ = json.NewEncoder(w).Encode(response{OK: true})
    })

    log.Printf("phase queued SUT listening on %s concurrency=%d delays=[%s,%s,%s,%s] schedule=%s seed=%d",
        *addr, *concurrency, delays[0], delays[1], delays[2], delays[3], schedule.String(), *seed)
    log.Fatal(http.ListenAndServe(*addr, mux))
}