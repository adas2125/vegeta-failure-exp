# k6 Client-Side Churn Experiment

## Overview

This experiment is designed to make `k6` fail under a specific workload. We show that `k6` can fail when it runs against a SUT that:

- closes connections,
- uses HTTPS, and
- forces HTTP/1 connections.

The failure is due to client-side churn. In particular, a smaller client can experience brief CPU utilization spikes, which may cause it to send less load during those intervals. If this under-sending overlaps with the SUT's slow phase, then the latency measurements can exhibit coordinated omission. As a result, the reported `p95` and `p97.5` latencies may be underreported.

## Setup

This experiment requires two machines:

1. **SUT VM**: runs the HTTPS SUT instances.
2. **LG VM**: runs the `k6` load generator.

Run the SUTs first. Each SUT should run in a separate terminal on the SUT VM.

Replace the IP address below with the address of the SUT machine.

```bash
ADDR="130.127.133.121:8080" RUN_ID=1 ./run_phase_queued_server.sh
ADDR="130.127.133.121:8081" RUN_ID=2 ./run_phase_queued_server.sh
ADDR="130.127.133.121:8082" RUN_ID=3 ./run_phase_queued_server.sh
ADDR="130.127.133.121:8083" RUN_ID=4 ./run_phase_queued_server.sh
ADDR="130.127.133.121:8084" RUN_ID=5 ./run_phase_queued_server.sh
```

## Running the Load Generator

On the LG VM, run two sets of experiments.

### 1. Limited CPU setup

This simulates a smaller client machine.

```bash
RUNS_PER_CPU=5 CPU_PROFILE_SPEC="limited_cpu_0-7:0-7" ./run_burst_k6_with_cpu.sh
```

### 2. Full CPU setup

This simulates a larger client machine.

```bash
RUNS_PER_CPU=5 CPU_PROFILE_SPEC="full_cpu_0-55:0-55" ./run_burst_k6_with_cpu.sh
```

## Expected Results Directory Structure

After the runs complete, the results directory should begin populating with subfolders such as:

```text
full_cpu_0-55/
limited_cpu_0-7/
```

These folders contain the JSON files from the actual `k6` output. These JSON files are used by later analysis scripts.

The results directory also includes plots of CPU utilization for each run.

## Plotting Latency Results

After collecting the `k6` results, run:

```bash
python3 plot_latencies.py --start-after=20 --end-before=60
```

We start plotting after 20 seconds because the startup period is typically noisy. This script should automatically plot the full-CPU and limited-CPU runs on the same figure. It should also print the `p95` and `p97.5` latency values for comparison, along with the standard deviations across runs.

## Plotting Arrivals at the SUT

To plot arrivals at the SUT, go to the SUT VM and run:

```bash
python3 plot_arrivals.py
```

This plot is useful for checking whether the limited-client run sends fewer requests during the SUT slow phase.

## Important Note: Adjusting the SUT Slow Phase

Currently, `./run_phase_queued_server.sh` is hard-coded to make the SUT slow from **29s to 31s**.

Depending on the arrival-rate plot at the SUT, this slow phase may need to be changed to better demonstrate coordinated omission.

To change the slow phase, modify the following line in `run_phase_queued_server.sh`:

```bash
PHASE_SCHEDULE="${PHASE_SCHEDULE:-0:100,0,0,0;xx:0,100,0,0;yy:100,0,0,0}"
```

Here:

- `xx` marks the start of the slow phase.
- `yy` marks the end of the slow phase.

For example, if the slow phase should begin at 27 seconds and end at 30 seconds, then `xx = 27` and `yy = 30`.
