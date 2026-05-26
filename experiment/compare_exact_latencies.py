import argparse
import csv
import math
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# defining the range of percentiles
SUMMARY_PERCENTILES = [pct for pct in np.arange(0.0, 1.0, 0.01)]

def percentile(sorted_values, pct):
    """Obtaining the value at a given percentile from a sorted list of values."""
    idx = math.ceil(pct * len(sorted_values)) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]

def rps_value(path):
    return int(path.name.removeprefix("rps_"))

def run_value(path):
    return int(path.name.removeprefix("run_"))

def parse_duration_ms(value):
    """Convert a duration string with units (e.g., "10ms", "4s") to milliseconds."""
    units = [
        ("ns", 1 / 1_000_000),
        ("us", 1 / 1_000),
        ("ms", 1),
        ("s", 1_000),
        ("m", 60_000),
        ("h", 3_600_000),
    ]
    value = value.strip()
    for suffix, multiplier in units:
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value)

def phase_delay_ms(elapsed_ms, fast_delay_ms, slow_delay_ms, cycle_ms, spike_ms):
    """cycle logic for the spurt SUT: if we are in the slow phase, return slow_delay_ms, otherwise return fast_delay_ms"""
    return slow_delay_ms if elapsed_ms % cycle_ms >= cycle_ms - spike_ms else fast_delay_ms

def in_window(elapsed_seconds, start_seconds, end_seconds):
    """Check if the elapsed time is within the specified start and end seconds window."""
    return elapsed_seconds >= start_seconds and elapsed_seconds < end_seconds

def filename_number(value):
    """helper to window_suffix function"""
    return f"{value:g}".replace("-", "m").replace(".", "p")

def window_suffix(start_seconds, end_seconds):
    """for filenames"""
    start = f"{filename_number(start_seconds)}s"
    end = f"{filename_number(end_seconds)}s"
    return f"_{start}_to_{end}"

def load_lg_latencies_ms(path, start_seconds, end_seconds):
    """Obtains the latency measurements and timestamps from the LG results.csv file within a given window"""
    with path.open(newline="") as f:
        samples = [(int(row[0]) / 1_000_000_000, int(row[2]) / 1_000_000) for row in csv.reader(f)]
    base_timestamp = min(timestamp for timestamp, _ in samples)
    return sorted(
        latency_ms
        for timestamp, latency_ms in samples
        if in_window(timestamp - base_timestamp, start_seconds, end_seconds)
    )

def load_spurt_arrivals_ms(path):
    """Obtaining the arrival times of the spurt SUT requests in milliseconds from the CSV file."""
    with path.open(newline="") as f:
        return sorted(int(row["arrival_time_unix_ms"]) for row in csv.DictReader(f))

def ideal_elapsed_ms_values(rps, start_seconds, end_seconds):
    """Generates ideal request arrival times in (ms)"""
    # loading the first and last index based on the start and end seconds, using the RPS value
    first_idx, last_idx = math.ceil(start_seconds * rps), math.ceil(end_seconds * rps) - 1
    # yielding the arrival times in milliseconds for the ideal open-loop SUT
    for i in range(first_idx, last_idx + 1):
        yield i * 1_000 / rps   # e.g. if RPS = 15K, arrival times are 0, 0.0667, 0.1333, 0.2, ... ms

def reconstruct_sut_latencies_ms(
    path, rps, fast_delay_ms, slow_delay_ms,
    cycle_ms, spike_ms, start_seconds, end_seconds,
):
    """
    Reconstructing the SUT latencies based on the ideal open-loop schedule and the spurt SUT phase cycle.
    The spurt SUT starts its phase cycle when the first request arrives. For ideal open-loop ground truth, 
    use that same zero point and keep only ideal schedule points inside the requested elapsed-time window.
    """
    arrivals = load_spurt_arrivals_ms(path)
    # generating the ideal elapsed times in milliseconds for the given RPS within the specified window
    elapsed_values = ideal_elapsed_ms_values(rps, start_seconds, end_seconds)
    # returns the GT latencies on the fixed SUT latency schedule for each arrival time; sorted for percentile calculations
    return sorted(phase_delay_ms(ms, fast_delay_ms, slow_delay_ms, cycle_ms, spike_ms) for ms in elapsed_values)

def print_summary(rps, runs):
    """Obtaining the percentile values for both LG and SUT"""
    print(f"\nrps {rps}")
    print(f"{'run':>8} {'n_lg':>10} {'n_sut':>10} {'percentile':>10} {'lg_exact':>12} {'sut_truth':>12} {'lg-sut':>12}")
    for run_name, lg_values, sut_values in runs:
        for pct in SUMMARY_PERCENTILES:
            lg = percentile(lg_values, pct)
            sut = percentile(sut_values, pct)
            print(f"{run_name:>8} {len(lg_values):10d} {len(sut_values):10d} p{pct * 100:<9g} {lg:12.3f} {sut:12.3f} {lg - sut:12.3f}")

