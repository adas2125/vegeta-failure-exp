#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Experiment variables
RUN_ID="${RUN_ID:-1}"
EXP_DIR="${1:-$ROOT_DIR/experiments_phase_queued_sut_k6/run_${RUN_ID}}"

# Server configuration variables
ADDR="${ADDR:-130.127.133.121:8080}"

# Delay tiers
DELAY_1="${DELAY_1:-10ms}"
DELAY_2="${DELAY_2:-2s}"
DELAY_3="${DELAY_3:-100ms}"
DELAY_4="${DELAY_4:-4s}"

# Wall-time phase schedule: start_second:w1,w2,w3,w4
PHASE_SCHEDULE="${PHASE_SCHEDULE:-0:100,0,0,0;29:0,100,0,0;31:100,0,0,0}"

# creating output directory and building the server binary
mkdir -p "$EXP_DIR"
cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/bin"
go build -o bin/phase-queued-server ./cmd/phase-queued-sut

./bin/phase-queued-server \
  -addr "$ADDR" \
  -delay-1 "$DELAY_1" \
  -delay-2 "$DELAY_2" \
  -delay-3 "$DELAY_3" \
  -delay-4 "$DELAY_4" \
  -phase-schedule "$PHASE_SCHEDULE" \
  -https \
  -close-connections-after 18s \
  -close-connections-until 23s \
  -arrivals-dir "$ROOT_DIR/arrivals_${RUN_ID}" \
  2>&1 | tee "$EXP_DIR/server.log"
