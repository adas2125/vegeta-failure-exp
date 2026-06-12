import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

def load_cpu(path):
    df = pd.read_csv(path)
    start_time = df["timestamp_unix"].min()
    df["relative_time_s"] = df["timestamp_unix"] - start_time
    return df

def load_workers(path):
    df = pd.read_csv(path)
    df["relative_time_s"] = df["elapsed_ms"] / 1000.0
    return df

def plot_cpu_and_workers(cpu_df, workers_df, output_path, rps, run):
    # ACM Paper Styling Requirements
    plt.rcParams.update({
        'font.size': 10,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'font.family': 'serif',
        'pdf.fonttype': 42, # Forces Type 1 fonts (Required by ACM)
        'ps.fonttype': 42
    })

    # 3.33 inches is the exact width of a single column in the ACM sigconf template
    fig, ax_cpu = plt.subplots(figsize=(3.33, 2.3))
    ax_workers = ax_cpu.twinx()

    core_cols = [f"core_{i}" for i in range(8) if f"core_{i}" in cpu_df.columns]
    
    # Calculate the average across all selected cores
    cpu_df["avg_cpu"] = cpu_df[core_cols].mean(axis=1)

    ax_cpu.plot(
        cpu_df["relative_time_s"],
        cpu_df["avg_cpu"],
        label="Avg CPU",
        linewidth=1.5,
        color="#1f77b4", 
    )

    ax_workers.step(
        workers_df["relative_time_s"],
        workers_df["workers_used"],
        where="post",
        linewidth=1.5,
        color="#d62728", 
        linestyle="--",
        label="Workers",
    )
    
    ax_cpu.set_xlabel("Time (s)")
    ax_cpu.set_ylabel("Avg CPU (%)")
    ax_workers.set_ylabel("Workers Used")
    
    ax_cpu.set_ylim(0, 105)
    ax_cpu.grid(True, linestyle=":", alpha=0.7)

    # --- UPDATED LEGEND LOGIC ---
    # Combines the legends and places them above the plot horizontally
    cpu_lines, cpu_labels = ax_cpu.get_legend_handles_labels()
    worker_lines, worker_labels = ax_workers.get_legend_handles_labels()
    
    ax_cpu.legend(
        cpu_lines + worker_lines, 
        cpu_labels + worker_labels, 
        loc="lower center",           # Anchor point of the legend box
        bbox_to_anchor=(0.5, 1.02),   # Push it perfectly above the top axis line
        ncol=2,                       # Make it a horizontal 2-column layout
        frameon=False                 # Keep the clean, frameless look
    )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as PDF for vector rendering
    pdf_output = output_path.with_suffix('.pdf')
    fig.savefig(pdf_output, format='pdf', dpi=300, bbox_inches="tight")
    
    # Save as PNG for quick local viewing
    png_output = output_path.with_suffix('.png')
    fig.savefig(png_output, format='png', dpi=300, bbox_inches="tight")
    
    plt.close(fig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot Average CPU utilization and Vegeta worker growth.")
    parser.add_argument("--experiments-dir", type=Path, default=Path("phase-smooth-data/experiments_phase_queued_sut"))
    parser.add_argument("--rps", type=int, default=15000)
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cpu-set", type=str, required=True, help="CPU set label to include in plot title")
    args = parser.parse_args()

    run_dir = args.experiments_dir / f"rps_{args.rps}_{args.cpu_set}" / f"run_{args.run}"
    cpu_csv = run_dir / "cpu_utilization.csv"
    workers_csv = run_dir / "workers_timeline.csv"

    cpu_df = load_cpu(cpu_csv)
    workers_df = load_workers(workers_csv)

    # Base output path (extensions handled inside the function)
    output = args.output or Path("results") / f"rps_{args.rps}_{args.cpu_set}" / f"run_{args.run}_cpu_workers"
    
    plot_cpu_and_workers(cpu_df, workers_df, output, args.rps, args.run)
    
    print(f"Wrote plot: {output.with_suffix('.pdf')}")
    print(f"Wrote plot: {output.with_suffix('.png')}")