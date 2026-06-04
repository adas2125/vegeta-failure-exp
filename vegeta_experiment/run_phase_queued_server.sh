#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Experiment variables (User must set ADDR to the server IP address)
CONCURRENCY="${CONCURRENCY:-2000}"
RUN_ID="${RUN_ID:-1}"
PORT="${PORT:-$((8080 + RUN_ID - 1))}"
ADDR="${ADDR:-130.127.133.121:$PORT}"
SEED="${SEED:-$RUN_ID}" # set SEED to RUN_ID

# Delay tiers
DELAY_1="${DELAY_1:-10ms}"
DELAY_2="${DELAY_2:-50ms}"
DELAY_3="${DELAY_3:-100ms}"
DELAY_4="${DELAY_4:-4000ms}"

# Wall-time phase schedule: start_second:w1,w2,w3,w4
PHASE_SCHEDULE="${PHASE_SCHEDULE:-0:70,20,8,2;5:64,23,10,3;8:20,20,20,30;9:64,23,10,3;14:70,20,8,2}"

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
  -phase-schedule "$PHASE_SCHEDULE" 