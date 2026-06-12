#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Global defaults
# Adjusted: Split into HOST and PORT for dynamic URL generation
export TARGET_HOST="${TARGET_HOST:-https://130.127.133.121}"
export START_PORT="${START_PORT:-8080}"
export RATE="${RATE:-3000}"
export DURATION="${DURATION:-60s}"
export PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-25000}"
export MAX_VUS="${MAX_VUS:-1000000}"
export RESPONSE_TYPE="${RESPONSE_TYPE:-text}"
DELAY_BETWEEN_RUNS="${DELAY_BETWEEN_RUNS:-10}"

export K6_INSECURE_SKIP_TLS_VERIFY="true"

RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"
RUNS_PER_CPU="${RUNS_PER_CPU:-3}"
CPU_PROFILE_SPEC="${CPU_PROFILE_SPEC:-limited_cpu_0-7:0-7 full_cpu_0-55:0-55}"

CPU_MONITOR_PID=""

cleanup() {
  if [[ -n "$CPU_MONITOR_PID" ]] && kill -0 "$CPU_MONITOR_PID" 2>/dev/null; then
    kill "$CPU_MONITOR_PID" 2>/dev/null || true
    wait "$CPU_MONITOR_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

write_run_config() {
  local run_dir="$1" cpuset="$2"
  cat <<EOF > "$run_dir/run_config.txt"
target_url=$TARGET_URL
rate=$RATE
duration=$DURATION
pre_allocated_vus=$PRE_ALLOCATED_VUS
max_vus=$MAX_VUS
cpuset=$cpuset
response_type=$RESPONSE_TYPE
EOF
}

run_one() {
  local profile_name="$1" cpuset="$2" run_number="$3"
  local run_dir="$RESULTS_DIR/$profile_name/run_$run_number"
  local k6_results_json="$run_dir/burst-results.json"
  local cpu_results_csv="$run_dir/cpu_utilization.csv"
  
  mkdir -p "$run_dir"
  write_run_config "$run_dir" "$cpuset"

  echo -e "\n=== Profile $profile_name | run $run_number/$RUNS_PER_CPU | CPUs $cpuset ==="
  echo "Output directory: $run_dir"

  echo "Starting CPU monitor..."
  python3 "$SCRIPT_DIR/cpu_monitor.py" "$cpu_results_csv" &
  CPU_MONITOR_PID="$!"
  sleep 0.3

  echo "Running k6 against $TARGET_URL on CPUs $cpuset"

  set +e
  (
    cd "$SCRIPT_DIR"
    taskset -c "$cpuset" ./k6 run --out "json=$k6_results_json" burst-server-test.js
  ) 2>&1 | tee "$run_dir/k6.log"
  local k6_status="${PIPESTATUS[0]}"
  set -e

  cleanup
  CPU_MONITOR_PID=""

  echo "Latency percentiles:"
  python3 "$SCRIPT_DIR/print_latencies.py" "$k6_results_json" | tee "$run_dir/latencies.txt"

  echo "Plotting CPU utilization and VU growth..."
  python3 "$SCRIPT_DIR/plot_cpu_vus.py" --cpu "$cpu_results_csv" --k6 "$k6_results_json" --output "$run_dir/burst-cpu-vus.png" --cores "$cpuset"

  return "$k6_status"
}

main() {
  mkdir -p "$RESULTS_DIR"
  local overall_status=0
  
  # Added: Track the total number of runs globally to calculate the port
  local global_run_count=0

  for profile in $CPU_PROFILE_SPEC; do
    local profile_name="${profile%%:*}"
    local cpuset="${profile#*:}"

    if [[ -z "$profile_name" || -z "$cpuset" || "$profile_name" == "$cpuset" ]]; then
      echo "Invalid CPU profile entry: $profile" >&2
      return 1
    fi

    for ((run_number = 1; run_number <= RUNS_PER_CPU; run_number++)); do
      # Added: Dynamically calculate and export the target URL for this specific run
      local current_port=$((START_PORT + global_run_count))
      export TARGET_URL="${TARGET_HOST}:${current_port}/"

      if ! run_one "$profile_name" "$cpuset" "$run_number"; then
        overall_status=1
        echo "Run failed: profile=$profile_name run=$run_number" >&2
      fi
      
      # Added: Increment the run tracker so the next loop hits the next port
      global_run_count=$((global_run_count + 1))
      
      echo "Sleeping for $DELAY_BETWEEN_RUNS seconds before next run...Restart SUT for accurate tracking"
      sleep "$DELAY_BETWEEN_RUNS"
    done
  done

  echo -e "\nAll requested runs finished. Results root: $RESULTS_DIR"
  return "$overall_status"
}

main "$@"