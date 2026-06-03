import pandas as pd
import matplotlib.pyplot as plt
import os

EXP_DIR = "cpu_0_7"
RESULTS_DIR = "results"

def plot_all_arrivals(num_runs=5):
    # Set up the figure and subplots ONCE before the loop
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # Set the overarching title to the experiment directory name
    fig.suptitle(EXP_DIR, fontsize=16, fontweight='bold')

    for run_id in range(1, num_runs + 1):
        csv_filename = f"{EXP_DIR}/arrivals_{run_id}/arrivals.csv"
        print(f"Processing Run {run_id}...")
        
        try:
            # Read the CSV and parse precise timestamps
            df = pd.read_csv(csv_filename)
        except FileNotFoundError:
            print(f"  -> File {csv_filename} not found. Skipping.")
            continue

        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

        # Sort to guarantee chronological order
        df = df.sort_values('Timestamp')

        # Use relative seconds on the x-axis, where 0 is the first observed second
        start_second = df['Timestamp'].min().floor('s')
        df['Relative_Seconds'] = (df['Timestamp'] - start_second).dt.total_seconds()

        # Calculate Cumulative Arrivals based on row sequence
        df['Cumulative_Arrivals'] = range(1, len(df) + 1)

        # Calculate Arrival Rate over 1-second intervals
        df_rate = df.set_index('Timestamp').resample('1s').size().reset_index(name='Arrivals_Per_Second')
        df_rate['Relative_Seconds'] = (df_rate['Timestamp'] - start_second).dt.total_seconds()

        # --- Top Panel: Cumulative Arrivals ---
        # Note: 'color' is removed so matplotlib automatically cycles through colors
        ax1.plot(df['Relative_Seconds'], df['Cumulative_Arrivals'], linewidth=2, label=f'Run {run_id}')

        # --- Bottom Panel: Arrival Rate (Arrivals per Second) ---
        ax2.plot(df_rate['Relative_Seconds'], df_rate['Arrivals_Per_Second'], linewidth=2, label=f'Run {run_id}')

    # --- Formatting Top Panel ---
    ax1.set_title('Request Arrivals Over Time')
    ax1.set_ylabel('Total Arrivals')
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend(loc="upper left")

    # --- Formatting Bottom Panel ---
    ax2.set_title('Arrival Rate')
    ax2.set_xlabel('Relative Time (s)')
    ax2.set_ylabel('Arrivals per Second')
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend(loc="upper left")

    # Adjust layout so labels don't overlap with the suptitle
    plt.tight_layout()

    # Save and display the plot
    output_filename = f"{RESULTS_DIR}/{EXP_DIR}_arrivals_plot.png"
    plt.savefig(output_filename, dpi=300)
    print(f"\nPlot saved as {output_filename}")
    
    plt.show()

if __name__ == "__main__":
    plot_all_arrivals(5)