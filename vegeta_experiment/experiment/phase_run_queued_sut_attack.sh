#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RPS="${RPS:-5000}"
RATE="${RATE:-${RPS}/s}"
DURATION="${DURATION:-30s}"
TIMEOUT="${TIMEOUT:-60s}"
NAME="${NAME:-phase-queued-sut-${RATE}-${DURATION}}"
HIST_BUCKETS="${HIST_BUCKETS:-[0,5ms,10ms,15ms,25ms,50ms,100ms,200ms,300ms,350ms,400ms,450ms,500ms,750ms,1s,2s,5s,10s,30s]}"
VEGETA_CPUSET="${VEGETA_CPUSET:-0-7}"
RUN_IDS="${RUN_IDS:-1 2 3}"
TARGET_HOST="${TARGET_HOST:-130.127.133.121}"
BASE_PORT="${BASE_PORT:-8079}"
EXPERIMENTS_DIR="${EXPERIMENTS_DIR:-experiments_phase_queued_sut}"
START_ID="${START_ID:-0}"

cd "$ROOT_DIR"
# running with taskset to bind vegeta to specific CPU cores (reproducibility and performance isolation)
VEGETA_CMD=(taskset -c "$VEGETA_CPUSET" "$ROOT_DIR/vegeta")
TARGET_WRITER="$ROOT_DIR/scripts/experiment/utils/write_targets.py"

# each run directed to a different port to avoid conflicts
for RUN_ID in $RUN_IDS; do
  PORT=$((BASE_PORT + RUN_ID))
  EXP_DIR="${ROOT_DIR}/${EXPERIMENTS_DIR}/rps_${RPS}/run_${RUN_ID}"
  TARGET_URL="http://${TARGET_HOST}:${PORT}/"
  mkdir -p "$EXP_DIR"

  # generating the targets.txt file with the appropriate number of targets based on the RPS and duration
  TARGET_COUNT="$(python3 "$TARGET_WRITER" \
    --target-base-url "$TARGET_URL" \
    --output "$EXP_DIR/targets.txt" \
    --rps "$RPS" \
    --duration "$DURATION" \
    --start-id "$START_ID")"

  printf '[experiment] directory: %s\n' "$EXP_DIR"
  printf '[experiment] attack: target=%s rate=%s duration=%s timeout=%s targets=%s start_id=%s\n' \
    "$TARGET_URL" "$RATE" "$DURATION" "$TIMEOUT" "$TARGET_COUNT" "$START_ID"

  CPU_CSV_PATH="$EXP_DIR/cpu_utilization.csv"
  MEMORY_CSV_PATH="$EXP_DIR/memory_utilization.csv"

  # running vegeta attack in the background, capturing its PID for monitoring
  "${VEGETA_CMD[@]}" attack \
    -name "$NAME" \
    -rate "$RATE" \
    -duration "$DURATION" \
    -timeout "$TIMEOUT" \
    -targets "$EXP_DIR/targets.txt" \
    -output "$EXP_DIR/results.gob" \
    -workers-output "$EXP_DIR/workers.json" \
    -workers-timeline-output "$EXP_DIR/workers_timeline.csv" &
  ATTACK_PID=$!

  # running the CPU/memory monitor in the background, capturing its PID for later termination
  python3 "$ROOT_DIR/cpu_monitor.py" "$CPU_CSV_PATH" "$MEMORY_CSV_PATH" "$ATTACK_PID" &
  MONITOR_PID=$!
  printf '[experiment] Started background CPU/memory monitor (PID: %s) for attack PID %s\n' "$MONITOR_PID" "$ATTACK_PID"

  # waiting for the vegeta attack to complete and capturing its exit status
  set +e
  wait "$ATTACK_PID"
  ATTACK_STATUS=$?
  set -e

  # terminating the CPU/memory monitor and waiting for it to finish
  kill -SIGTERM "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  printf '[experiment] Stopped CPU/memory monitor. Data saved to %s and %s\n' "$CPU_CSV_PATH" "$MEMORY_CSV_PATH"

  if [[ "$ATTACK_STATUS" -ne 0 ]]; then
    exit "$ATTACK_STATUS"
  fi

  # generating reports from the vegeta results in various formats (CSV, JSON, histogram, HDR plot)
  "${VEGETA_CMD[@]}" encode -to=csv -output "$EXP_DIR/results.csv" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type=json -output "$EXP_DIR/metrics.json" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type="hist$HIST_BUCKETS" -output "$EXP_DIR/hist.txt" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type=hdrplot -output "$EXP_DIR/hdrplot.tsv" "$EXP_DIR/results.gob"

  printf '[experiment] wrote results under %s\n' "$EXP_DIR"
  sleep 60
done
