#!/usr/bin/env python3
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

CSV_COLUMNS = [
    "timestamp_ns", "status", "latency_ns", "bytes_out", 
    "bytes_in", "error", "body", "attack", "seq", 
    "method", "url", "headers",
]

def load_send_rate(path):
    df = pd.read_csv(path, header=None, names=CSV_COLUMNS, usecols=["timestamp_ns"])
    df["timestamp_ns"] = pd.to_numeric(df["timestamp_ns"], errors="raise")
    df = df.sort_values("timestamp_ns").reset_index(drop=True)

    start_ns = df["timestamp_ns"].iloc[0]
    df["relative_s"] = (df["timestamp_ns"] - start_ns) / 1_000_000_000.0
    max_bin = int(df["relative_s"].max())

    df["time_bin"] = df["relative_s"].astype(int)
    bins = pd.DataFrame({"time_bin": range(max_bin + 1)})

    counts = df.groupby("time_bin").size().reset_index(name="rate_req_s")

    rates = bins.merge(counts, on="time_bin", how="left").fillna({"rate_req_s": 0})
    rates["time_s"] = rates["time_bin"]
    
    return rates

def plot_send_rates(run_rates, output_path, rps, duration_s=None):
    # ACM Paper Styling Requirements (Matched to CPU/Worker script)
    plt.rcParams.update({
        'font.size': 10,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'font.family': 'serif',
        'pdf.fonttype': 42,
        'ps.fonttype': 42
    })

    fig, ax = plt.subplots(figsize=(3.33, 2.3))

    # Combine all DataFrames and average the rates per second
    all_rates = pd.concat([rates for _, rates in run_rates])
    avg_rates = all_rates.groupby("time_s")["rate_req_s"].mean().reset_index()

    max_time = int(avg_rates["time_s"].max())

    # Plot the averaged rate
    ax.step(
        avg_rates["time_s"], 
        avg_rates["rate_req_s"], 
        where="post", 
        linewidth=1.5, 
        color="#1f77b4", # standard matplotlib blue
        label="Avg Send Rate"
    )

    # Plot the target ideal rate
    ax.axhline(
        rps, 
        color="#d62728", # standard matplotlib red 
        linestyle="--", 
        linewidth=1.5, 
        label=f"Target ({rps}/s)"
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rate (req/s)")
    
    # Matching dotted grid
    ax.grid(True, linestyle=":", alpha=0.7)
    ax.set_xlim(0, duration_s if duration_s is not None else max_time)
    
    # Y-axis scaling to give a little headroom above the target RPS
    max_actual_rate = avg_rates["rate_req_s"].max()
    y_upper_limit = max(rps * 1.15, max_actual_rate * 1.10)
    ax.set_ylim(0, y_upper_limit)

    # Horizontal legend above the plot
    ax.legend(
        loc="lower center", 
        bbox_to_anchor=(0.5, 1.02), 
        ncol=2, 
        frameon=False
    )

    # Remove fig.tight_layout() and replace with explicit layout tuning
    # This leaves 15% padding at the top of the canvas for the legend text
    fig.subplots_adjust(top=0.85)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # The bbox_inches="tight" here is critical—it tells matplotlib to recalculate
    # the bounding box including the elements that sit outside the standard axis lines.
    pdf_output = output_path.with_suffix('.pdf')
    fig.savefig(pdf_output, format='pdf', dpi=300, bbox_inches="tight")
    
    png_output = output_path.with_suffix('.png')
    fig.savefig(png_output, format='png', dpi=300, bbox_inches="tight")
    
    plt.close(fig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot average Vegeta send rate from results.csv timestamps.")
    parser.add_argument("--rps", type=int, required=True, help="configured target RPS")
    parser.add_argument("--runs", type=int, default=1, help="number of run_N directories to read")
    parser.add_argument("--experiments-dir", type=Path, default=Path("phase-smooth-data/experiments_phase_queued_sut"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cpu-set", type=str, required=True, help="CPU set label to include in plot title")
    args = parser.parse_args()

    exp_base = args.experiments_dir / f"rps_{args.rps}_{args.cpu_set}"
    run_rates = []

    for run in range(1, args.runs + 1):
        results_csv = exp_base / f"run_{run}" / "results.csv"
        print(f"Processing {results_csv}...")
        run_rates.append((run, load_send_rate(results_csv)))

    # Base output path
    output = args.output or Path("results") / f"rps_{args.rps}_{args.cpu_set}" / "send_rate_1s_avg"
    
    plot_send_rates(run_rates, output, args.rps, duration_s=30)
    
    print(f"Wrote plot: {output.with_suffix('.pdf')}")
    print(f"Wrote plot: {output.with_suffix('.png')}")