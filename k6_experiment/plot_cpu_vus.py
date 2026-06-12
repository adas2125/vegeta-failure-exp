#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

# Example Usage: python3 plot_cpu_vus.py --cpu results/limited_cpu_0-7/run_1/cpu_utilization.csv --k6 results/limited_cpu_0-7/run_1/burst-results.json --output paper_figures/burst-cpu-vus.png --cores 0-7 --start-time=20 --end-time=50

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
    parser = argparse.ArgumentParser(description="Plot CPU utilization vs k6 VUs with ACM styling.")
    parser.add_argument("--cpu", required=True)
    parser.add_argument("--k6", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cores", default="0-7")
    # New trimming options (default to None so original data bounds can be inferred first)
    parser.add_argument("--start-time", type=float, default=None, help="Trim window start in relative seconds")
    parser.add_argument("--end-time", type=float, default=None, help="Trim window end in relative seconds")
    args = parser.parse_args()

    # Parse requested cores
    selected_cores = parse_cores(args.cores)
    core_keys = [f"core_{c}" for c in selected_cores]
    print(f"Core Keys for plotting: {core_keys}")

    # Extract k6 VU Data
    first_five_count = 0
    points = {"vus": [], "vus_max": []}
    with open(args.k6, "r", encoding="utf-8") as f:
        for line in f:
            # if first_five_count < 5:
            #     print(line.strip())  # Debug: Print each line to verify content
            #     first_five_count += 1
            if '"metric":"vus"' in line or '"metric":"vus_max"' in line:
                row = json.loads(line)
                if row.get("type") == "Point":
                    # print(f"Parsed VU line: {row}")  # Debug: Print parsed VU data
                    # adding the time and the value
                    points[row["metric"]].append(
                        (parse_time(row["data"]["time"]), float(row["data"]["value"]))
                    )
                    # print(points)

    for v in points.values():
        v.sort()
    # all_points consists of both vus and vus_max, each independently sorted by their timestamps
    all_points = points["vus"] + points["vus_max"]

    # Global time reference anchor from original k6 data bounds
    global_start = min(p[0] for p in all_points)
    global_end = max(p[0] for p in all_points)

    # Resolve active plot boundaries based on trimming inputs
    plot_start_rel = args.start_time if args.start_time is not None else 0.0
    plot_end_rel = args.end_time if args.end_time is not None else (global_end - global_start)

    # Convert relative plot window filters back to unix timestamps for filtering data files
    filter_start_unix = global_start + plot_start_rel
    filter_end_unix = global_start + plot_end_rel

    print(f"Global time range: {global_start:.2f} to {global_end:.2f} (duration: {global_end - global_start:.2f} seconds)")

    # Read and average CPU data within bounds
    cpu_x, cpu_avg = [], []
    with open(args.cpu, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = float(row.get("timestamp_unix") or 0)
            if filter_start_unix <= ts <= filter_end_unix:
                vals = [float(row[c]) for c in core_keys if row.get(c)]
                if vals:
                    cpu_x.append(ts - global_start) # Keep baseline to original run start
                    # obtaining the average of the selected cores for this timestamp
                    # print(f"len(vals)={len(vals)}, vals={vals}, average={sum(vals) / len(vals)}")  # Debug: Print CPU values and average
                    cpu_avg.append(sum(vals) / len(vals))

    # Parse VU arrays with structural relative timestamps (for max vus)
    vus_max_x, vus_max_y = [], []
    for t, v in points["vus_max"]:
        rel_t = t - global_start

        # adding the points if they are within the time bounds
        if plot_start_rel <= rel_t <= plot_end_rel:
            vus_max_x.append(rel_t)
            vus_max_y.append(v)

    # for vus being used
    vus_x, vus_y = [], []
    for t, v in points["vus"]:
        rel_t = t - global_start
        if plot_start_rel <= rel_t <= plot_end_rel:
            vus_x.append(rel_t)
            vus_y.append(v)

    # --- ACM Paper Styling Configuration --- (Gemini)
    plt.rcParams.update({
        'font.size': 10,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 8,
        'font.family': 'serif',
        'pdf.fonttype': 42,
        'ps.fonttype': 42
    })

    # Standard compact single-column dimensions
    fig, ax_cpu = plt.subplots(figsize=(3.33, 2.5), layout="constrained")
    ax_vus = ax_cpu.twinx()

    # Disable secondary layout grid artifacts to avoid overlapping line mesh patterns
    ax_cpu.grid(True, linestyle=":", alpha=0.6)
    ax_vus.grid(False)

    # Plot CPU stats (Shading + Line visibility matches print requirements)
    if cpu_x:
        ax_cpu.fill_between(cpu_x, cpu_avg, color="#d9ead3", alpha=0.4)
        ax_cpu.plot(cpu_x, cpu_avg, color="#38761d", linewidth=1.5, label="CPU Avg")

    # Plot VU timelines using step adjustments 
    if vus_max_x:
        ax_vus.step(vus_max_x, vus_max_y, where="post", color="#111111", linewidth=1.5, label="Allocated VUs")
    if vus_x:
        ax_vus.step(vus_x, vus_y, where="post", color="#cc0000", linewidth=1.5, linestyle="--", label="Active VUs")

    # Formatting Limits and Context labels
    ax_cpu.set_xlabel("Time (s)")
    ax_cpu.set_ylabel("CPU Utilization (%)")
    ax_vus.set_ylabel("Virtual Users")
    
    ax_cpu.set_xlim(plot_start_rel, plot_end_rel)
    ax_cpu.set_ylim(0, 105)
    ax_vus.set_ylim(bottom=0)

    # Consolidated Legend pinned cleanly outside top boundary framework
    lines_cpu, labels_cpu = ax_cpu.get_legend_handles_labels()
    lines_vus, labels_vus = ax_vus.get_legend_handles_labels()
    
    ax_cpu.legend(
        lines_cpu + lines_vus, 
        labels_cpu + labels_vus, 
        loc="upper center", 
        bbox_to_anchor=(0.5, 1.25), 
        ncol=3, 
        frameon=False
    )

    # Save target assets (PDF Vector format prioritized for TeX compilation environments)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save formatted files
    fig.savefig(output_path, format=output_path.suffix.lstrip('.'), dpi=300, bbox_inches="tight")
    print(f"Wrote plot: {output_path}")
    
    plt.close(fig)