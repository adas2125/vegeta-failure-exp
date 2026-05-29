#!/usr/bin/env python3
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


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


def load_send_rate(path, duration_s=None):
    df = pd.read_csv(path, header=None, names=CSV_COLUMNS, usecols=["timestamp_ns"])
    df["timestamp_ns"] = pd.to_numeric(df["timestamp_ns"], errors="raise")
    df = df.sort_values("timestamp_ns").reset_index(drop=True)

    start_ns = df["timestamp_ns"].iloc[0]
    df["relative_s"] = (df["timestamp_ns"] - start_ns) / 1_000_000_000.0
    if duration_s is not None:
        df = df[df["relative_s"] <= duration_s]
        max_bin = int(duration_s)
    else:
        max_bin = int(df["relative_s"].max())

    df["time_bin"] = df["relative_s"].astype(int)
    bins = pd.DataFrame({"time_bin": range(max_bin + 1)})
    counts = df.groupby("time_bin").size().reset_index(name="rate_req_s")
    rates = bins.merge(counts, on="time_bin", how="left").fillna({"rate_req_s": 0})
    rates["time_s"] = rates["time_bin"]
    return rates


def plot_send_rates(run_rates, output_path, rps, duration_s=None):
    plt.figure(figsize=(12, 6))
    max_time = 0

    for run, rates in run_rates:
        max_time = max(max_time, int(rates["time_s"].max()))
        plt.step(rates["time_s"], rates["rate_req_s"], where="post", linewidth=1.8, label=f"Run {run}")

    if rps > 0:
        plt.axhline(rps, color="black", linestyle="--", linewidth=1.5, label=f"Ideal {rps}/s")

    plt.xlabel("Time since first Vegeta result timestamp (s)")
    plt.ylabel("Request-start rate (req/s)")
    plt.title("Vegeta Request-Start Rate (1s bins)")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.xlim(0, duration_s if duration_s is not None else max_time)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot Vegeta request-start/send rate from results.csv timestamps.")
    parser.add_argument("--rps", type=int, required=True, help="configured target RPS")
    parser.add_argument("--runs", type=int, default=1, help="number of run_N directories to read")
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments_phase_queued_sut"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--duration", type=float, default=None, help="optional plot duration in seconds")
    args = parser.parse_args()

    exp_base = args.experiments_dir / f"rps_{args.rps}"
    run_rates = []
    for run in range(1, args.runs + 1):
        results_csv = exp_base / f"run_{run}" / "results.csv"
        if not results_csv.exists():
            raise FileNotFoundError(f"missing {results_csv}")
        print(f"Processing {results_csv}...")
        run_rates.append((run, load_send_rate(results_csv, args.duration)))

    output = args.output or Path("results") / f"rps_{args.rps}" / "send_rate_1s_all_runs.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plot_send_rates(run_rates, output, args.rps, args.duration)
    print(f"wrote plot: {output}")


if __name__ == "__main__":
    main()
