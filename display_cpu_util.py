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
    fig, ax_cpu = plt.subplots(figsize=(12, 6))
    ax_workers = ax_cpu.twinx()

    core_cols = [f"core_{i}" for i in range(8) if f"core_{i}" in cpu_df.columns]
    colormap = plt.colormaps.get_cmap("tab10")
    # plotting the CPU utilization for each core
    for i, core in enumerate(core_cols):
        ax_cpu.plot(
            cpu_df["relative_time_s"],
            cpu_df[core],
            label=f"Core {core.split('_')[1]}",
            alpha=0.55,
            linewidth=1.1,
            color=colormap(i),
        )

    # plotting the workers used over time
    ax_workers.step(
        workers_df["relative_time_s"],
        workers_df["workers_used"],
        where="post",
        linewidth=3.0,
        color="black",
        linestyle="--",
        label="Workers used",
        zorder=10,
    )

    ax_cpu.set_title(f"CPU Utilization and Worker Growth - {rps} RPS Run {run}")
    ax_cpu.set_xlabel("Time (s)")
    ax_cpu.set_ylabel("Per-core CPU %")
    ax_workers.set_ylabel("Workers used")
    ax_cpu.set_ylim(0, 105)
    ax_cpu.grid(True, linestyle="--", alpha=0.6)

    cpu_lines, cpu_labels = ax_cpu.get_legend_handles_labels()
    worker_lines, worker_labels = ax_workers.get_legend_handles_labels()
    ax_cpu.legend(cpu_lines + worker_lines, cpu_labels + worker_labels, loc="upper left", fontsize=8)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot CPU utilization and Vegeta worker growth for one run.")
    parser.add_argument("--experiments-dir", type=Path, default=Path("phase-smooth-data/experiments_phase_queued_sut"))
    parser.add_argument("--rps", type=int, default=15000)
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cpu-set", type=str, required=True, help="CPU set label to include in plot title")
    args = parser.parse_args()

    # loading the CSV files
    run_dir = args.experiments_dir / f"rps_{args.rps}_{args.cpu_set}" / f"run_{args.run}"
    cpu_csv = run_dir / "cpu_utilization.csv"
    workers_csv = run_dir / "workers_timeline.csv"

    # loading the dataframes
    cpu_df = load_cpu(cpu_csv)
    workers_df = load_workers(workers_csv)

    print(cpu_df.head())
    print(workers_df.head())

    # plotting the data
    output = args.output or Path("results") / f"rps_{args.rps}_{args.cpu_set}" / f"run_{args.run}_cpu_workers.png"
    plot_cpu_and_workers(cpu_df, workers_df, output, args.rps, args.run)
    print(f"wrote plot: {output}")
