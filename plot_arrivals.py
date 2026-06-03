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


def load_arrivals(path: str, field: str = "arrived_at_s") -> np.ndarray:
    """Return sorted array of <field> values from a JSONL log."""
    times = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                times.append(obj[field])
            except (json.JSONDecodeError, KeyError):
                continue
    if not times:
        raise ValueError(f"No valid entries with field '{field}' found in {path}")
    arr = np.array(times, dtype=float)
    # shift so t=0 is the first event in this run
    arr -= arr.min()
    return np.sort(arr)


def cumulative_series(arrival_times: np.ndarray, bin_width: float):
    """
    Returns (bin_right_edges, cumulative_counts) at bin_width resolution.
    """
    t_max = arrival_times.max()
    bins = np.arange(0, t_max + bin_width, bin_width)
    if len(bins) < 2:
        bins = np.array([0.0, t_max + bin_width])
    counts, edges = np.histogram(arrival_times, bins=bins)
    cumulative = np.cumsum(counts)
    centres = edges[1:]          # right edge of each bin
    return centres, cumulative


def choose_bin_width(span_s: float, target_bins: int = 50) -> float:
    """Pick a bin width that yields ~target_bins bins for the given span."""
    raw = span_s / target_bins
    # round to a nice number
    for nice in [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005,
                 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]:
        if raw <= nice:
            return nice
    return raw


def main():
    parser = argparse.ArgumentParser(description="Plot cumulative arrivals per stream count")
    parser.add_argument(
        "--files", nargs="+", required=True,
        metavar="STREAMS:PATH",
        help="One entry per run, format  STREAMS:path/to/file.jsonl"
    )
    parser.add_argument("--out", default="arrivals.png", help="Output image path")
    parser.add_argument("--bin-width", type=float, default=None,
                        help="Time bin width in seconds (default: auto-selected from data span)")
    parser.add_argument("--field", default="arrived_at_s",
                        choices=["arrived_at_s", "admitted_at_s", "completed_at_s"],
                        help="Timestamp field to plot (default: arrived_at_s)")
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

    # collect all arrival arrays first so we can pick a shared bin_width
    all_arrivals = []
    for streams, path in runs:
        print(f"Loading {path}  (streams={streams}, field={args.field}) ...", file=sys.stderr)
        try:
            all_arrivals.append((streams, path, load_arrivals(path, field=args.field)))
        except Exception as e:
            print(f"  SKIP: {e}", file=sys.stderr)
            all_arrivals.append((streams, path, None))

    # auto-select bin_width from the widest span if user didn't override
    if args.bin_width is None:
        spans = [a.max() for _, _, a in all_arrivals if a is not None]
        max_span = max(spans) if spans else 1.0
        bin_width = choose_bin_width(max_span)
    else:
        bin_width = args.bin_width

    # if all data fits within 1 second, show x-axis in milliseconds
    use_ms = (max(a.max() for _, _, a in all_arrivals if a is not None) < 1.0)
    scale = 1000.0 if use_ms else 1.0
    x_label = "Timestamp (ms)" if use_ms else "Timestamp (s)"

    print(f"bin_width={bin_width:.4f}s  x_unit={'ms' if use_ms else 's'}", file=sys.stderr)

    fig, ax = plt.subplots(figsize=(9, 6))

    for i, (streams, path, arrivals) in enumerate(all_arrivals):
        if arrivals is None:
            continue
        centres, cumulative = cumulative_series(arrivals, bin_width=bin_width)
        colour = colours[i % len(colours)]
        event_word = {"arrived_at_s": "arrived", "admitted_at_s": "admitted",
                      "completed_at_s": "completed"}.get(args.field, args.field)
        ax.plot(centres * scale, cumulative,
                color=colour,
                linewidth=1.8,
                label=f"Total requests {event_word} ({streams} Streams)")

    ax.set_xlabel(x_label, fontsize=12)
    event_word = {"arrived_at_s": "Arrived", "admitted_at_s": "Admitted",
                  "completed_at_s": "Completed"}.get(args.field, args.field)
    ax.set_ylabel(f"Total Number of Requests {event_word}", fontsize=12)

    default_titles = {
        "arrived_at_s": ("Number of Requests Arrived When h2load Attempts to Send N RPS\n"
                         "to Server with 10s Delay (varying stream counts)"),
        "admitted_at_s": ("Number of Requests Admitted (Given Worker Slot) Over Time\n"
                          "h2load vs Server with 10s Delay (varying stream counts)"),
        "completed_at_s": ("Number of Requests Completed Over Time\n"
                           "h2load vs Server with 10s Delay (varying stream counts)"),
    }
    title = args.title or default_titles.get(args.field, f"Cumulative {args.field} over time")
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