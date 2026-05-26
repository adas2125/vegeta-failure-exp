#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPS="${RPS:-15000}"
RUN_ID="${RUN_ID:-1}"
EXP_DIR="${1:-$ROOT_DIR/experiments_SUT/rps_${RPS}/run_${RUN_ID}}"

ADDR="${ADDR:-130.127.133.121:8080}"
FAST_DELAY="${FAST_DELAY:-10ms}"
SLOW_DELAY="${SLOW_DELAY:-4000ms}"
CYCLE="${CYCLE:-4s}"
SPIKE="${SPIKE:-1500ms}"

mkdir -p "$EXP_DIR"

printf '[experiment] directory: %s\n' "$EXP_DIR"
printf '[experiment] server: addr=%s fast=%s slow=%s cycle=%s spike=%s\n' \
  "$ADDR" "$FAST_DELAY" "$SLOW_DELAY" "$CYCLE" "$SPIKE"

cd "$ROOT_DIR"

# 1. Build the binary first to avoid go run overhead during execution
echo "[experiment] building spurt server..."
go build -o bin/spurt ./cmd/spurt/main.go

# 2. Execute the binary and pass the specific output paths for your logs
./bin/spurt \
  --addr "$ADDR" \
  --fast-delay "$FAST_DELAY" \
  --slow-delay "$SLOW_DELAY" \
  --cycle "$CYCLE" \
  --spike "$SPIKE" \
  --csv "$EXP_DIR/spurt_data.csv" \
  --phase-csv "$EXP_DIR/phase_log.csv" \
  --requests-jsonl "$EXP_DIR/requests.jsonl" \
  2>&1 | tee "$EXP_DIR/server.log"