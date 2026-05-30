#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Experiment variables
CONCURRENCY="${CONCURRENCY:-2000}"
RUN_ID="${RUN_ID:-1}"
RPS="${RPS:-5000}"
EXP_DIR="${1:-$ROOT_DIR/experiments_phase_queued_sut/concurrency_${CONCURRENCY}/rps_${RPS}/run_${RUN_ID}}"

# Server configuration variables
ADDR="${ADDR:-130.127.133.121:8080}"

# set SEED to RUN_ID
SEED="${SEED:-$RUN_ID}"

# Delay tiers
DELAY_1="${DELAY_1:-10ms}"
DELAY_2="${DELAY_2:-50ms}"
DELAY_3="${DELAY_3:-100ms}"
DELAY_4="${DELAY_4:-4000ms}"

# Wall-time phase schedule: start_second:w1,w2,w3,w4
PHASE_SCHEDULE="${PHASE_SCHEDULE:-0:70,20,8,2;5:64,23,10,3;8:20,20,20,30;9:64,23,10,3;14:70,20,8,2}"

mkdir -p "$EXP_DIR"

cd "$ROOT_DIR"

echo "[experiment] building phase queued server..."
go build -o bin/phase-queued-server ./cmd/phase-queued-sut

./bin/phase-queued-server \
  -addr "$ADDR" \
  -concurrency "$CONCURRENCY" \
  -seed "$SEED" \
  -delay-1 "$DELAY_1" \
  -delay-2 "$DELAY_2" \
  -delay-3 "$DELAY_3" \
  -delay-4 "$DELAY_4" \
  -phase-schedule "$PHASE_SCHEDULE" \
  2>&1 | tee "$EXP_DIR/server.log"