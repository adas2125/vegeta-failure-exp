#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path
import matplotlib.pyplot as plt

from phase_generate_queued_sut_cdf import (
    DEFAULT_PHASE_SCHEDULE,
    parse_duration_ms,
    parse_phase_schedule,
    percentile,
    simulate_ground_truth,
    filename_number,
    SUMMARY_PERCENTILES,
)

CSV_COLUMNS = [
    "timestamp_ns",
    "status",
    "latency_ns",
    "bytes_out",
    "bytes_in",
    "error",
    "body",
    "attack",
    "seq",
    "method",
    "url",
    "headers",
]

# column names in hdrplot.tsv output from Vegeta
HDR_VALUE_COLUMN = "Value(ms)"
HDR_PERCENTILE_COLUMN = "Percentile"
HDR_INV_PERCENTILE_COLUMN = "1/(1-Percentile)"

def load_run_latencies(results_csv):
    latencies, statuses = [], {}
    with results_csv.open(newline="") as f:
        for row in csv.reader(f):
            if len(row) != len(CSV_COLUMNS):
                continue
            status = row[1]
            statuses[status] = statuses.get(status, 0) + 1
            if status != "200":
                continue
            # add the latencies in ms to the list
            latencies.append(float(row[2]) / 1_000_000.0)
    return sorted(latencies), statuses

def load_hdrplot_points(hdrplot_tsv):
    """Load the points from a Vegeta hdrplot.tsv file, returning a list of (percentile, latency_ms, 1/(1-percentile)) tuples."""
    points = []
    with hdrplot_tsv.open() as f:
        header = f.readline().split()
        for line in f:
            if not line.strip():
                continue
            row = dict(zip(header, line.split()))
            points.append((
                float(row[HDR_PERCENTILE_COLUMN]),
                float(row[HDR_VALUE_COLUMN]),
                float(row[HDR_INV_PERCENTILE_COLUMN]),
            ))
    points.sort(key=lambda point: point[0])
    return points

def percentile_curve(sorted_values, percentiles):
    return [percentile(sorted_values, pct) for pct in percentiles]

def format_latency_axis(ax):
    ax.set_xscale("log")
    ax.set_xlim(left=1)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")
    ax.set_xticks([1, 10, 100, 1_000, 10_000, 100_000, 1_000_000])
    ax.set_xticklabels(["0%", "90%", "99%", "99.9%", "99.99%", "99.999%", "99.9999%"])

def write_plot(path, truth_values_by_name, run_values_by_name, hdr_points_by_name, rps, concurrency):
    """Plots the truth and measured latency distributions on a 3-row plot, saving to the given path.
    Uses the hdr_points_by_name to obtain percentiles and 1/(1-percentile) values for the x-axis."""
    # set up a 3-row plot: top row for truth, middle row for measured, bottom row for combined
    fig, axes = plt.subplots(3, 1, figsize=(11, 13), sharex=True, sharey=True)
    truth_ax, measured_ax, combined_ax = axes

    for (truth_name, truth_values), (_, hdr_points) in zip(truth_values_by_name, hdr_points_by_name):
        
        # obtaining the percentiles and 1/(1-percentile) values from the hdr_points
        percentiles = [pct for pct, _, _ in hdr_points]
        x = [one_by for _, _, one_by in hdr_points]

        # drawing the the truth curve for the truth points
        y = percentile_curve(truth_values, percentiles)

        # plotting on the truth_ax and combined_ax with dashed lines for the truth curve
        truth_ax.plot(x, y, linewidth=2.2, linestyle="--", label=truth_name)
        combined_ax.plot(x, y, linewidth=2.2, linestyle="--", label=truth_name)

    for (run_name, run_values), (_, hdr_points) in zip(run_values_by_name, hdr_points_by_name):
        percentiles = [pct for pct, _, _ in hdr_points]
        x = [one_by for _, _, one_by in hdr_points]

        # getting the percentiles for the actual run values
        y = percentile_curve(run_values, percentiles)

        # plotting on the measured_ax and combined_ax with solid lines for the actual run values
        measured_ax.plot(x, y, linewidth=2.0, label=run_name)
        combined_ax.plot(x, y, linewidth=2.0, label=run_name)

    # figure labels
    fig.suptitle(f"Phase Queued SUT CSV Latency Distribution - {rps:g} RPS, C={concurrency}")
    for ax, title in zip(axes, ["Ideal Ground Truth", "Measured Vegeta results.csv", "Combined"]):
        ax.set_title(title)
        ax.set_ylabel("Latency (ms)")
        format_latency_axis(ax)
    axes[-1].set_xlabel("Percentile")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(path, dpi=300)
    plt.close(fig)

