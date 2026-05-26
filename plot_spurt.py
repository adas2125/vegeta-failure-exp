import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import os

# User-defined constants, may need to be changed based on experimental setup
RPS = 20000
NUM_RUNS = 3
RESULTS_DIR = Path("results") / f"rps_{RPS}"
os.makedirs(RESULTS_DIR, exist_ok=True)

### Initialize Combined Plots Before the Loop ###
# Figure 1: Combined Cumulative Arrivals
plt.figure(1, figsize=(12, 6))
plt.ylabel('Cumulative Arrivals')
plt.title('Spurt Server Cumulative Arrivals & Phase Cycles (All Runs)')
plt.grid(True, linestyle='--', alpha=0.7)

# Figure 2: Combined Arrival Rate
plt.figure(2, figsize=(12, 8))
plt.ylabel('Arrival Rate (Req/Sec)')
plt.title('Load Generator Send Rate vs. Server Phase (All Runs)')
plt.grid(True, linestyle='--', alpha=0.7)

for run in range(1, NUM_RUNS + 1):
    print(f"Processing run {run} for RPS {RPS}...")
    EXPERIMENTS_DIR = Path("experiments_SUT") / f"rps_{RPS}" / f"run_{run}"

    # load the data
    df = pd.read_csv(EXPERIMENTS_DIR / 'spurt_data.csv')
    phase_df = pd.read_csv(EXPERIMENTS_DIR / 'phase_log.csv')

    # synchronize timelines between the spurt dataset recording requests and background phase log
    start_time = df['arrival_time_unix_ms'].min()

    # Convert both datasets to relative seconds starting from T=0
    df['relative_arrival_s'] = (df['arrival_time_unix_ms'] - start_time) / 1000.0
    phase_df['relative_time_s'] = (phase_df['timestamp_unix_ms'] - start_time) / 1000.0

    phase_label = 'Slow Phase' if run == 1 else "" 

    ### UPDATE COMBINED PLOT 1: Cumulative Arrivals ###
    plt.figure(1)
    plt.plot(df['relative_arrival_s'], range(1, len(df) + 1), linewidth=2, label=f'Run {run}')

    # marking the slow phase based on the first run's phase log for consistency across all runs
    plt.fill_between(
        phase_df['relative_time_s'], 
        0, 1, 
        where=(phase_df['phase'] == 'slow'), 
        color='red', 
        alpha=0.10, 
        transform=plt.gca().get_xaxis_transform(),
        label=phase_label
    )

    ### CREATE & SAVE INDIVIDUAL PLOT 1 for a specific run ###
    plt.figure(3, figsize=(12, 6))
    # length of df is used to create a cumulative count for the y-axis (since one arrival per row)
    plt.plot(df['relative_arrival_s'], range(1, len(df) + 1), color='blue', linewidth=2)
    plt.ylabel('Cumulative Arrivals')
    plt.title(f'Spurt Server Cumulative Arrivals & Phase Cycles - Run {run}')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.fill_between(
        phase_df['relative_time_s'], 
        0, 1, 
        where=(phase_df['phase'] == 'slow'), 
        color='red', 
        alpha=0.15, 
        transform=plt.gca().get_xaxis_transform() 
    )
    plt.xlim(0, 35)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / f'spurt_server_plot_cum_run_{run}.png', dpi=300)
    plt.close(3) # Close to free memory

    ### PREPARE RATE DATA (Used for both Combined & Individual) ###
    df['time_bin'] = df['relative_arrival_s'].astype(int)
    rate_df = df.groupby('time_bin').size().reset_index(name='count')
    min_bin = rate_df['time_bin'].min()
    max_bin = rate_df['time_bin'].max()
    all_bins = pd.DataFrame({'time_bin': range(min_bin, max_bin + 1)})
    rate_df = pd.merge(all_bins, rate_df, on='time_bin', how='left').fillna({'count': 0})
    # The 'count' column represents the number of arrivals in each second, which is equivalent to the arrival rate in requests per second.
    rate_df['rate_req_sec'] = rate_df['count']

    ### UPDATE COMBINED PLOT 2: Arrival Rate ###
    plt.figure(2)
    plt.plot(rate_df['time_bin'], rate_df['rate_req_sec'], linewidth=2, label=f'Run {run}')
    plt.fill_between(
        phase_df['relative_time_s'], 
        0, 1, 
        where=(phase_df['phase'] == 'slow'), 
        color='red', 
        alpha=0.10, 
        transform=plt.gca().get_xaxis_transform(),
        label=phase_label
    )

    ### CREATE & SAVE INDIVIDUAL PLOT 2 for a specific run ###
    plt.figure(4, figsize=(12, 8))
    plt.plot(rate_df['time_bin'], rate_df['rate_req_sec'], color='blue', linewidth=2)
    plt.ylabel('Arrival Rate (Req/Sec)')
    plt.title(f'Load Generator Send Rate vs. Server Phase - Run {run}')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.fill_between(
        phase_df['relative_time_s'], 
        0, 1, 
        where=(phase_df['phase'] == 'slow'), 
        color='red', 
        alpha=0.15, 
        transform=plt.gca().get_xaxis_transform() 
    )
    plt.xlim(0, 35)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / f'spurt_server_plot_rate_run_{run}.png', dpi=300)
    plt.close(4) # Close to free memory

### Finalize and Save Combined Plots After the Loop ###
# Finalize Combined Plot 1
plt.figure(1)
plt.xlim(0, 35)
plt.legend(loc='lower right') 
plt.tight_layout()
plt.savefig(RESULTS_DIR / 'spurt_server_plot_cum_all_runs.png', dpi=300)
plt.close(1)

# Finalize Combined Plot 2
plt.figure(2)
plt.xlim(0, 35)
plt.legend(loc='lower right') 
plt.tight_layout()
plt.savefig(RESULTS_DIR / 'spurt_server_plot_rate_all_runs.png', dpi=300)
plt.close(2)

print("Individual and combined plots generated successfully.")
