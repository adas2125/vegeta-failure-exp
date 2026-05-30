#!/usr/bin/env python3
import argparse
import math
import re
from pathlib import Path


DURATION_UNITS = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}
DURATION_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)(ns|us|µs|ms|s|m|h)")


def parse_duration_seconds(value):
    value = value.strip()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return float(value)

    pos = 0
    total = 0.0
    for match in DURATION_PATTERN.finditer(value):
        if match.start() != pos:
            raise ValueError(f"unsupported duration: {value}")
        total += float(match.group(1)) * DURATION_UNITS[match.group(2)]
        pos = match.end()

    if pos != len(value):
        raise ValueError(f"unsupported duration: {value}")
    return total


def write_targets(target_base_url, output_path, count, start_id):
    separator = "&" if "?" in target_base_url else "?"
    with output_path.open("w", encoding="utf-8") as f:
        for offset in range(count):
            f.write(f"GET {target_base_url}{separator}id={start_id + offset}\n")


def main():
    parser = argparse.ArgumentParser(description="Write Vegeta targets with deterministic request IDs.")
    parser.add_argument("--target-base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rps", required=True, type=float)
    parser.add_argument("--duration", required=True)
    parser.add_argument("--start-id", type=int, default=0)
    args = parser.parse_args()

    duration_seconds = parse_duration_seconds(args.duration)
    count = math.ceil(args.rps * duration_seconds)

    write_targets(args.target_base_url, args.output, count, args.start_id)
    print(count)


if __name__ == "__main__":
    main()
