from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# User-defined arguments; may need to be adjusted based on your experiment setup
EXPERIMENTS_DIR = Path('experiments')
RESULTS_DIR = Path('results')
RPS = 5000
RUNS = 3

for run in range(1, RUNS + 1):
    # Load the data
    cpu_csv = EXPERIMENTS_DIR / f'rps_{RPS}/run_{run}/cpu_utilization.csv'
    memory_csv = EXPERIMENTS_DIR / f'rps_{RPS}/run_{run}/memory_utilization.csv'
    df = pd.read_csv(cpu_csv)

    # Convert Unix timestamps to relative seconds (starting at T=0)
    start_time = df['timestamp_unix'].min()
    df['relative_time_s'] = df['timestamp_unix'] - start_time

    # Identify only the first 8 core columns
    core_cols = [f'core_{i}' for i in range(8) if f'core_{i}' in df.columns]

    memory_df = pd.read_csv(memory_csv) if memory_csv.exists() else None
    if memory_df is not None:
        memory_df['relative_time_s'] = memory_df['timestamp_unix'] - start_time

    subplot_count = 2 if memory_df is not None else 1
    fig, axes = plt.subplots(subplot_count, 1, figsize=(12, 8), sharex=True)
    if subplot_count == 1:
        axes = [axes]
    ax_cpu = axes[0]

    # --- Per-Core CPU ---
    # We loop through and plot each core.
    # Using a colormap ensures we get distinct colors for up to 8-16 cores.
    colormap = plt.cm.get_cmap('tab10', len(core_cols))

    for i, core in enumerate(core_cols):
        ax_cpu.plot(
            df['relative_time_s'],
            df[core],
            label=f"Core {core.split('_')[1]}",
            alpha=0.7,
            linewidth=1.5,
            color=colormap(i)
        )

    ax_cpu.set_ylabel('Per-Core CPU %')
    ax_cpu.set_ylim(0, 105)
    ax_cpu.grid(True, linestyle='--', alpha=0.7)
    ax_cpu.legend(loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0.)

    if memory_df is not None:
        ax_mem = axes[1]
        ax_mem.plot(
            memory_df['relative_time_s'],
            memory_df['rss_mb'],
            label='RSS MB',
            linewidth=1.8,
            color='tab:blue'
        )
        ax_mem.plot(
            memory_df['relative_time_s'],
            memory_df['vms_mb'],
            label='VMS MB',
            linewidth=1.8,
            color='tab:orange'
        )
        ax_mem.set_ylabel('Memory MB')
        ax_mem.grid(True, linestyle='--', alpha=0.7)
        ax_mem.legend(loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0.)

    axes[-1].set_xlabel('Time (Seconds)')
    plt.tight_layout()

    # save the figure
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(RESULTS_DIR / f'cpu_utilization_plot_run_{run}.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
