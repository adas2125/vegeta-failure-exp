import argparse
import json
import math
import re
import sys
import statistics
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt

PERCENTILES = [0, 50, 75, 90, 95, 97.5, 99, 99.5, 99.9, 99.99, 99.999, 99.9999]

def parse_args():
    p = argparse.ArgumentParser(description="Plot k6 latency percentile curves.")
    p.add_argument("--results-dir", default="results", help="Output dir")
    p.add_argument("--metric", default="http_req_duration", help="Metric to plot")
    p.add_argument("--start-after", required=True, type=float, help="in seconds")
    p.add_argument("--end-before", required=True, type=float, help="Elapsed time cutoff")
    return p.parse_args()

def parse_timestamp(val):
    val = val.strip().replace("Z", "+00:00")
    if m := re.match(r"^(.*)\.(\d+)([+-]\d{2}:\d{2})$", val):
        val = f"{m[1]}.{m[2][:6].ljust(6, '0')}{m[3]}"
    return datetime.fromisoformat(val).timestamp()

def calc_percentile(data, p):
    k = (len(data) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return data[f] if f == c else data[f] * (c - k) + data[c] * (k - f)

def load_metric_values(path, metric, start_s=0.0, end_s=None):
    points = []

    # adding the timestamp and the latency value to points list
    with open(path, "r", encoding="utf-8") as f:
        for line in filter(str.strip, f):
            row = json.loads(line)
            if row.get("type") == "Point" and row.get("metric") == metric:
                points.append((parse_timestamp(row["data"]["time"]), float(row["data"]["value"])))

    run_start = min(ts for ts, _ in points)
    end_s = end_s if end_s is not None else float("inf")
    
    # filtering based on the start and end time, and sorting the latency values
    filtered = sorted(val for ts, val in points if start_s <= (ts - run_start) < end_s)
    return filtered

def plot_runs(res_dir, metric, start_s, end_s):
    paths = sorted(Path(res_dir).glob("*/*/burst-results.json"))
    print(f"Found paths: {[str(p) for p in paths]}")
    fig, ax = plt.subplots(figsize=(12.5, 7))

    # Dictionary to hold our metric aggregates for CI calculation
    stats_data = defaultdict(lambda: {"p95": [], "p97.5": []})

    for path in paths:
        vals = load_metric_values(path, metric, start_s, end_s)

        # calculating the percentiles and their corresponding latency values
        x_vals = [100 / (100 - p) for p in PERCENTILES]
        y_vals = [calc_percentile(vals, p) for p in PERCENTILES]
        
        # Determine group prefix and styling
        profile_name = path.parent.parent.name
        run_name = path.parent.name
        
        if profile_name.startswith("limited_"):
            group_prefix = "limited"
            l_style = "--"
        else:
            group_prefix = "full"
            l_style = "-"
            
        # Collect p95 and p97.5 for CI calculation
        stats_data[group_prefix]["p95"].append(y_vals[PERCENTILES.index(95)])
        stats_data[group_prefix]["p97.5"].append(y_vals[PERCENTILES.index(97.5)])

        # Label format: "profile_name / run_name"
        label = f"{profile_name} / {run_name}"
        ax.plot(x_vals, y_vals, alpha=0.9, linewidth=2.0, label=label, linestyle=l_style)
        print(f"Loaded {len(vals)} samples from {label}")

    # Calculate and print Means & Confidence Intervals
    print("\n" + "="*50)
    print("Aggregate Statistics (Mean ± 95% CI)")
    print("="*50)
    for group, metrics in stats_data.items():
        for pct, p_vals in metrics.items():
            n = len(p_vals)
            if n > 1:
                mean_val = statistics.mean(p_vals)
                std_dev = statistics.stdev(p_vals)
                # Standard Normal 95% CI Margin: 1.96 * (std_dev / sqrt(n))
                margin = 1.96 * (std_dev / math.sqrt(n))
                print(f"[{group}] {pct} Mean: {mean_val:.2f} ms ± {margin:.2f} (95% CI: [{mean_val - margin:.2f}, {mean_val + margin:.2f}])")
            elif n == 1:
                print(f"[{group}] {pct} Mean: {p_vals[0]:.2f} ms (N=1, cannot calculate CI)")
    print("="*50 + "\n")

    ax.set(title="Latency Distributions", xlabel="Percentile", ylabel="Latency (ms)", 
           xscale="log", xlim=(1, None), ylim=(0, None))
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")
    
    ticks = [0, 90, 99, 99.9, 99.99, 99.999, 99.9999]
    ax.set_xticks([100 / (100 - t) for t in ticks])
    ax.set_xticklabels([f"{t:g}%" for t in ticks])

    suffix = f"-after-{start_s:g}s" if start_s else ""
    suffix += f"-before-{end_s:g}s" if end_s else ""
    out_png = Path(res_dir) / f"latency-distributions{suffix}.png"
    
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote plot: {out_png}")

if __name__ == "__main__":
    args = parse_args()
    start_s, end_s = args.start_after, args.end_before
    plot_runs(args.results_dir, args.metric, start_s, end_s)