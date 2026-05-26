#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPS="${RPS:-10000}"
RUN_ID="${RUN_ID:-1}"
EXP_DIR="${1:-$ROOT_DIR/experiments_SUT/rps_${RPS}/run_${RUN_ID}}"

ADDR="${ADDR:-130.127.133.121:8080}"
DIST="${DIST:-longtail}"
FAST_DELAY="${FAST_DELAY:-10ms}"
SLOW_DELAY="${SLOW_DELAY:-400ms}"
SLOW_PROB="${SLOW_PROB:-0.05}"
SEED="${SEED:-1}"

mkdir -p "$EXP_DIR"

printf '[experiment] directory: %s\n' "$EXP_DIR"
printf '[experiment] server: addr=%s fast=%s slow=%s slow_prob=%s seed=%s\n' \
  "$ADDR" "$FAST_DELAY" "$SLOW_DELAY" "$SLOW_PROB" "$SEED"

cd "$ROOT_DIR"
go run ./cmd/burst \
  --addr "$ADDR" \
  --dist "$DIST" \
  --fast-delay "$FAST_DELAY" \
  --slow-delay "$SLOW_DELAY" \
  --slow-prob "$SLOW_PROB" \
  --seed "$SEED" \
  --requests-jsonl "$EXP_DIR/requests.jsonl" \
  2>&1 | tee "$EXP_DIR/server.log"
