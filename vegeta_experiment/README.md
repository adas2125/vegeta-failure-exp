### Reproducing Experiment 1

This experiment runs several attacks against a phase-shifting SUT. The SUT
alternates between fast and slow phases and uses a limited concurrency pool,
which also introduces queuing artifacts.

The goal is to show that, with default Vegeta settings, the load generator (LG)
can silently fail to deliver the expected load distribution to the SUT. This can
lead to issues such as coordinated omission.

### Some Important Notes

This repository includes the files `attack.go` and `lib/attack.go`. Assuming 
you have already cloned Vegeta, replace the original files with the same name
by these new ones to ensure that everything runs smoothly. Additionally, I have
also included a setup script `setup_vegeta.sh`. Copy this over to the
local copy of Vegeta and run it as well.

#### 12K Vegeta Attack Against a Limited-Concurrency CPU on a Large Node

This case simulates a larger node by increasing CPU access with `taskset`.

On the SUT VM, run the following commands in separate terminals:

```sh
RUN_ID=1 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=2 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=3 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=4 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=5 CONCURRENCY=4800 ./run_phase_queued_server.sh
```

These commands use the `RUN_ID` variable to start the servers on different ports
and initialize them with different seeds for request-handling randomization.

On the LG VM, run the following command:

```sh
VEGETA_CPUSET="0-55"  RPS=12000 ./experiment/phase_run_queued_sut_attack.sh
```

#### 12K Vegeta Attack Against a Limited-Concurrency CPU on a Small Node

This case simulates a smaller node by decreasing CPU access with `taskset`.

On the SUT VM, run the following commands in separate terminals:

```sh
RUN_ID=1 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=2 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=3 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=4 CONCURRENCY=4800 ./run_phase_queued_server.sh
RUN_ID=5 CONCURRENCY=4800 ./run_phase_queued_server.sh
```

On the LG VM, run the following command:

```sh
VEGETA_CPUSET="0-7"  RPS=12000 ./scripts/experiment/phase_run_queued_sut_attack.sh
```

#### 5K Vegeta Attack Against 2K Concurrency on a Small Node

This case simulates a smaller node by decreasing CPU access with `taskset`.

On the SUT VM, run the following commands in separate terminals:

```sh
RUN_ID=1 CONCURRENCY=2000 ./run_phase_queued_server.sh
RUN_ID=2 CONCURRENCY=2000 ./run_phase_queued_server.sh
RUN_ID=3 CONCURRENCY=2000 ./run_phase_queued_server.sh
RUN_ID=4 CONCURRENCY=2000 ./run_phase_queued_server.sh
RUN_ID=5 CONCURRENCY=2000 ./run_phase_queued_server.sh
```

On the LG VM, run the following command:

```sh
VEGETA_CPUSET="0-7"  RPS=5000 ./scripts/experiment/phase_run_queued_sut_attack.sh
```

#### 15K Vegeta Attack Against 6K Concurrency on a Small Node

This case simulates a smaller node by decreasing CPU access with `taskset`.

On the SUT VM, run the following commands in separate terminals:

```sh
RUN_ID=1 CONCURRENCY=6000 ./run_phase_queued_server.sh
RUN_ID=2 CONCURRENCY=6000 ./run_phase_queued_server.sh
RUN_ID=3 CONCURRENCY=6000 ./run_phase_queued_server.sh
RUN_ID=4 CONCURRENCY=6000 ./run_phase_queued_server.sh
RUN_ID=5 CONCURRENCY=6000 ./run_phase_queued_server.sh
```

On the LG VM, run the following command:

```sh
VEGETA_CPUSET="0-7"  RPS=15000 ./scripts/experiment/phase_run_queued_sut_attack.sh
```

#### Analysis Scripts

After the results have been collected, this workflow assumes they are stored in
the standard format under the `phase-smooth-data/` directory.

Run the following scripts to generate the full results and figures:

```sh
# Plots and saves send rates over time
python3 experiment/plot_send_rate.py --rps=5000 --runs=5 --cpu-set=0-7
python3 experiment/plot_send_rate.py --rps=15000 --runs=5 --cpu-set=0-7
python3 experiment/plot_send_rate.py --rps=12000 --runs=5 --cpu-set=0-7
python3 experiment/plot_send_rate.py --rps=12000 --runs=5 --cpu-set=0-55

# Plots and saves CPU utilization over time
python3 display_cpu_util.py --rps=5000 --cpu-set=0-7
python3 display_cpu_util.py --rps=15000 --cpu-set=0-7
python3 display_cpu_util.py --rps=12000 --cpu-set=0-7
python3 display_cpu_util.py --rps=12000 --cpu-set=0-55

# Plots and saves HDR and raw latency histograms in comparison with the ground truth
python3 experiment/phase_compare_queued_sut_latency.py --results-csv=phase-smooth-data/experiments_phase_queued_sut/rps_5000_0-7/run_1/results.csv --rps=5000 --concurrency=2000 --duration=30 --runs=5 --cpu-set=0-7

python3 experiment/phase_compare_queued_sut_latency.py --results-csv=phase-smooth-data/experiments_phase_queued_sut/rps_15000_0-7/run_1/results.csv --rps=15000 --concurrency=6000 --duration=30 --runs=5 --cpu-set=0-7

python3 experiment/phase_compare_queued_sut_latency.py --results-csv=phase-smooth-data/experiments_phase_queued_sut/rps_12000_0-7/run_1/results.csv --rps=12000 --concurrency=4800 --duration=30 --runs=5 --cpu-set=0-7

python3 experiment/phase_compare_queued_sut_latency.py --results-csv=phase-smooth-data/experiments_phase_queued_sut/rps_12000_0-55/run_1/results.csv --rps=12000 --concurrency=4800 --duration=30 --runs=5 --cpu-set=0-55
```
