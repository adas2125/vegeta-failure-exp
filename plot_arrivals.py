"""
plot_arrivals.py
----------------
Reads one server_arrivals.jsonl file per stream-count run and plots
cumulative requests arrived over time

Usage:
    python plot_arrivals.py \
        --files 100:run_100streams.jsonl 200:run_200streams.jsonl 256:run_256streams.jsonl 300:run_300streams.jsonl \
        --out arrivals.png

Each --files entry is  STREAMS:PATH  e.g. 100:server_arrivals_m100.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def load_arrivals(path: str) -> np.ndarray:
    """Return sorted array of arrived_at_s values from a JSONL log."""
    times = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                times.append(obj["arrived_at_s"])
            except (json.JSONDecodeError, KeyError):
                continue
    if not times:
        raise ValueError(f"No valid entries found in {path}")
    arr = np.array(times, dtype=float)
    # shift so t=0 is the first arrival in this run
    arr -= arr.min()
    return np.sort(arr)


def cumulative_series(arrival_times: np.ndarray, bin_width: float = 1.0):
    """
    Returns (bin_centres, cumulative_counts) at bin_width-second resolution.
    """
    t_max = arrival_times.max()
    bins = np.arange(0, t_max + bin_width, bin_width)
    counts, edges = np.histogram(arrival_times, bins=bins)
    cumulative = np.cumsum(counts)
    centres = edges[1:]          # right edge of each bin = end of that second
    return centres, cumulative


def main():
    parser = argparse.ArgumentParser(description="Plot cumulative arrivals per stream count")
    parser.add_argument(
        "--files", nargs="+", required=True,
        metavar="STREAMS:PATH",
        help="One entry per run, format  STREAMS:path/to/file.jsonl"
    )
    parser.add_argument("--out", default="arrivals.png", help="Output image path")
    parser.add_argument("--bin-width", type=float, default=1.0,
                        help="Time bin width in seconds (default 1)")
    parser.add_argument("--title", default=None, help="Override plot title")
    args = parser.parse_args()

    # parse STREAMS:PATH pairs
    runs = []
    for token in args.files:
        if ":" not in token:
            print(f"ERROR: expected STREAMS:PATH, got '{token}'", file=sys.stderr)
            sys.exit(1)
        streams_str, path = token.split(":", 1)
        try:
            streams = int(streams_str)
        except ValueError:
            print(f"ERROR: stream count must be an int, got '{streams_str}'", file=sys.stderr)
            sys.exit(1)
        if not Path(path).exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        runs.append((streams, path))

    # sort by stream count for consistent legend ordering
    runs.sort(key=lambda x: x[0])

    # colour cycle matching the reference figure
    colours = ["blue", "green", "purple", "black", "red", "orange"]

    fig, ax = plt.subplots(figsize=(9, 6))

    for i, (streams, path) in enumerate(runs):
        print(f"Loading {path}  (streams={streams}) ...", file=sys.stderr)
        try:
            arrivals = load_arrivals(path)
        except Exception as e:
            print(f"  SKIP: {e}", file=sys.stderr)
            continue

        centres, cumulative = cumulative_series(arrivals, bin_width=args.bin_width)
        colour = colours[i % len(colours)]
        ax.plot(centres, cumulative,
                color=colour,
                linewidth=1.8,
                label=f"Total requests arrived ({streams} Streams)")

    # formatting to match Figure 4.16
    ax.set_xlabel("Timestamp (s)", fontsize=12)
    ax.set_ylabel("Total Number of Requests Arrived", fontsize=12)

    title = args.title or (
        "Number of Requests Arrived When h2load Attempts to Send N RPS\n"
        "to Server with 10s Delay (varying stream counts)"
    )
    ax.set_title(title, fontsize=12)

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.legend(fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    plt.savefig(args.out, dpi=150)
    print(f"Saved → {args.out}", file=sys.stderr)
    plt.show()


if __name__ == "__main__":
    main()