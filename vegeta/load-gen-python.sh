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

  load-gen-target-generator \
    | vegeta attack -lazy -format=json -rate=1 -duration=0 -max-workers=1 \
    &> /dev/null &

  echo "🕹  Vegeta leak-test running against ${TARGET_URL}"
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
else
  echo "Unknown LOAD_GEN_MODE: $LOAD_GEN_MODE (expected 1-4)"
fi
