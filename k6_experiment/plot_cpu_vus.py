#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

def parse_time(raw_val):
    # Truncate nanoseconds to microseconds (6 digits) for Python datetime compatibility
    clean = re.sub(r'(\.\d{6})\d+', r'\1', raw_val.strip().replace('Z', '+00:00'))
    return datetime.fromisoformat(clean).timestamp()

def parse_cores(cores_str):
    cores = set()
    for part in [p.strip() for p in cores_str.split(",") if p.strip()]:
        if "-" in part:
            s, e = map(int, part.split("-"))
            cores.update(range(s, e + 1))
        else:
            cores.add(int(part))
    return sorted(cores)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot CPU utilization vs k6 VUs.")
    parser.add_argument("--cpu", required=True)
    parser.add_argument("--k6", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cores", default="0-7")
    args = parser.parse_args()

    # Parse requested cores (e.g. "0-3, 5" -> ["core_0", "core_1", ...])
    selected_cores = parse_cores(args.cores)
    core_keys = [f"core_{c}" for c in selected_cores]

    # Extract k6 VU Data (for both "vus" and "vus_max")
    points = {"vus": [], "vus_max": []}
    with open(args.k6, "r", encoding="utf-8") as f:
        for line in f:
            if '"metric":"vus"' in line or '"metric":"vus_max"' in line:
                row = json.loads(line)
                if row.get("type") == "Point":
                    # adding the VU data points
                    points[row["metric"]].append(
                        (parse_time(row["data"]["time"]), float(row["data"]["value"]))
                    )

    for v in points.values():
        v.sort()
    all_points = points["vus"] + points["vus_max"]

    # obtaining the time range of the k6 run from the VU data points
    start_time = min(p[0] for p in all_points)
    end_time = max(p[0] for p in all_points)

    # Read and average CPU data
    cpu_x, cpu_avg = [], []
    with open(args.cpu, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = float(row.get("timestamp_unix") or 0)
            # if it is between the start and end time of the k6 run, we will consider it for plotting
            if start_time <= ts <= end_time:
                # obtaining the CPU utilization values for the selected cores
                vals = [float(row[c]) for c in core_keys if row.get(c)]
                # adding relative timestamp and average CPU utilization
                cpu_x.append(ts - start_time)
                cpu_avg.append(sum(vals) / len(vals))

    # Plotting
    fig, ax_cpu = plt.subplots(figsize=(13, 6.5))
    ax_vus = ax_cpu.twinx()

    # shading the CPU in green and plotting the average line
    ax_cpu.fill_between(cpu_x, cpu_avg, color="#d9ead3", alpha=0.65, label="CPU avg")
    ax_cpu.plot(cpu_x, cpu_avg, color="#38761d", linewidth=2.0)

    # plotting the VU capacity and active VUs as step lines
    x, y = zip(*[(t - start_time, v) for t, v in points["vus_max"]])
    ax_vus.step(x, y, where="post", color="#111111", linewidth=2.2, label="Allocated VUs")
    
    x, y = zip(*[(t - start_time, v) for t, v in points["vus"]])
    ax_vus.step(x, y, where="post", color="#cc0000", linewidth=2.0, linestyle="--", label="Active VUs")

    # Formatting
    duration = max(0, end_time - start_time)
    core_label = ", ".join(str(c) for c in sorted(selected_cores))
    
    first_last_core_idx_label = f"{core_label.split(',')[0]} - {core_label.split(',')[-1]}"
    ax_cpu.set(title=f"CPU Average for Cores {first_last_core_idx_label}", 
               xlabel="Time since k6 run start (s)", ylabel="CPU utilization (%)",
               xlim=(0, duration), ylim=(0, 105))
    ax_vus.set_ylabel("Virtual users")
    ax_cpu.grid(True, linestyle="--", alpha=0.35)

    lines_cpu, labels_cpu = ax_cpu.get_legend_handles_labels()
    lines_vus, labels_vus = ax_vus.get_legend_handles_labels()
    ax_cpu.legend(lines_cpu + lines_vus, labels_cpu + labels_vus, loc="upper left")

    # Save the plot
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200, bbox_inches="tight")
    print(f"Wrote plot: {args.output}")
