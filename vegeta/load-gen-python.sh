#!/usr/bin/env bash
set -e

TARGET_URL="${TARGET_URL:-http://leaky-api-python:9082/movies}"
LOAD_GEN_MODE=${LOAD_GEN_MODE:-0}

function load-gen-target-generator() {
  while true; do
    echo "{\"method\": \"GET\", \"url\": \"${TARGET_URL}?q=$(openssl rand -hex 12)\"}"
    sleep 0.1
  done
}

function load-gen-leak-python() {
  pkill -f vegeta &> /dev/null || true

  # 2 req/s → ~17 min OOM at 512 Mi (256 KiB/req)
  # Only /movies (heap leak); no /spawn-thread so Step 2 stays "No" and flow goes to Live Heap
  load-gen-target-generator \
    | vegeta attack -lazy -format=json -rate=2 -duration=0 -max-workers=4 \
    &> /dev/null &

  echo "🕹  Vegeta leak-test running against ${TARGET_URL} (2 req/s)"
  tail -f /dev/null
}

function load-gen-challenges-python() {
    vegeta -cpus 1 attack -duration=0 -rate=1 -max-workers=1 -targets /usr/local/targets-python.http &> /dev/null &
    echo "🕹  Vegeta challenges load gen running against Python endpoints"
    tail -f /dev/null
}

function load-gen-timeline-python() {
    echo "GET http://movies-api-python-timeline:9083/stats?q=the" | vegeta -cpus 1 attack -duration=0 -rate=0 -max-workers=4 &> /dev/null &
    echo "🕹  Vegeta timeline load gen running against Python stats endpoint"
    tail -f /dev/null
}

function load-gen-intro-python() {
    echo "GET http://intro-movies-api-python:9085/credits?q=and" | vegeta -cpus 1 attack -duration=0 -rate=1 -max-workers=1 &> /dev/null &
    echo "🕹  Vegeta intro load gen running against Python credits endpoint"
    tail -f /dev/null
}

function load-gen-simple() {
  local url="$1"
  local label="$2"
  local rate="${3:-2}"
  pkill -f vegeta &> /dev/null || true

  while true; do
    echo "{\"method\": \"GET\", \"url\": \"${url}\"}"
    sleep 0.5
  done | vegeta attack -lazy -format=json -rate="${rate}" -duration=0 -max-workers=2 \
    &> /dev/null &

  echo "🕹  Vegeta ${label} running against ${url} (${rate} req/s)"
  tail -f /dev/null
}

if [ "$LOAD_GEN_MODE" -eq 1 ]; then
  echo "Mode 1: running leak load gen (Python)"
  load-gen-leak-python
elif [ "$LOAD_GEN_MODE" -eq 2 ]; then
  echo "Mode 2: running challenges load gen (Python)"
  load-gen-challenges-python
elif [ "$LOAD_GEN_MODE" -eq 3 ]; then
  echo "Mode 3: running timeline load gen (Python)"
  load-gen-timeline-python
elif [ "$LOAD_GEN_MODE" -eq 4 ]; then
  echo "Mode 4: running intro load gen (Python)"
  load-gen-intro-python
elif [ "$LOAD_GEN_MODE" -eq 5 ]; then
  echo "Mode 5: running thread-leak load gen (Python)"
  # 2 req/s = 120 threads/min; 2 Gi limit for ~17 min OOM (integer rate ensures vegeta works)
  load-gen-simple "${TARGET_URL}" "thread-leak" 2
elif [ "$LOAD_GEN_MODE" -eq 6 ]; then
  echo "Mode 6: running gc-pressure load gen (Python)"
  # 5 req/s, 100× gc.collect(2)/req → 500 gen2/sec; 2 Gi limit for ~30 min OOM
  load-gen-simple "${TARGET_URL}" "gc-pressure" 5
elif [ "$LOAD_GEN_MODE" -eq 7 ]; then
  echo "Mode 7: running native-leak load gen (Python)"
  # 1 req/s × 2 MiB/req = 2 MiB/s; 4 Gi limit for ~34 min OOM
  load-gen-simple "${TARGET_URL}" "native-leak" 1
else
  echo "Unknown LOAD_GEN_MODE: $LOAD_GEN_MODE (expected 1-7)"
fi
