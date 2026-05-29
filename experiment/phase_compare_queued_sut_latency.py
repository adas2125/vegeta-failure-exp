#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

from phase_generate_queued_sut_cdf import (
    DEFAULT_PHASE_SCHEDULE,
    parse_duration_ms,
    parse_phase_schedule,
    percentile,
    simulate_ground_truth,
    filename_number,
    plot_percentiles,
    SUMMARY_PERCENTILES,
)

CSV_COLUMNS = [
    "timestamp_ns",
    "status",
    "latency_ns",
    "bytes_out",
    "bytes_in",
    "error",
    "body",
    "attack",
    "seq",
    "method",
    "url",
    "headers",
]

def load_run_latencies(results_csv):
    latencies, statuses = [], {}
    with results_csv.open(newline="") as f:
        for row in csv.reader(f):
            if len(row) != len(CSV_COLUMNS):
                continue
            status = row[1]
            statuses[status] = statuses.get(status, 0) + 1
            if status != "200":
                continue
            # add the latencies in ms to the list
            latencies.append(float(row[2]) / 1_000_000.0)
    return sorted(latencies), statuses

def percentile_curve(sorted_values, percentiles):
    return [percentile(sorted_values, pct) for pct in percentiles]

def write_plot(path, truth_values_by_name, run_values_by_name, rps, concurrency):
    percentiles, x = plot_percentiles()

    fig, ax = plt.subplots(figsize=(10, 6))
    for name, values in truth_values_by_name:
        ax.plot(x, percentile_curve(values, percentiles), linewidth=2.2, linestyle="--", label=name)

    for name, values in run_values_by_name:
        ax.plot(x, percentile_curve(values, percentiles), linewidth=2.0, label=name)

    ax.set_title(f"Phase Queued SUT Latency Distribution - {rps:g} RPS, C={concurrency}")
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

def print_summary(truth_values, run_values, statuses, truth_seed):
    print(f"truth_seed={truth_seed}")
    print(f"statuses={statuses}")
    print(f"samples={len(run_values)}")
    print(f"{'percentile':>10} {'truth_ms':>12} {'run_ms':>12} {'run-truth':>12}")
    for pct in SUMMARY_PERCENTILES:
        truth = percentile(truth_values, pct)
        run = percentile(run_values, pct)
        print(f"p{pct * 100:<9g} {truth:12.3f} {run:12.3f} {run - truth:12.3f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare phase-queued-sut run latency with ideal phased open-loop truth.")
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--rps", type=float, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True, help="experiment duration in seconds")
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1, help="first ground-truth seed; run N uses seed + N - 1")
    parser.add_argument("--delays", default="10ms,50ms,100ms,4s")
    parser.add_argument("--phase-schedule", type=parse_phase_schedule, default=parse_phase_schedule(DEFAULT_PHASE_SCHEDULE))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--runs", type=int, default=1, help="number of runs to compare (default: 1)")
    args = parser.parse_args()

    delays_ms = [parse_duration_ms(part) for part in args.delays.split(",") if part.strip()]

    truth_values_by_name = []
    run_values_by_name = []
    for run in range(1, args.runs + 1):
        print(f"run {run}/{args.runs}")

        truth_seed = args.seed + run - 1
        truth_samples = simulate_ground_truth(
            args.rps,
            args.concurrency,
            args.duration,
            args.start_id,
            truth_seed,
            delays_ms,
            args.phase_schedule,
        )
        truth_values = sorted(row["latency_ms"] for row in truth_samples)
        truth_values_by_name.append((f"Run {run} ideal (seed={truth_seed})", truth_values))

        # replace the /run_1/results.csv at the end with /run_{run}/results.csv to load the correct run's results
        results_csv = args.results_csv.parent.parent / f"run_{run}" / args.results_csv.name
        run_values, statuses = load_run_latencies(results_csv)
        run_values_by_name.append((f"Run {run} Vegeta latency", run_values))
        print_summary(truth_values, run_values, statuses, truth_seed)

    output = args.output or (
        Path("results")
        / "phase_queued_sut_comparison"
        / f"rps_{filename_number(args.rps)}"
        / f"runs_1_to_{args.runs}"
        / "latency_distribution_comparison.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    write_plot(output, truth_values_by_name, run_values_by_name, args.rps, args.concurrency)
    print(f"wrote plot: {output}")