def write_hdr_plot(path, truth_values_by_name, hdr_points_by_name, rps, concurrency, combined_only=True):
    if combined_only:
        fig, ax = plt.subplots(figsize=(11, 6))
        for (truth_name, truth_values), (_, hdr_points) in zip(truth_values_by_name, hdr_points_by_name):
            percentiles = [pct for pct, _, _ in hdr_points]
            x = [one_by for _, _, one_by in hdr_points]
            ax.plot(x, percentile_curve(truth_values, percentiles), linewidth=2.2, linestyle="--", label=truth_name)

        for hdr_name, hdr_points in hdr_points_by_name:
            x = [one_by for _, _, one_by in hdr_points]
            y = [latency_ms for _, latency_ms, _ in hdr_points]
            ax.plot(x, y, linewidth=2.0, label=hdr_name)

        ax.set_title(f"Phase Queued SUT HDR Latency Plot - {rps:g} RPS, C={concurrency}")
        ax.set_ylabel("Latency (ms)")
        format_latency_axis(ax)
        ax.set_xlabel("Percentile")
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        fig.savefig(path, dpi=300)
        plt.close(fig)
    else:
        fig, axes = plt.subplots(3, 1, figsize=(11, 13), sharex=True, sharey=True)
        truth_ax, measured_ax, combined_ax = axes

        for (truth_name, truth_values), (_, hdr_points) in zip(truth_values_by_name, hdr_points_by_name):
            percentiles = [pct for pct, _, _ in hdr_points]
            x = [one_by for _, _, one_by in hdr_points]
            truth_ax.plot(x, percentile_curve(truth_values, percentiles), linewidth=2.2, linestyle="--", label=truth_name)
            combined_ax.plot(x, percentile_curve(truth_values, percentiles), linewidth=2.2, linestyle="--", label=truth_name)

        for hdr_name, hdr_points in hdr_points_by_name:
            x = [one_by for _, _, one_by in hdr_points]
            y = [latency_ms for _, latency_ms, _ in hdr_points]

            # plotting the measured HDR points on the measured_ax and combined_ax with solid lines
            measured_ax.plot(x, y, linewidth=2.0, label=hdr_name)
            combined_ax.plot(x, y, linewidth=2.0, label=hdr_name)

        fig.suptitle(f"Phase Queued SUT HDR Latency Plot - {rps:g} RPS, C={concurrency}")
        for ax, title in zip(axes, ["Ideal Ground Truth", "Measured Vegeta HDR", "Combined"]):
            ax.set_title(title)
            ax.set_ylabel("Latency (ms)")
            format_latency_axis(ax)
        axes[-1].set_xlabel("Percentile")
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        fig.savefig(path, dpi=300)
        plt.close(fig)

def write_hdrplot_hdr_and_original(path, run_values_by_name, hdr_points_by_name, rps, concurrency, combined_only=False):
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, sharey=True)

    # plotting the measured HDR points on the first axis
    measured_ax, original_ax, combined_ax = axes
    for hdr_name, hdr_points in hdr_points_by_name:
        x = [one_by for _, _, one_by in hdr_points]
        y = [latency_ms for _, latency_ms, _ in hdr_points]
        measured_ax.plot(x, y, linewidth=2.0, label=hdr_name)
        combined_ax.plot(x, y, linewidth=2.0, label=hdr_name)
    
    # plotting the measured original points on the second axis
    for (run_name, run_values), (_, hdr_points) in zip(run_values_by_name, hdr_points_by_name):
        percentiles = [pct for pct, _, _ in hdr_points]
        x = [one_by for _, _, one_by in hdr_points]
        y = percentile_curve(run_values, percentiles)
        original_ax.plot(x, y, linewidth=2.0, label=run_name)
        combined_ax.plot(x, y, linewidth=2.0, label=run_name)
    
    if combined_only:
        print("Only showing combined HDR vs Original plot")
        axes[0].remove()
        axes[1].remove()
        combined_ax.set_title("Measured Vegeta HDR vs Original Latency Plot")
    fig.suptitle(f"Phase Queued SUT HDR vs Original Latency Plot - {rps:g} RPS, C={concurrency}")
    if combined_only:
        axes_to_format = [combined_ax]
    else:
        axes_to_format = axes
    for ax, title in zip(axes_to_format, ["Measured Vegeta HDR", "Measured Original", "Combined"]):
        ax.set_title(title)
        ax.set_ylabel("Latency (ms)")
        format_latency_axis(ax)
    axes_to_format[-1].set_xlabel("Percentile")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(path, dpi=300)
    plt.close(fig)


def print_summary(truth_values, run_values, statuses, truth_seed):
    print(f"truth_seed={truth_seed}")
    print(f"statuses={statuses}")
    print(f"samples={len(run_values)}")
    print(f"{'percentile':>10} {'truth_ms':>12} {'run_ms':>12} {'run-truth':>12}")

    run_pcts = {}
    truth_pcts = {}
    for pct in SUMMARY_PERCENTILES:
        truth = percentile(truth_values, pct)
        run = percentile(run_values, pct)
        run_pcts[pct] = run
        truth_pcts[pct] = truth
        print(f"p{pct * 100:<9g} {truth:12.3f} {run:12.3f} {run - truth:12.3f}")
    
    return run_pcts, truth_pcts


def mean_stddev(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance)


