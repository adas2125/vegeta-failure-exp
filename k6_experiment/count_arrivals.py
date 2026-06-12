"""
This script uses the sut_arrivals directory, which contains subdirectories for each CPU profile.
It then generates the average and standard deviation of the count of arrivals that were assigned a 
specific SUT delay (e.g., 2s for the slow delay) for each CPU profile.
"""

import argparse
import csv
import math
import re
import statistics
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(
        description="Count arrivals assigned a specific SUT delay per CPU profile."
    )
    # sut_arrivals are captured on the SUT side
    parser.add_argument(
        "--arrivals-dir",
        default="sut_arrivals",
        help="Directory containing cpu_*/arrivals_*/arrivals.csv files.",
    )
    # the slow delay for this setup is 2s
    parser.add_argument(
        "--delay-ms",
        default=2000.0,
        type=float,
        help="Assigned_Delay_MS value to count. Defaults to 2000 ms, i.e. 2s.",
    )
    return parser.parse_args()


def natural_key(path):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.name)
    ]


def count_matching_delay(path, target_delay_ms):
    count = 0
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # obtain the Assigned_Delay_MS value and compare it to the target
            delay_ms = float(row["Assigned_Delay_MS"])
            if math.isclose(delay_ms, target_delay_ms, abs_tol=0.001):
                count += 1
    return count


def summarize_cpu_profile(cpu_dir, target_delay_ms):
    counts = []

    for run_dir in sorted(cpu_dir.glob("arrivals_*"), key=natural_key):
        print("  Processing", run_dir.name)
        arrivals_csv = run_dir / "arrivals.csv"

        # count how many arrivals in this run have the target delay
        counts.append(count_matching_delay(arrivals_csv, target_delay_ms))

    return counts

if __name__ == "__main__":
    args = parse_args()
    arrivals_dir = Path(args.arrivals_dir)

    # obtaining the cpu directories
    cpu_dirs = sorted(
        (path for path in arrivals_dir.iterdir() if path.is_dir()),
        key=natural_key,
    )

    for cpu_dir in cpu_dirs:
        print("Processing", cpu_dir.name)
        counts = summarize_cpu_profile(cpu_dir, args.delay_ms)

        avg = statistics.mean(counts)
        std = statistics.stdev(counts) if len(counts) > 1 else 0.0
        line = f"{cpu_dir.name}: avg={avg:.2f}, std={std:.2f}, n={len(counts)}"
        print(line)
