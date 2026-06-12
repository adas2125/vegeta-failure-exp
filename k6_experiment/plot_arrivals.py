import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# globals for the directories
ARRIVALS_DIR = Path("sut_arrivals")
LIMITED_EXP_DIR = ARRIVALS_DIR / "cpu_0_7"
FULL_EXP_DIR = ARRIVALS_DIR / "cpu_0_55"
RESULTS_DIR = Path("paper_figures")
DURATION_SECONDS = 60

def get_avg_rates(exp_dir, num_runs=10):
    """Helper function to extract and average the arrival rates for a given experiment directory."""
    all_rates = []

    # going from e.g. arrivals_1/arrivals.csv to arrivals_10/arrivals.csv
    for run_id in range(1, num_runs + 1):
        csv_filename = exp_dir / f"arrivals_{run_id}" / "arrivals.csv"
        df = pd.read_csv(csv_filename)

        # print(df.head())  # Debug: print the first few rows to verify the structure

        # converting Timestamp to datetime and sorting just in case
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df.sort_values('Timestamp')

        # print(df.head())  # Debug: print the first few rows after processing

        # Baseline to the first observed second
        start_second = df['Timestamp'].min().floor('s')

        # print(f"Run {run_id}: Start time baseline set to {start_second}")  # Debug: print the baseline time

        # Calculate Arrival Rate over 1-second intervals
        df_rate = df.set_index('Timestamp').resample('1s').size().reset_index(name='Arrivals_Per_Second')
        df_rate['Relative_Seconds'] = (df_rate['Timestamp'] - start_second).dt.total_seconds()
        
        # has the columns. relative_seconds and arrivals_per_second
        all_rates.append(df_rate[['Relative_Seconds', 'Arrivals_Per_Second']])

    # Combine all runs and calculate the average rate per relative second
    combined_rates = pd.concat(all_rates)

    # for each relative second, calculate the average arrival rate across all runs
    avg_rates = combined_rates.groupby('Relative_Seconds')['Arrivals_Per_Second'].mean().reset_index()

    # print(avg_rates.head())  # Debug: print the first few rows of the average rates

    return avg_rates

def plot_aggregate_rate(num_runs=10, start_time=0, end_time=DURATION_SECONDS):
    """Generated using Gemini for plotting"""

    # ACM Paper Styling Requirements
    plt.rcParams.update({
        'font.size': 10,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'font.family': 'serif',
        'pdf.fonttype': 42, # Forces Type 1 fonts
        'ps.fonttype': 42
    })

    # Single plot, adjusted height for one panel
    fig, ax = plt.subplots(figsize=(3.33, 2.5), layout="constrained")

    print("Processing Limited Run Data...")
    df_limited = get_avg_rates(LIMITED_EXP_DIR, num_runs)
    
    print("Processing Full Run Data...")
    df_full = get_avg_rates(FULL_EXP_DIR, num_runs)

    # Plot Full Run - Rate (req/s) within the trimmed window
    df_full_trimmed = df_full[(df_full['Relative_Seconds'] >= start_time) & (df_full['Relative_Seconds'] <= end_time)]
    ax.step(
        df_full_trimmed['Relative_Seconds'], 
        df_full_trimmed['Arrivals_Per_Second'], 
        where="post",
        linewidth=2.0, # Thicker line for print visibility
        linestyle='-', # Solid line
        color="#1f77b4", # Standard matplotlib blue
        label='Full (56 cores)'
    )

    # Plot Limited Run - Rate (req/s) within the trimmed window
    df_limited_trimmed = df_limited[(df_limited['Relative_Seconds'] >= start_time) & (df_limited['Relative_Seconds'] <= end_time)]
    ax.step(
        df_limited_trimmed['Relative_Seconds'], 
        df_limited_trimmed['Arrivals_Per_Second'], 
        where="post",
        linewidth=2.0, # Thicker line for print visibility
        linestyle='--', # Dashed line guarantees contrast in black-and-white print
        color="#d62728", # Contrasting red
        label='Limited (8 cores)'
    )

    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Rate (req/s)')
    ax.grid(True, linestyle=':', alpha=0.7)
    
    # Dynamically bound the X-axis to the trimmed window
    ax.set_xlim(start_time, end_time)
    ax.set_ylim(bottom=0)
    
    # Place legend up top, outside the plot bounds
    ax.legend(
        loc="upper center", 
        bbox_to_anchor=(0.5, 1.15), # Anchors legend slightly above the figure
        ncol=2, # Places labels side-by-side
        frameon=False
    )

    # create results directory if it doesn't exist
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_base = RESULTS_DIR / f"comparison_rate_avg_{start_time}_to_{end_time}"

    # Save outputs
    pdf_output = output_base.with_suffix('.pdf')
    fig.savefig(pdf_output, format='pdf', dpi=300, bbox_inches='tight')
    
    png_output = output_base.with_suffix('.png')
    fig.savefig(png_output, format='png', dpi=300, bbox_inches='tight')

    print(f"\nPlots saved successfully to {RESULTS_DIR}/ as {output_base.name}.pdf/.png")
    
    plt.close(fig)

if __name__ == "__main__":
    # plotting the aggregate rates across 10 runs, trimming the startup period
    plot_aggregate_rate(num_runs=10, start_time=0, end_time=50)