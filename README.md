### 05.25.26 Updates

To generate the results, I ran the spurt server located in
`cmd/spurt/main.go` with the `run_spurt_server.sh` script.
To plot the latencies, I used the raw latencies stored by the Vegeta attack
and construct the ground truth latency distribution from the known phase schedule
for the spurt server. This script is located in `experiments/compare_exact_latencies.py`

### 05.28.26 Updates

These use the phase shift server. The commands should be run like this:

#### For the 5K Attack

```sh
RUN_ID=1 RPS=5000 CONCURRENCY=2000 ADDR="130.127.133.121:8080" ./run_phase_queued_server.sh

RUN_ID=2 RPS=5000 CONCURRENCY=2000 ADDR="130.127.133.121:8081" ./run_phase_queued_server.sh

RUN_ID=3 RPS=5000 CONCURRENCY=2000 ADDR="130.127.133.121:8082" ./run_phase_queued_server.sh

RPS=5000 ./scripts/experiment/phase_run_queued_sut_attack.sh
```

#### For the 15K Attack

```sh
RUN_ID=1 RPS=15000 CONCURRENCY=6000 ADDR="130.127.133.121:8080" ./run_phase_queued_server.sh

RUN_ID=2 RPS=15000 CONCURRENCY=6000 ADDR="130.127.133.121:8081" ./run_phase_queued_server.sh

RUN_ID=3 RPS=15000 CONCURRENCY=6000 ADDR="130.127.133.121:8082" ./run_phase_queued_server.sh

RPS=15000 ./scripts/experiment/phase_run_queued_sut_attack.sh
```

#### Analysis scripts

```sh
python3 scripts/experiment/plot_send_rate.py --rps=5000 --runs=3
python3 scripts/experiment/plot_send_rate.py --rps=15000 --runs=3

python3 display_cpu_util.py --rps=5000
python3 display_cpu_util.py --rps=15000

python3 scripts/experiment/phase_compare_queued_sut_latency.py --results-csv=experiments_phase_queued_sut/rps_5000/run_1/results.csv --rps=5000 --concurrency=2000 --duration=30 --runs=3

python3 scripts/experiment/phase_compare_queued_sut_latency.py --results-csv=experiments_phase_queued_sut/rps_15000/run_1/results.csv --rps=15000 --concurrency=6000 --duration=30 --runs=3
```