def print_all_runs_summary(all_run_pcts, all_truth_pcts):
    runs = sorted(all_truth_pcts)
    print(f"\nSummary of percentiles across all runs ({len(runs)} runs):")
    print(
        f"{'percentile':>10} {'truth_mean':>12} {'truth_std':>12} "
        f"{'run_mean':>12} {'run_std':>12} {'diff_mean':>12} {'diff_std':>12}"
    )

    for pct in SUMMARY_PERCENTILES:
        truth_values = [all_truth_pcts[run][pct] for run in runs]
        run_values = [all_run_pcts[run][pct] for run in runs]
        diff_values = [all_run_pcts[run][pct] - all_truth_pcts[run][pct] for run in runs]

        truth_mean, truth_stddev = mean_stddev(truth_values)
        run_mean, run_stddev = mean_stddev(run_values)
        diff_mean, diff_stddev = mean_stddev(diff_values)

        print(
            f"p{pct * 100:<9g} {truth_mean:12.3f} {truth_stddev:12.3f} "
            f"{run_mean:12.3f} {run_stddev:12.3f} {diff_mean:12.3f} {diff_stddev:12.3f}"
        )


def default_output_path(rps, runs, cpu_set, filename):
    return (
        Path("results")
        / "phase_queued_sut_comparison"
        / f"rps_{filename_number(rps)}_{cpu_set}"
        / f"runs_1_to_{runs}"
        / filename
    )

def default_hdr_output_path(output):
    """the output path for the HDR plot"""
    suffix = output.suffix or ".png"
    return output.with_name(f"{output.stem}_hdr{suffix}")

def run_path(first_run_path, run):
    """
    Replaces the path with the correct run number:
    e.g. phase-smooth-data/experiments_phase_queued_sut/rps_5000/run_1/results.csv -> 
        phase-smooth-data/experiments_phase_queued_sut/rps_5000/run_{run}/results.csv
    """
    return first_run_path.parent.parent / f"run_{run}" / first_run_path.name

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare phase-queued-sut run latency with ideal phased open-loop truth.")
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--rps", type=float, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True, help="experiment duration in seconds")
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1, help="first ground-truth seed; run N uses seed + N - 1")
    parser.add_argument("--delays", default="10ms,50ms,100ms,4s")
    parser.add_argument("--phase-schedule", type=parse_phase_schedule, default=parse_phase_schedule(DEFAULT_PHASE_SCHEDULE))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--hdr-output", type=Path, default=None)
    parser.add_argument("--cpu-set", type=str, required=True, help="CPU set label to include in plot title")
    parser.add_argument("--runs", type=int, default=1, help="number of runs to compare (default: 1)")
    args = parser.parse_args()

    delays_ms = [parse_duration_ms(part) for part in args.delays.split(",") if part.strip()]

    truth_values_by_name = []
    run_values_by_name = []
    hdr_points_by_name = []

    all_run_pcts, all_truth_pcts = {}, {}
    for run in range(1, args.runs + 1):
        print(f"run {run}/{args.runs}")

        truth_seed = args.seed + run - 1
        truth_samples = simulate_ground_truth(
            args.rps,
            args.concurrency,
            args.duration,
            args.start_id,
            truth_seed,
            delays_ms,
            args.phase_schedule,
        )
        truth_values = sorted(row["latency_ms"] for row in truth_samples)
        truth_values_by_name.append((f"Run {run} ideal (seed={truth_seed})", truth_values))

        # replace the /run_1/results.csv at the end with /run_{run}/results.csv to load the correct run's results
        results_csv = run_path(args.results_csv, run)
        run_values, statuses = load_run_latencies(results_csv)
        run_values_by_name.append((f"Run {run} Vegeta latency", run_values))

        # obtain the HDR plot points from the Vegeta hdrplot.tsv file in the same directory as results.csv
        hdrplot_tsv = results_csv.with_name("hdrplot.tsv")
        hdr_points_by_name.append((f"Run {run} Vegeta HDR latency", load_hdrplot_points(hdrplot_tsv)))
        run_pcts, truth_pcts = print_summary(truth_values, run_values, statuses, truth_seed)
        all_run_pcts[run] = run_pcts
        all_truth_pcts[run] = truth_pcts

    print_all_runs_summary(all_run_pcts, all_truth_pcts)

    # create the output directories if they don't exist
    output = args.output or default_output_path(args.rps, args.runs, args.cpu_set, "latency_distribution_comparison.png")
    hdr_output = args.hdr_output or default_hdr_output_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    hdr_output.parent.mkdir(parents=True, exist_ok=True)
    hdr_original_output = default_hdr_output_path(output.with_name(f"{output.stem}_hdr_vs_original.png"))
    hdr_original_output.parent.mkdir(parents=True, exist_ok=True)

    # plot the measured and truth latency distributions, saving to the output path
    write_plot(output, truth_values_by_name, run_values_by_name, hdr_points_by_name, args.rps, args.concurrency)
    # plot the measured and truth latency distributions using the HDR points, saving to the hdr_output path
    write_hdr_plot(hdr_output, truth_values_by_name, hdr_points_by_name, args.rps, args.concurrency)
    # plot the measured HDR points and the original measured points, saving to the hdr_original_output path
    write_hdrplot_hdr_and_original(hdr_original_output, run_values_by_name, hdr_points_by_name, args.rps, args.concurrency)