def write_latency_plot(path, exp_latency_path, rps, runs):
    """Plotting the LG measured latencies and the reconstructed SUT latencies"""
    fig, ax = plt.subplots(figsize=(10, 6))

    plot_percentiles, x = load_plot_percentiles(exp_latency_path)
    for run_name, lg_values, sut_values in runs:
        lg_y = [percentile(lg_values, pct) for pct in plot_percentiles]
        sut_y = [percentile(sut_values, pct) for pct in plot_percentiles]
        ax.plot(x, lg_y, linewidth=2.0, label=f"LG measured {run_name}")
        ax.plot(x, sut_y, linestyle="--", linewidth=1.8, label=f"SUT reconstructed {run_name}")

    ax.set_title(f"LG Latency vs Reconstructed SUT Distribution - {rps} RPS")
    ax.set_xlabel("Percentile")
    ax.set_ylabel("Latency (ms)")
    ax.set_xscale("log")
    ax.set_xlim(left=1)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")

    x_ticks = [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000]
    x_labels = ["0%", "90%", "99%", "99.9%", "99.99%", "99.999%", "99.9999%"]
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)

    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

def load_plot_percentiles(path):
    """Loads the percentiles and corresponding 1/(1-p) values from the hdrplot.tsv file for plotting."""
    with path.open() as f:
        header = f.readline().split()
        rows = [dict(zip(header, line.split())) for line in f if line.strip()]
    percentiles = sorted(float(row["Percentile"]) for row in rows)
    inv_values = sorted(float(row["1/(1-Percentile)"]) for row in rows)
    return percentiles, inv_values
        
if __name__ == "__main__":
    # Setting up the arguments
    parser = argparse.ArgumentParser(
        description="Compare LG measured latencies with a reconstructed spurt SUT latency distribution."
    )
    parser.add_argument("--lg-dir", type=Path, default=Path("vegeta_pitfalls/experiments"))
    parser.add_argument("--sut-dir", type=Path, default=Path("vegeta_pitfalls/experiments_SUT"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))

    # these arguments should match the setup of the spurt server exactly
    parser.add_argument("--fast-delay", default="10ms", help="spurt fast delay, e.g. 10ms")
    parser.add_argument("--slow-delay", default="4000ms", help="spurt slow delay, e.g. 4000ms")
    parser.add_argument("--cycle", default="4s", help="spurt phase cycle duration, e.g. 4s")
    parser.add_argument("--spike", default="1500ms", help="slow phase duration within each cycle, e.g. 1500ms")

    # where to start the analysis from (in my slides, we start from earlier windows)
    parser.add_argument(
        "--start-seconds",
        type=float,
        help="start of the elapsed-time window, measured from the first request in each run",
        required=True
    )
    parser.add_argument(
        "--end-seconds",
        type=float,
        help="end of the elapsed-time window, measured from the first request in each run",
        required=True
    )
    args = parser.parse_args()

    # obtaining the values in milliseconds for the spurt SUT phase cycle and delays
    fast_delay_ms = parse_duration_ms(args.fast_delay)
    slow_delay_ms = parse_duration_ms(args.slow_delay)
    cycle_ms = parse_duration_ms(args.cycle)
    spike_ms = parse_duration_ms(args.spike)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for lg_rps_dir in sorted(args.lg_dir.glob("rps_*"), key=rps_value):
        # obtaining the rps value from the directory name, e.g. "rps_15000" -> 15000
        rps = rps_value(lg_rps_dir)

        if rps == 5000:
            print(f"skipping rps {rps} because the SUT was not run for this RPS value")
            continue

        # now we have both the LG and SUT directories for this RPS value
        sut_rps_dir = args.sut_dir / lg_rps_dir.name
        runs = []
        for run_dir in sorted(lg_rps_dir.glob("run_*"), key=run_value):
            # loading the measured results.csv between the start and end seconds for the LG
            lg_values = load_lg_latencies_ms(run_dir / "results.csv", args.start_seconds, args.end_seconds)

            # reconstruct the GT SUT latencies
            sut_values = reconstruct_sut_latencies_ms(
                sut_rps_dir / run_dir.name / "spurt_data.csv",
                rps,
                fast_delay_ms,
                slow_delay_ms,
                cycle_ms,
                spike_ms,
                args.start_seconds,
                args.end_seconds,
            )

            # appending in the format the plot function expects: (run_name, lg_values, sut_values)
            runs.append((run_dir.name, lg_values, sut_values))

        print_summary(rps, runs)
        plot_path = args.output_dir / f"exact_latency_rps_{rps}{window_suffix(args.start_seconds, args.end_seconds)}.png"
        exp_latency_path = args.lg_dir / f"rps_{rps}" / f"run_1" / "hdrplot.tsv"
        write_latency_plot(plot_path, exp_latency_path, rps, runs)
        print(f"wrote plot: {plot_path}")
