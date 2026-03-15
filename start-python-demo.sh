#!/usr/bin/env bash
#
# Start the Python profiling demo environment.
#
# Usage:
#   ./start-python-demo.sh                     # start the leaky Python service (default)
#   ./start-python-demo.sh leaky               # same as above
#   ./start-python-demo.sh intro               # start the intro Python service
#   ./start-python-demo.sh movies              # start the movies Python service
#   ./start-python-demo.sh timeline            # start the timeline Python service
#   ./start-python-demo.sh all                 # start all Python services
#   ./start-python-demo.sh leaky intro         # start multiple services
#   ./start-python-demo.sh --stop              # stop everything
#
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEMO_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!!]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
step()  { echo -e "\n${YELLOW}---${NC} $1"; }

# ---------------------------------------------------------------------------
# Service registry: name -> app container + load generator
# ---------------------------------------------------------------------------
declare -A APP_MAP=(
    [leaky]="leaky-api-python"
    [intro]="intro-movies-api-python"
    [movies]="movies-api-python"
    [timeline]="movies-api-python-timeline"
)
declare -A LOADGEN_MAP=(
    [leaky]="loadgen-leak-python"
    [intro]="loadgen-movies-api-intro-python"
    [movies]="loadgen-movies-api-python"
    [timeline]="loadgen-timeline-python"
)

AVAILABLE_NAMES="${!APP_MAP[*]}"

# ---------------------------------------------------------------------------
# Handle --stop
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--stop" ]]; then
    step "Stopping all demo containers"
    docker compose down 2>/dev/null || true
    info "All containers stopped"
    exit 0
fi

# ---------------------------------------------------------------------------
# Handle --help
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: $0 [SERVICE...] | --stop | --help"
    echo ""
    echo "Services: $AVAILABLE_NAMES all"
    echo "  (default: leaky)"
    echo ""
    echo "Examples:"
    echo "  $0                  # start leaky service"
    echo "  $0 leaky intro      # start leaky + intro"
    echo "  $0 all              # start all Python services"
    echo "  $0 --stop           # tear down everything"
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse requested services
# ---------------------------------------------------------------------------
REQUESTED=("${@:-leaky}")
if [[ "${REQUESTED[0]}" == "all" ]]; then
    REQUESTED=(leaky intro movies timeline)
fi

APP_CONTAINERS=()
LOADGEN_CONTAINERS=()
for name in "${REQUESTED[@]}"; do
    if [[ -z "${APP_MAP[$name]:-}" ]]; then
        fail "Unknown service '$name'. Available: $AVAILABLE_NAMES all"
    fi
    APP_CONTAINERS+=("${APP_MAP[$name]}")
    LOADGEN_CONTAINERS+=("${LOADGEN_MAP[$name]}")
done

SERVICES_TO_START="movies-api-mongo datadog-agent ${APP_CONTAINERS[*]} ${LOADGEN_CONTAINERS[*]}"

# ---------------------------------------------------------------------------
# 1. Pre-flight: Docker Desktop
# ---------------------------------------------------------------------------
step "1/7  Checking Docker Desktop"
if ! docker info >/dev/null 2>&1; then
    fail "Docker Desktop is not running. Open it from Applications, wait for it to start, then re-run this script."
fi
info "Docker Desktop is running"

# ---------------------------------------------------------------------------
# 2. Pre-flight: DD_API_KEY
# ---------------------------------------------------------------------------
step "2/7  Checking DD_API_KEY"
if [[ -z "${DD_API_KEY:-}" ]]; then
    if [[ -f .env ]] && grep -q DD_API_KEY .env; then
        export "$(grep DD_API_KEY .env | head -1)"
        info "Loaded DD_API_KEY from .env"
    else
        fail "DD_API_KEY is not set. Export it or add it to a .env file in $DEMO_DIR"
    fi
else
    info "DD_API_KEY is set"
fi

# ---------------------------------------------------------------------------
# 3. Clean restart (avoids stale DNS / network issues)
# ---------------------------------------------------------------------------
step "3/7  Tearing down old containers and network"
docker compose down 2>/dev/null || true
info "Clean slate"

# ---------------------------------------------------------------------------
# 4. Start services
# ---------------------------------------------------------------------------
step "4/7  Starting services"
for svc in $SERVICES_TO_START; do
    echo "  -> $svc"
