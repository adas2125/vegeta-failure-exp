#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RPS="${RPS:-20000}"
RATE="${RATE:-${RPS}/s}"
DURATION="${DURATION:-30s}"
TIMEOUT="${TIMEOUT:-5s}"
NAME="${NAME:-burst-${RATE}-${DURATION}}"
HIST_BUCKETS="${HIST_BUCKETS:-[0,5ms,10ms,15ms,25ms,50ms,100ms,200ms,300ms,350ms,400ms,450ms,500ms,750ms,1s,2s,5s]}"
VEGETA_CPUSET="${VEGETA_CPUSET:-0-7}"
cd "$ROOT_DIR"

VEGETA_CMD=(taskset -c "$VEGETA_CPUSET" "$ROOT_DIR/vegeta")

for RUN_ID in 1 2 3; do
  PORT=$((8079 + RUN_ID))
  EXP_DIR="${ROOT_DIR}/experiments/rps_${RPS}/run_${RUN_ID}"
  TARGET_URL="http://130.127.133.121:${PORT}/"
  mkdir -p "$EXP_DIR"
  
  printf 'GET %s\n' "$TARGET_URL" > "$EXP_DIR/targets.txt"
  printf '[experiment] directory: %s\n' "$EXP_DIR"
  printf '[experiment] attack: target=%s rate=%s duration=%s timeout=%s\n' \
    "$TARGET_URL" "$RATE" "$DURATION" "$TIMEOUT"

  CPU_CSV_PATH="$EXP_DIR/cpu_utilization.csv"
  MEMORY_CSV_PATH="$EXP_DIR/memory_utilization.csv"

  "${VEGETA_CMD[@]}" attack \
    -name "$NAME" \
    -rate "$RATE" \
    -duration "$DURATION" \
    -timeout "$TIMEOUT" \
    -targets "$EXP_DIR/targets.txt" \
    -output "$EXP_DIR/results.gob" \
    -workers-output "$EXP_DIR/workers.json" &
  ATTACK_PID=$!

  # --- START BACKGROUND CPU/MEMORY MONITOR ---
  python3 "$ROOT_DIR/cpu_monitor.py" "$CPU_CSV_PATH" "$MEMORY_CSV_PATH" "$ATTACK_PID" &
  MONITOR_PID=$!
  printf '[experiment] Started background CPU/memory monitor (PID: %s) for attack PID %s\n' "$MONITOR_PID" "$ATTACK_PID"
  # ------------------------------------------

  set +e
  wait "$ATTACK_PID"
  ATTACK_STATUS=$?
  set -e
    
  # --- STOP BACKGROUND CPU/MEMORY MONITOR ---
  # Send termination signal and wait for the process to cleanly exit
  kill -SIGTERM "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  printf '[experiment] Stopped CPU/memory monitor. Data saved to %s and %s\n' "$CPU_CSV_PATH" "$MEMORY_CSV_PATH"
  # -----------------------------------------

  if [[ "$ATTACK_STATUS" -ne 0 ]]; then
    exit "$ATTACK_STATUS"
  fi

  "${VEGETA_CMD[@]}" encode -to=csv -output "$EXP_DIR/results.csv" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type=json -output "$EXP_DIR/metrics.json" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type="hist$HIST_BUCKETS" -output "$EXP_DIR/hist.txt" "$EXP_DIR/results.gob"
  "${VEGETA_CMD[@]}" report -type=hdrplot -output "$EXP_DIR/hdrplot.tsv" "$EXP_DIR/results.gob"
  
  printf '[experiment] wrote results under %s\n' "$EXP_DIR"
  sleep 60

done