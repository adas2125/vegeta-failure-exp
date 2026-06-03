#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Print latency percentiles from k6 JSON output.")
    parser.add_argument(
        "k6_json",
        nargs="?",
        default="burst-results.json",
        help="Path to k6 line-delimited JSON output (default: burst-results.json).",
    )
    parser.add_argument(
        "--metric",
        default="http_req_duration",
        help="k6 metric to summarize (default: http_req_duration).",
    )
    return parser.parse_args()


def percentile(sorted_values, p):
    k = (len(sorted_values) - 1) * p / 100
    floor = math.floor(k)
    ceil = math.ceil(k)
    if floor == ceil:
        return sorted_values[floor]
    return sorted_values[floor] * (ceil - k) + sorted_values[ceil] * (k - floor)


def main():
    args = parse_args()
    values = []

    with Path(args.k6_json).open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("type") == "Point" and row.get("metric") == args.metric:
                values.append(float(row["data"]["value"]))

    if not values:
        raise SystemExit(f"No {args.metric} samples found in {args.k6_json}")

    values.sort()
    print(f"Latency metric: {args.metric}")
    print(f"Samples: {len(values)}")
    for p in [50, 90, 95, 99, 99.9]:
        print(f"p{p}: {percentile(values, p):.3f} ms")
    print(f"avg: {sum(values) / len(values):.3f} ms")
    print(f"min: {values[0]:.3f} ms")
    print(f"max: {values[-1]:.3f} ms")


if __name__ == "__main__":
    main()