done
docker compose up -d $SERVICES_TO_START 2>&1 | grep -v "variable is not set" | grep -v "attribute.*version.*obsolete" || true
info "Containers started"

# ---------------------------------------------------------------------------
# 5. Wait for health checks
# ---------------------------------------------------------------------------
step "5/7  Waiting for containers to become healthy"
MAX_WAIT=90
ELAPSED=0

FIRST_APP="${APP_CONTAINERS[0]}"
FIRST_APP_CONTAINER="dd-continuous-profiler-demo-${FIRST_APP}-1"
AGENT_CONTAINER="dd-continuous-profiler-demo-datadog-agent-1"

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    AGENT_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$AGENT_CONTAINER" 2>/dev/null || echo "missing")
    APP_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$FIRST_APP_CONTAINER" 2>/dev/null || echo "missing")

    if [[ "$AGENT_HEALTH" == "healthy" && "$APP_HEALTH" == "healthy" ]]; then
        break
    fi

    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo -ne "  agent=$AGENT_HEALTH  $FIRST_APP=$APP_HEALTH  (${ELAPSED}s)\r"
done
echo ""

if [[ "$AGENT_HEALTH" != "healthy" ]]; then
    warn "Agent did not become healthy within ${MAX_WAIT}s (status: $AGENT_HEALTH)"
else
    info "Datadog Agent is healthy"
fi

if [[ "$APP_HEALTH" != "healthy" ]]; then
    warn "$FIRST_APP did not become healthy within ${MAX_WAIT}s (status: $APP_HEALTH)"
else
    info "$FIRST_APP is healthy"
fi

# ---------------------------------------------------------------------------
# 6. Verify data flow
# ---------------------------------------------------------------------------
step "6/7  Waiting 30s for first data to flow"
sleep 30

AGENT_STATUS=$(docker exec "$AGENT_CONTAINER" agent status 2>&1)

TRACES=$(echo "$AGENT_STATUS" | grep "Traces received" | head -1 | grep -oE '[0-9]+' | head -1 || echo "0")
METRICS=$(echo "$AGENT_STATUS" | grep "Metric Packets" | head -1 | grep -oE '[0-9]+' | head -1 || echo "0")

if [[ "$TRACES" -gt 0 ]]; then
    info "APM traces flowing ($TRACES received)"
else
    warn "No APM traces received yet. Check app logs: docker logs $FIRST_APP_CONTAINER"
fi

if [[ "$METRICS" -gt 0 ]]; then
    info "DogStatsD runtime metrics flowing ($METRICS packets)"
else
    warn "No DogStatsD metrics received. Runtime metrics (thread_count, gc.count) won't appear in the Memory Leaks workflow."
fi

UPLOAD_ERRORS=$(docker logs "$FIRST_APP_CONTAINER" 2>&1 | grep -c "Error uploading\|timed out" || true)
if [[ "$UPLOAD_ERRORS" -gt 0 ]]; then
    warn "$FIRST_APP has $UPLOAD_ERRORS upload errors. Run: docker logs $FIRST_APP_CONTAINER 2>&1 | tail -20"
else
    info "No upload errors from $FIRST_APP"
fi

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
step "7/7  Ready"
echo ""
echo "  Services running:"
docker ps --format "    {{.Names}}  {{.Status}}" --filter "label=com.docker.compose.project=dd-continuous-profiler-demo" 2>/dev/null || docker ps --format "    {{.Names}}  {{.Status}}"
echo ""
echo "  Profiling data will appear on Datadog within 1-2 minutes."
echo ""

for name in "${REQUESTED[@]}"; do
    svc="${APP_MAP[$name]}"
    svc_name="${svc//-api-python/}"
    svc_name="${svc_name//-python/}"
    echo "  ${name}:"
    echo "    Staging:  https://dd.datad0g.com/apm/entity/service%3A${svc}?env=prod"
    echo "    Local:    https://dd-dev-local.datad0g.com/apm/entity/service%3A${svc}?env=prod&set_config_profiling-memory-leaks-tab-for-python=true&set_config_profiling-memory-leaks-tab-generic-orchestrators=true#profiling"
    echo ""
done

echo "  Memory Leaks tab: click Profiling > Memory Leaks in the left sidebar"
echo "  Time picker: set to 'Past 15 Minutes' to see fresh data"
echo ""
echo "  To stop:  $0 --stop"
echo ""
