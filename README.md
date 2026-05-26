### 05.25.26 Updates
To generate the results, I ran the spurt server located in 
`cmd/spurt/main.go` with the `run_spurt_server.sh` script.
To plot the latencies, I used the raw latencies stored by the Vegeta attack
and construct the ground truth latency distribution from the known phase schedule 
for the spurt server. This script is located in `experiments/compare_exact_latencies.py`