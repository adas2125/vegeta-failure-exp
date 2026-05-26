import argparse
import json
import math
from statistics import mean
from pathlib import Path
import matplotlib.pyplot as plt

SUMMARY_PERCENTILES = [0.50, 0.90, 0.95, 0.99, 0.999]

def percentile(sorted_values, p):
    """Obtains the percentile from a list of sorted values"""
    idx = math.ceil(p * len(sorted_values)) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]

def rps_value(path):
    """Extracts the RPS value from a path like 'rps_10000'"""
    return int(path.name.removeprefix("rps_"))

def run_value(path):
    """Extracts the run value from a path like 'run_3'"""
    return int(path.name.removeprefix("run_"))

def load_hdrplot_points(path):
    points = []
    with path.open() as f:
        next(f, None)
        for line in f:
            fields = line.split()
            if len(fields) < 4:
                continue
            latency_ms = float(fields[0])
            pct = float(fields[1])
            one_by = float(fields[3])
            points.append((pct, latency_ms, one_by))
    points.sort()
    return points

def load_sut_latencies(path):
    """Loads the SUT latencies from a JSONL file and returns them as a sorted list of floats"""
    values = []
    # loading the SUT latencies and sorting them for percentile calculations
    with path.open() as f:
        for line in f:
            if line.strip():
                values.append(float(json.loads(line)["server_latency_ms"]))
    values.sort()
    return values

def hdr_value_at(points, pct):
    if pct <= points[0][0]:
        return points[0][1]

    for (p0, v0, _), (p1, v1, _) in zip(points, points[1:]):
        if pct <= p1:
            if p1 == p0:
                return v1
            ratio = (pct - p0) / (p1 - p0)
            return v0 + ratio * (v1 - v0)

    return points[-1][1]

def sut_points_for_hdr_percentiles(sut_values, hdr_points):
    return [(pct, percentile(sut_values, pct), one_by) for pct, _, one_by in hdr_points]

def percentile_curve_wasserstein_ms(hdr_points, sut_values):
    gaps = []
    for pct, latency, _ in hdr_points:
        gaps.append((pct, abs(latency - percentile(sut_values, pct))))

    distance = 0.0
    for (p0, gap0), (p1, gap1) in zip(gaps, gaps[1:]):
        distance += (p1 - p0) * (gap0 + gap1) / 2
    return distance

def print_summary(rps, runs):
    """For a given RPS, prints a summary of the HDR percentiles and SUT latencies across all runs"""
    print(f"\nrps {rps}")
    print(f"{'percentile':>10} {'lg_avg':>12} {'sut_avg':>12}")

    # printing the averages of the HDR percentiles and SUT latencies across all runs
    for pct in SUMMARY_PERCENTILES:
        # assumes runs is a list of tuples (run_name, hdr_points, sut_values)
        lg_avg = mean(hdr_value_at(points, pct) for _, points, _ in runs)
        sut_avg = mean(percentile(sut_values, pct) for _, _, sut_values in runs)
        print(f"p{pct * 100:g} {lg_avg:12.3f} {sut_avg:12.3f}")

    # calculating the Wasserstein distance between the HDR percentile curve and the SUT latency curve for each run
    distances = [(run_name, percentile_curve_wasserstein_ms(points, sut_values)) for run_name, points, sut_values in runs]
    print("wasserstein_ms")
    for run_name, distance in distances:
        print(f"{run_name:>10} {distance:12.3f}")
    print(f"{'avg':>10} {mean(distance for _, distance in distances):12.3f}")

def write_latency_plot(path, rps, runs):
    fig, ax = plt.subplots(figsize=(10, 6))

    for run_name, points, sut_values in runs:

        # plotting the HDR percentile curve
        x = [one_by for _, _, one_by in points]
        y = [latency for _, latency, _ in points]
        ax.plot(x, y, linewidth=2.0, label=f"LG {run_name}")

        # plotting the SUT latency curve
        sut_points = sut_points_for_hdr_percentiles(sut_values, points)
        sut_x = [one_by for _, _, one_by in sut_points]
        sut_y = [latency for _, latency, _ in sut_points]
        ax.plot(sut_x, sut_y, linestyle="--", linewidth=1.8, label=f"SUT {run_name}")

    ax.set_title(f"Latency by Percentile - {rps} RPS")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare LG HDR percentiles with SUT request latencies across experiments.")
    parser.add_argument("--lg-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--sut-dir", type=Path, default=Path("experiments_SUT"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()

    # create output directory if it doesn't exist
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for lg_rps_dir in sorted(args.lg_dir.glob("rps_*"), key=rps_value):
        rps = rps_value(lg_rps_dir)
        sut_rps_dir = args.sut_dir / lg_rps_dir.name

        runs = []
        for run_dir in sorted(lg_rps_dir.glob("run_*"), key=run_value):
            sut_run_dir = sut_rps_dir / run_dir.name

            # loading the paired HDR plot points and SUT latencies for this run
            runs.append((
                run_dir.name,
                load_hdrplot_points(run_dir / "hdrplot.tsv"),
                load_sut_latencies(sut_run_dir / "requests.jsonl"),
            ))

        print_summary(rps, runs)
        
        # creating the plot
        plot_path = args.output_dir / f"latency_rps_{rps}.png"
        write_latency_plot(plot_path, rps, runs)
        print(f"wrote plot: {plot_path}")
