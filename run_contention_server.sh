#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPS="${RPS:-100}"
RUN_ID="${RUN_ID:-1}"
EXP_DIR="${1:-$ROOT_DIR/experiments_SUT/contention/rps_${RPS}/run_${RUN_ID}}"

ADDR="${ADDR:-127.0.0.1:8080}"
CONN_LIMIT="${CONN_LIMIT:-50}"
DELAY_1="${DELAY_1:-10ms}"
DELAY_2="${DELAY_2:-50ms}"
DELAY_3="${DELAY_3:-100ms}"
DELAY_4="${DELAY_4:-4000ms}"
WEIGHT_1="${WEIGHT_1:-1.0}"
WEIGHT_2="${WEIGHT_2:-1.0}"
WEIGHT_3="${WEIGHT_3:-1.0}"
WEIGHT_4="${WEIGHT_4:-1.0}"
SEED="${SEED:-1}"

mkdir -p "$EXP_DIR"

printf '[experiment] directory: %s\n' "$EXP_DIR"
printf '[experiment] server: addr=%s conn-limit=%s delays=[%s,%s,%s,%s] weights=[%s,%s,%s,%s] seed=%s\n' \
  "$ADDR" "$CONN_LIMIT" "$DELAY_1" "$DELAY_2" "$DELAY_3" "$DELAY_4" \
  "$WEIGHT_1" "$WEIGHT_2" "$WEIGHT_3" "$WEIGHT_4" "$SEED"

cd "$ROOT_DIR"
go run ./cmd/contention \
  --addr        "$ADDR" \
  --conn-limit  "$CONN_LIMIT" \
  --delay-1     "$DELAY_1" \
  --delay-2     "$DELAY_2" \
  --delay-3     "$DELAY_3" \
  --delay-4     "$DELAY_4" \
  --weight-1    "$WEIGHT_1" \
  --weight-2    "$WEIGHT_2" \
  --weight-3    "$WEIGHT_3" \
  --weight-4    "$WEIGHT_4" \
  --seed        "$SEED" \
  --requests-jsonl "$EXP_DIR/requests.jsonl" \
  2>&1 | tee "$EXP_DIR/server.log"
