#!/usr/bin/env python3
import argparse
import base64
import csv
import json
import math
from datetime import datetime
from pathlib import Path

from phase_generate_queued_sut_cdf import (
    DEFAULT_PHASE_SCHEDULE,
    parse_duration_ms,
    parse_phase_schedule,
    percentile,
    simulate_ground_truth,
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

# HARD-CODED mapping of RPS to concurrency
CONCURRENCY_BY_RPS = {
    5000: 2000,
    12000: 4800,
    15000: 6000,
}

def parse_sut_time_ms(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000.0

def phase_for_elapsed(elapsed_s, phase_schedule):
    """Determines the active phase index for a given elapsed time based on the phase schedule."""
    active_idx = 0
    for idx, (start_s, _weights) in enumerate(phase_schedule[1:], start=1):
        if elapsed_s < start_s:
            break
        active_idx = idx
    return active_idx

def phase_label(index, phase_schedule):
    """e.g. "0s-5s", "5s-8s", "8s-9s", "9s-14s", "14s+"""
    start_s, _weights = phase_schedule[index]
    if index + 1 < len(phase_schedule):
        return f"{start_s:g}s-{phase_schedule[index + 1][0]:g}s"
    return f"{start_s:g}s+"


def load_queue_wait(results_csv, phase_schedule):
    """Loads the queue wait times from the results.csv file and organizes them by phase intervals."""
    rows = []
    # obtaining tupes of (arrival_ms, queue_wait_ms) for all samples in the results.csv
    with results_csv.open(newline="") as f:
        for row in csv.reader(f):
            assert len(row) == len(CSV_COLUMNS), f"expected {len(CSV_COLUMNS)} columns in {results_csv}: {row}"
            assert row[1] == "200", f"unexpected non-200 status in {results_csv}: {row[1]}"
            body = json.loads(base64.b64decode(row[6]))
            rows.append((parse_sut_time_ms(body["arrived_at"]), float(body["queue_wait_ms"])))
    assert rows, f"expected at least one row in {results_csv}"
    
    first_arrival_ms = min(arrived_ms for arrived_ms, _queue_wait_ms in rows)
    queue_waits = []
    phase_waits = {phase_label(idx, phase_schedule): [] for idx in range(len(phase_schedule))}
    for arrived_ms, queue_wait_ms in rows:
        # adding to overall queue waits list and also to the specific phase interval list
        queue_waits.append(queue_wait_ms)
        phase_idx = phase_for_elapsed((arrived_ms - first_arrival_ms) / 1000.0, phase_schedule)
        # adding the latency sample to the list of samples for this phase
        phase_waits[phase_label(phase_idx, phase_schedule)].append(queue_wait_ms)
    return sorted(queue_waits), {phase: sorted(values) for phase, values in phase_waits.items()}

def pct_values(sorted_values):
    return {pct: percentile(sorted_values, pct) for pct in SUMMARY_PERCENTILES}

def mean_stddev(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance)

def print_all_runs_summary(exp_name, all_run_pcts, all_truth_pcts):
    runs = sorted(all_truth_pcts)
    print(f"\nSummary of percentiles across all runs for {exp_name} ({len(runs)} runs):")
    print(
        f"{'percentile':>10} {'truth_mean':>12} {'truth_std':>12} "
        f"{'run_mean':>12} {'run_std':>12}"
    )

    for pct in SUMMARY_PERCENTILES:
        truth_values = [all_truth_pcts[run][pct] for run in runs]
        run_values = [all_run_pcts[run][pct] for run in runs]

        truth_mean, truth_stddev = mean_stddev(truth_values)
        run_mean, run_stddev = mean_stddev(run_values)
        
        print(
            f"p{pct * 100:<9g} {truth_mean:12.3f} {truth_stddev:12.3f} "
            f"{run_mean:12.3f} {run_stddev:12.3f}"
        )


def print_phase_comparison(all_phase_waits_by_exp, phase_schedule):
    exp_names = sorted(all_phase_waits_by_exp)
    if len(exp_names) < 2:
        return
    assert len(exp_names) == 2, f"expected exactly 2 experiments to compare, found {exp_names}"

    left_exp, right_exp = exp_names
    runs = sorted(set(all_phase_waits_by_exp[left_exp]) & set(all_phase_waits_by_exp[right_exp]))
    assert runs, "no matching runs found between experiments"   # e.g. [1, 2, 3, 4, 5]

    print(f"\nPhase queue wait comparison ({right_exp} - {left_exp}), paired run means:")
    print(f"{'phase':>12} {'delta_mean':>14} {'delta_mean_std':>14}")
    for phase in [phase_label(idx, phase_schedule) for idx in range(len(phase_schedule))]:
        delta_means = []
        for run in runs:
            left = all_phase_waits_by_exp[left_exp][run][phase]
            right = all_phase_waits_by_exp[right_exp][run][phase]
            assert left and right, f"expected samples for phase {phase} run {run}"

            left_mean = sum(left) / len(left)
            right_mean = sum(right) / len(right)
            delta_means.append(right_mean - left_mean)

        delta_mean, delta_mean_stddev = mean_stddev(delta_means)
        print(
            f"{phase:>12} "
            f"{delta_mean:14.3f} "
            f"{delta_mean_stddev:14.3f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare phase-queued-sut queue waits with ideal phased open-loop truth.")
    parser.add_argument("--input-dir", type=Path, default=Path("experiments_phase_queued_sut"), help="directory containing rps_*/run_*/results.csv")
    parser.add_argument("--rps", type=float, required=True)
    parser.add_argument("--duration", type=float, default=30.0, help="experiment duration in seconds")
    parser.add_argument("--delays", default="10ms,50ms,100ms,4s")
    parser.add_argument("--phase-schedule", type=parse_phase_schedule, default=parse_phase_schedule(DEFAULT_PHASE_SCHEDULE))
    parser.add_argument("--runs", type=int, default=1, help="number of runs to compare (default: 1)")
    args = parser.parse_args()

    delays_ms = [parse_duration_ms(part) for part in args.delays.split(",") if part.strip()]
    all_phase_waits_by_exp = {}

    for exp_dir in sorted(args.input_dir.iterdir()):
        rps = int(float(exp_dir.name.split("_")[1]))
        if rps != args.rps:
            continue
        print(f"Processing experiment directory: {exp_dir}")

        concurrency = CONCURRENCY_BY_RPS[rps]
        all_run_pcts, all_truth_pcts, all_phase_waits = {}, {}, {}
        for run in range(1, args.runs + 1):
            # obtaining ground truth values
            truth_samples = simulate_ground_truth(
                args.rps,
                concurrency,
                args.duration,
                0,
                run,
                delays_ms,
                args.phase_schedule,
            )
            truth_values = sorted(row["queue_wait_ms"] for row in truth_samples)

            # obtaining run values and sorted into specific phase intervals
            results_csv = exp_dir / f"run_{run}" / "results.csv"
            run_values, phase_waits = load_queue_wait(results_csv, args.phase_schedule)

            all_truth_pcts[run] = pct_values(truth_values)
            all_run_pcts[run] = pct_values(run_values)
            all_phase_waits[run] = phase_waits

        print_all_runs_summary(exp_dir.name, all_run_pcts, all_truth_pcts)
        all_phase_waits_by_exp[exp_dir.name] = all_phase_waits

    print_phase_comparison(all_phase_waits_by_exp, args.phase_schedule)
