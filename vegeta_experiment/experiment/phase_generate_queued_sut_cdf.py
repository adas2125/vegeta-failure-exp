#!/usr/bin/env python3
import argparse
import csv
import hashlib
import heapq
import math
from pathlib import Path
import matplotlib.pyplot as plt

# Request assignment hashing must match cmd/phase-queued-sut/main.go exactly.
DEFAULT_PHASE_SCHEDULE = "0:70,20,8,2;5:64,23,10,3;8:20,20,20,30;9:64,23,10,3;14:70,20,8,2"
SUMMARY_PERCENTILES = [0.50, 0.90, 0.95, 0.99, 0.999, 0.9999]
PLOT_INV_PERCENTILES = [1, 2, 5, 10, 20, 100, 1_000, 10_000, 100_000, 1_000_000]

def parse_duration_ms(value):
    units = [
        ("ns", 1 / 1_000_000),
        ("us", 1 / 1_000),
        ("µs", 1 / 1_000),
        ("ms", 1),
        ("s", 1_000),
        ("m", 60_000),
        ("h", 3_600_000),
    ]
    value = value.strip()
    for suffix, multiplier in units:
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value)


def parse_weights(value):
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_phase_start_seconds(value):
    value = value.strip()
    if any(ch.isalpha() or ch == "µ" for ch in value):
        return parse_duration_ms(value) / 1000.0
    return float(value)


def parse_phase_schedule(value):
    phases = []
    for raw_phase in value.split(";"):
        raw_phase = raw_phase.strip()
        if not raw_phase:
            continue
        start_raw, weights_raw = raw_phase.split(":", 1)
        start_s = parse_phase_start_seconds(start_raw)
        if start_s < 0:
            raise argparse.ArgumentTypeError("phase starts must be >= 0")
        phases.append((start_s, parse_weights(weights_raw)))

    if not phases:
        raise argparse.ArgumentTypeError("phase schedule must contain at least one phase")
    phases.sort(key=lambda phase: phase[0])
    if phases[0][0] != 0:
        raise argparse.ArgumentTypeError("phase schedule must start at 0")
    for prev, cur in zip(phases, phases[1:]):
        if prev[0] == cur[0]:
            raise argparse.ArgumentTypeError(f"duplicate phase start: {cur[0]:g}s")
    return phases


def phase_weights(elapsed_s, phase_schedule):
    """returns weights for the phase we are in"""
    active = phase_schedule[0]
    # loop through the phases
    for phase in phase_schedule[1:]:
        if elapsed_s < phase[0]:
            # we are not in this phase yet, stick with the previous
            break
        active = phase
    return active[1]


def hash_unit(request_id, seed):
    payload = seed.to_bytes(8, "big", signed=False) + request_id.to_bytes(8, "big", signed=False)
    digest = hashlib.sha256(payload).digest()
    x = int.from_bytes(digest[:8], "big")
    # Make the result a float in [0, 1) by shifting down to 53 bits and dividing by 2^53.
    return (x >> 11) / float(1 << 53)


def service_time_ms(request_id, seed, delays_ms, weights):
    total = sum(weights)
    thresholds = [
        weights[0] / total,
        (weights[0] + weights[1]) / total,
        (weights[0] + weights[1] + weights[2]) / total,
        1.0,
    ]

    # assignment of delays is based on request_id and seed, so that it is deterministic and repeatable
    unit = hash_unit(request_id, seed)
    for delay, threshold in zip(delays_ms, thresholds):
        if unit < threshold:
            return delay
    return delays_ms[-1]


def simulate_ground_truth(rps, concurrency, duration_s, start_id, seed, delays_ms, phase_schedule):
    request_count = math.ceil(rps * duration_s)

    # allocating a list of workers and using a heap
    workers = [0.0] * concurrency
    heapq.heapify(workers)

    samples = []
    for offset in range(request_count):
        # simulating the arrival of requests at the ideal open-loop rate
        request_id = start_id + offset
        arrival_ms = offset * 1000.0 / rps
        # get the weights for the phase we are in
        weights = phase_weights(arrival_ms / 1000.0, phase_schedule)
        # simulate the service time for this request using these weights
        service_ms = service_time_ms(request_id, seed, delays_ms, weights)

        # getting the earliest available worker
        earliest_available_ms = heapq.heappop(workers)
        # calculating the start time
        start_ms = max(arrival_ms, earliest_available_ms)
        finish_ms = start_ms + service_ms
        # how much time this request had to wait
        queue_wait_ms = start_ms - arrival_ms
        # the processing latency for this request
        latency_ms = finish_ms - arrival_ms
        # push to the heap indicating this worker will be busy until finish_ms
        heapq.heappush(workers, finish_ms)

        # adding the request sample to the list of samples
        samples.append(
            {
                "request_id": request_id,
                "arrival_ms": arrival_ms,
                "start_ms": start_ms,
                "finish_ms": finish_ms,
                "queue_wait_ms": queue_wait_ms,
                "service_ms": service_ms,
                "latency_ms": latency_ms,
            }
        )

    return samples


