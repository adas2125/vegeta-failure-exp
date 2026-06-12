"""
The purpose of this script is to verify that the assigned delays 
by the SUT match the expected delays based on the request_id, phase schedule, and
configured delays. It also prints out the distribution of assigned delays for each phase
to allow for sanity-checking the distribution. This script gives us confidence that
the SUT is correctly implementing the phase-queued-sut logic and allows us to identify
any discrepancies between the expected and assigned delays.
"""

import argparse
import base64
import csv
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from phase_generate_queued_sut_cdf import (
    DEFAULT_PHASE_SCHEDULE,
    parse_duration_ms,
    parse_phase_schedule,
    service_time_ms,
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


@dataclass
class PhaseStats:
    index: int
    start_s: float
    end_s: float | None
    weights: list[float]
    counts: Counter = field(default_factory=Counter)

    @property
    def samples(self):
        return sum(self.counts.values())


def parse_delays(value):
    delays = [parse_duration_ms(part) for part in value.split(",") if part.strip()]
    if len(delays) != 4:
        raise argparse.ArgumentTypeError(f"expected four delays, got {len(delays)}")
    return delays


def phase_for_elapsed(elapsed_s, phase_schedule):
    active_idx = 0
    for idx, (start_s, _weights) in enumerate(phase_schedule[1:], start=1):
        if elapsed_s < start_s:
            break
        active_idx = idx

    start_s, weights = phase_schedule[active_idx]
    end_s = phase_schedule[active_idx + 1][0] if active_idx + 1 < len(phase_schedule) else None
    return active_idx, start_s, end_s, weights


def phase_label(stats):
    if stats.end_s is None:
        return f"{stats.start_s:g}s+"
    return f"{stats.start_s:g}s-{stats.end_s:g}s"


def new_stats(index, start_s, end_s, weights):
    return PhaseStats(index=index, start_s=start_s, end_s=end_s, weights=weights)


def get_stats(stats_by_phase, index, start_s, end_s, weights):
    # initializing stats for phase if we haven't seen it before
    if index not in stats_by_phase:
        stats_by_phase[index] = new_stats(index, start_s, end_s, weights)
    # returns the stats for the current phase
    return stats_by_phase[index]


def parse_sut_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_sut_rows(results_csv):
    rows = []
    statuses = Counter()
    decode_errors = 0

    with results_csv.open(newline="") as f:
        for rec in csv.reader(f):
            if len(rec) != len(CSV_COLUMNS):
                continue
            statuses[rec[1]] += 1
            if rec[1] != "200":
                continue
            try:
                body = json.loads(base64.b64decode(rec[6]))
                rows.append(
                    {
                        "request_id": int(body["request_id"]),
                        "assigned_delay_ms": float(body["assigned_delay_ms"]),
                        "arrived_at_s": parse_sut_time(body["arrived_at"]),
                    }
                )
            except Exception as exc:
                decode_errors += 1
                if decode_errors <= 5:
                    print(f"warning: failed to decode response body: {exc}", file=sys.stderr)

    return rows, statuses, decode_errors


def analyze_sut_arrivals(results_csv, seed, delays_ms, phase_schedule):
    # load the rows from the results csv, counting statuses and decode errors along the way
    rows, statuses, decode_errors = load_sut_rows(results_csv)

    # santiy-check decoding and SUT arrivals before proceeding with analysis
    assert decode_errors == 0, f"failed to decode {decode_errors} response bodies, aborting analysis"
    assert statuses["200"] == len(rows), f"expected all successful responses to be decodable, but got {statuses['200']} statuses and {len(rows)} decodable rows"

    # obtain the timestamp of the first arrival to use as the origin for calculating elapsed time and determining phases
    origin_s = min(row["arrived_at_s"] for row in rows)

    stats_by_phase = {}
    for row in rows:
        # offset relative to first arrival
        elapsed_s = row["arrived_at_s"] - origin_s

        # calculating the phase we are in
        phase_idx, start_s, end_s, weights = phase_for_elapsed(elapsed_s, phase_schedule)

        # obtaining the expected and assigned delay
        expected_ms = service_time_ms(row["request_id"], seed, delays_ms, weights)
        assigned_ms = row["assigned_delay_ms"]

        # obtaining the stats for the current phase
        stats = get_stats(stats_by_phase, phase_idx, start_s, end_s, weights)

        # increment the count for the phase for the delay assigned to this request
        stats.counts[assigned_ms] += 1

        # assert the assigned_ms matches expected_ms
        assert assigned_ms == expected_ms, f"assigned delay {assigned_ms:.3f}ms does not match expected {expected_ms:.3f}ms for request_id={row['request_id']}"

    return stats_by_phase


def expected_delay_shares(weights):
    total = sum(weights)
    if total <= 0:
        raise ValueError("phase weights must sum to a positive value")
    return [weight / total for weight in weights]


def print_phase_distribution(stats_by_phase, delays_ms):
    for stats in [stats_by_phase[idx] for idx in sorted(stats_by_phase)]:
        # the total number of samples for this phase
        samples = stats.samples
        assert samples is not None, "phase samples should not be None"

        # obtaining weights (e.g. [0.7, 0.2, 0.08, 0.02]) 
        weights = expected_delay_shares(stats.weights)
        print(f"\nphase {stats.index} ({phase_label(stats)}) samples={samples} weights={weights}")
        print(f"{'delay_ms':>10} {'count':>10} {'actual_%':>10} {'expect_%':>10} {'delta':>10}")

        for delay_ms, share in zip(delays_ms, weights):
            # observered count for this delay in this phase
            observed = stats.counts.get(delay_ms, 0)
            expected = samples * share
            actual_pct = 100.0 * (observed / samples)
            expected_pct = 100.0 * share
            delta = observed - expected
            print(f"{delay_ms:10.3f} {observed:10d} {actual_pct:10.3f} {expected_pct:10.3f} {delta:10.1f}")


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Verify phase-queued-sut assigned-delay logic and print per-phase "
            "delay distribution sanity checks."
        )
    )
    parser.add_argument("--input-dir", type=Path, default="experiments_phase_queued_sut", help="The directory constiting of SUT responses to be verified.")
    parser.add_argument("--duration", type=float, default=30.0, help="ideal-arrival duration in seconds")
    parser.add_argument("--delays", type=parse_delays, default=parse_delays("10ms,50ms,100ms,4s"))
    parser.add_argument("--phase-schedule", type=parse_phase_schedule, default=parse_phase_schedule(DEFAULT_PHASE_SCHEDULE))
    return parser

def main():
    args = build_parser().parse_args()
    print(f"[INFO] delays_ms={args.delays} phase_schedule={[(start, weights) for start, weights in args.phase_schedule]}")

    # loop through all files in results directory
    for exp_dir in sorted(args.input_dir.iterdir()):
        print(f"[INFO] Analyzing {exp_dir}...")
        rps = float(exp_dir.name.split("_")[1])

        for run_dir in sorted(exp_dir.iterdir()):
            results_file = run_dir / "results.csv"
            run_id = int(run_dir.name.split("_")[1])
            stats_by_phase = analyze_sut_arrivals(
                results_file,
                run_id,
                args.delays,
                args.phase_schedule,
            )

            print_phase_distribution(stats_by_phase, args.delays)

if __name__ == "__main__":
    raise SystemExit(main())