def percentile(sorted_values, pct):
    idx = math.ceil(pct * len(sorted_values)) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def filename_number(value):
    return f"{value:g}".replace("-", "m").replace(".", "p")


def plot_percentiles():
    percentiles = [0.0 if inv == 1 else 1.0 - (1.0 / inv) for inv in PLOT_INV_PERCENTILES]
    return percentiles, PLOT_INV_PERCENTILES


def write_latency_plot(path, rps, latencies):
    percentiles, x = plot_percentiles()
    y = [percentile(latencies, pct) for pct in percentiles]

    fig, ax = plt.subplots(figsize=(10, 6))
    # percentiles on log-scale (x-axis) and latency on linear scale (y-axis)
    ax.plot(x, y, linewidth=2.0, label="Ideal phased open-loop")
    ax.set_title(f"Ideal Phased Open-Loop Latency (RPS={rps:g})")
    ax.set_xlabel("Percentile")
    ax.set_ylabel("Latency (ms)")
    ax.set_xscale("log")
    ax.set_xlim(left=1)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")
    ax.set_xticks([1, 10, 100, 1_000, 10_000, 100_000, 1_000_000])
    ax.set_xticklabels(["0%", "90%", "99%", "99.9%", "99.99%", "99.999%", "99.9999%"])
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def print_summary(sorted_latencies, samples, rps, concurrency, duration_s, phase_schedule):
    print(f"rps={rps:g} concurrency={concurrency} duration={duration_s:g}s requests={len(samples)}")
    print(f"{'percentile':>10} {'latency_ms':>12}")
    for pct in SUMMARY_PERCENTILES:
        print(f"p{pct * 100:<9g} {percentile(sorted_latencies, pct):12.3f}")
    print(f"mean_queue_wait_ms {sum(row['queue_wait_ms'] for row in samples) / len(samples):.3f}")
    print(f"max_queue_wait_ms {max(row['queue_wait_ms'] for row in samples):.3f}")

    # break down the queue wait by phase interval
    phase_waits = []
    for idx, (start_s, weights) in enumerate(phase_schedule):
        end_s = phase_schedule[idx + 1][0] if idx + 1 < len(phase_schedule) else duration_s

        # obtain the phase samples that fall within this phase interval
        phase_samples = [
            row for row in samples
            if start_s <= row["arrival_ms"] / 1000.0 < end_s
        ]

        if not phase_samples:
            continue

        mean_wait = sum(row["queue_wait_ms"] for row in phase_samples) / len(phase_samples)
        max_wait = max(row["queue_wait_ms"] for row in phase_samples)
        phase_waits.append((start_s, end_s, len(phase_samples), mean_wait, max_wait))

    print(f"{'phase_start_s':>14} {'phase_end_s':>12} {'samples':>10} {'mean_wait_ms':>14} {'max_wait_ms':>14}")
    for start_s, end_s, count, mean_wait, max_wait in phase_waits:
        print(f"{start_s:14.3f} {end_s:12.3f} {count:10d} {mean_wait:14.3f} {max_wait:14.3f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ideal open-loop truth for phase-queued-sut.")
    parser.add_argument("--rps", type=float, required=True, help="ideal open-loop arrival rate")
    parser.add_argument("--concurrency", type=int, required=True, help="phase-queued-sut --concurrency value")
    parser.add_argument("--duration", type=float, default=30.0, help="experiment duration in seconds")
    parser.add_argument("--start-id", type=int, default=0, help="first request id")
    parser.add_argument("--seed", type=int, default=1, help="phase-queued-sut --seed value")
    parser.add_argument("--delays", default="10ms,50ms,100ms,4s")
    parser.add_argument("--phase-schedule", type=parse_phase_schedule, default=parse_phase_schedule(DEFAULT_PHASE_SCHEDULE))
    args = parser.parse_args()

    delays_ms = [parse_duration_ms(part) for part in args.delays.split(",") if part.strip()]
    output_dir = Path("results") / "phase_queued_sut_ground_truth" / f"rps_{filename_number(args.rps)}_c_{args.concurrency}"
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = simulate_ground_truth(
        args.rps,
        args.concurrency,
        args.duration,
        args.start_id,
        args.seed,
        delays_ms,
        args.phase_schedule,
    )
    sorted_latencies = sorted(row["latency_ms"] for row in samples)

    write_latency_plot(output_dir / "latency.png", args.rps, sorted_latencies)
    print_summary(sorted_latencies, samples, args.rps, args.concurrency, args.duration, args.phase_schedule)
    print(f"wrote outputs to {output_dir}")
