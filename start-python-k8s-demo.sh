#!/usr/bin/env bash
#
# Start the Python profiling demo on a local Kind (Kubernetes in Docker) cluster.
#
# Usage:
#   ./start-python-k8s-demo.sh                    # create cluster, build, deploy, print URLs
#   ./start-python-k8s-demo.sh --stop              # delete the kind cluster
#   ./start-python-k8s-demo.sh --rebuild           # rebuild all images + rollout restart (cluster stays)
#   ./start-python-k8s-demo.sh --rebuild SERVICE   # rebuild + restart only SERVICE (e.g. leaky-api-python)
#   ./start-python-k8s-demo.sh --status            # show pod status
#
# Services: leaky-api-python, thread-leaky-api-python, gc-pressure-api-python, native-leaky-api-python, loadgen
#
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEMO_DIR"

CLUSTER_NAME="profiling-demo"
NAMESPACE="profiling-demo"
LEAKY_IMAGE="leaky-api-python:latest"
THREAD_LEAKY_IMAGE="thread-leaky-api-python:latest"
GC_PRESSURE_IMAGE="gc-pressure-api-python:latest"
NATIVE_LEAKY_IMAGE="native-leaky-api-python:latest"
LOADGEN_IMAGE="loadgen-python:latest"

# Map service name -> (dockerfile, build_context, image, manifest, deployments...)
# build_context is . or vegeta/
declare -A SVC_DOCKERFILE
declare -A SVC_BUILD_CTX
declare -A SVC_IMAGE
declare -A SVC_MANIFEST
SVC_DOCKERFILE[leaky-api-python]="Dockerfile.leaky-python"
SVC_BUILD_CTX[leaky-api-python]="."
SVC_IMAGE[leaky-api-python]="$LEAKY_IMAGE"
SVC_MANIFEST[leaky-api-python]="k8s/leaky-api-python.yaml"

SVC_DOCKERFILE[thread-leaky-api-python]="Dockerfile.thread-leaky-python"
SVC_BUILD_CTX[thread-leaky-api-python]="."
SVC_IMAGE[thread-leaky-api-python]="$THREAD_LEAKY_IMAGE"
SVC_MANIFEST[thread-leaky-api-python]="k8s/thread-leaky-api-python.yaml"

SVC_DOCKERFILE[gc-pressure-api-python]="Dockerfile.gc-pressure-python"
SVC_BUILD_CTX[gc-pressure-api-python]="."
SVC_IMAGE[gc-pressure-api-python]="$GC_PRESSURE_IMAGE"
SVC_MANIFEST[gc-pressure-api-python]="k8s/gc-pressure-api-python.yaml"

SVC_DOCKERFILE[native-leaky-api-python]="Dockerfile.native-leaky-python"
SVC_BUILD_CTX[native-leaky-api-python]="."
SVC_IMAGE[native-leaky-api-python]="$NATIVE_LEAKY_IMAGE"
SVC_MANIFEST[native-leaky-api-python]="k8s/native-leaky-api-python.yaml"

SVC_DOCKERFILE[loadgen]="vegeta/Dockerfile.python"
SVC_BUILD_CTX[loadgen]="vegeta"
SVC_IMAGE[loadgen]="$LOADGEN_IMAGE"
SVC_MANIFEST[loadgen]="k8s/loadgen.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!!]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
step()  { echo -e "\n${CYAN}---${NC} $1"; }

# ---------------------------------------------------------------------------
# --stop: tear down the entire cluster
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--stop" ]]; then
    step "Deleting Kind cluster '$CLUSTER_NAME'"
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
    info "Cluster deleted"
    exit 0
fi

# ---------------------------------------------------------------------------
# --status: show pod status
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--status" ]]; then
    kubectl get pods -n "$NAMESPACE" -o wide 2>/dev/null || echo "Cluster not found or namespace missing"
    exit 0
fi

# ---------------------------------------------------------------------------
# --rebuild SERVICE: rebuild and restart a single service
# ---------------------------------------------------------------------------
REBUILD_SVC=""
if [[ "${1:-}" == "--rebuild" ]]; then
    REBUILD_SVC="${2:-}"
fi

if [[ -n "$REBUILD_SVC" ]]; then
    if [[ -z "${SVC_DOCKERFILE[$REBUILD_SVC]:-}" ]]; then
        fail "Unknown service '$REBUILD_SVC'. Valid: leaky-api-python, thread-leaky-api-python, gc-pressure-api-python, native-leaky-api-python, loadgen"
    fi
    step "Rebuilding and restarting: $REBUILD_SVC"
    # Cluster must exist
    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        fail "No cluster found. Run without --rebuild first to create one."
    fi
    kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1 \
        || fail "Cannot connect to kind cluster"
    # Build
    DOCKERFILE="${SVC_DOCKERFILE[$REBUILD_SVC]}"
    BUILD_CTX="${SVC_BUILD_CTX[$REBUILD_SVC]}"
    IMAGE="${SVC_IMAGE[$REBUILD_SVC]}"
    docker build -t "$IMAGE" -f "$DOCKERFILE" "$BUILD_CTX" 2>&1 | tail -5
    info "Built $IMAGE"
    # Load into Kind
    kind load docker-image "$IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
    info "Loaded $IMAGE into Kind"
    # Apply manifest
    MANIFEST="${SVC_MANIFEST[$REBUILD_SVC]}"
    kubectl apply -f "$MANIFEST"
    info "Applied $MANIFEST"
    # Restart deployment(s)
    case "$REBUILD_SVC" in
        leaky-api-python)
            kubectl rollout restart deployment/leaky-api-python -n "$NAMESPACE"
            kubectl rollout status deployment/leaky-api-python -n "$NAMESPACE" --timeout=120s
            ;;
        thread-leaky-api-python)
            kubectl rollout restart deployment/thread-leaky-api-python -n "$NAMESPACE"
            kubectl rollout status deployment/thread-leaky-api-python -n "$NAMESPACE" --timeout=120s
            ;;
        gc-pressure-api-python)
            kubectl rollout restart deployment/gc-pressure-api-python -n "$NAMESPACE"
            kubectl rollout status deployment/gc-pressure-api-python -n "$NAMESPACE" --timeout=120s
            ;;
        native-leaky-api-python)
            kubectl rollout restart deployment/native-leaky-api-python -n "$NAMESPACE"
            kubectl rollout status deployment/native-leaky-api-python -n "$NAMESPACE" --timeout=120s
            ;;
        loadgen)
            for dep in loadgen-leak-python loadgen-thread-leak-python loadgen-gc-pressure-python loadgen-native-leak-python; do
                kubectl rollout restart deployment/"$dep" -n "$NAMESPACE"
            done
            kubectl rollout status deployment/loadgen-leak-python -n "$NAMESPACE" --timeout=60s
            ;;
    esac
    info "Restarted $REBUILD_SVC"
    echo ""
    kubectl get pods -n "$NAMESPACE" -o wide
    exit 0
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
step "1/8  Pre-flight checks"

for cmd in kind kubectl docker; do
    if ! command -v "$cmd" &>/dev/null; then
        fail "'$cmd' is not installed. Install it and re-run."
    fi
done
info "kind, kubectl, docker found"

if ! docker info >/dev/null 2>&1; then
    fail "Docker is not running. Start Docker Desktop and re-run."
fi
info "Docker is running"

if [[ -z "${DD_API_KEY:-}" ]]; then
    if [[ -f .env ]] && grep -q DD_API_KEY .env; then
        export "$(grep DD_API_KEY .env | head -1)"
        info "Loaded DD_API_KEY from .env"
    else
        fail "DD_API_KEY is not set. Export it or add it to $DEMO_DIR/.env"
    fi
else
    info "DD_API_KEY is set"
fi

# ---------------------------------------------------------------------------
# Build Docker images
# ---------------------------------------------------------------------------
step "2/8  Building Docker images"

docker build -t "$LEAKY_IMAGE" -f Dockerfile.leaky-python . 2>&1 | tail -3
info "Built $LEAKY_IMAGE"

docker build -t "$THREAD_LEAKY_IMAGE" -f Dockerfile.thread-leaky-python . 2>&1 | tail -3
info "Built $THREAD_LEAKY_IMAGE"

docker build -t "$GC_PRESSURE_IMAGE" -f Dockerfile.gc-pressure-python . 2>&1 | tail -3
info "Built $GC_PRESSURE_IMAGE"

docker build -t "$NATIVE_LEAKY_IMAGE" -f Dockerfile.native-leaky-python . 2>&1 | tail -3
info "Built $NATIVE_LEAKY_IMAGE"

docker build -t "$LOADGEN_IMAGE" -f vegeta/Dockerfile.python vegeta/ 2>&1 | tail -3
info "Built $LOADGEN_IMAGE"

# ---------------------------------------------------------------------------
# Create or reuse Kind cluster
# ---------------------------------------------------------------------------
IS_REBUILD=false
if [[ "${1:-}" == "--rebuild" ]]; then
    IS_REBUILD=true
fi

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    info "Kind cluster '$CLUSTER_NAME' already exists"
else
    if $IS_REBUILD; then
        fail "No cluster found. Run without --rebuild first to create one."
    fi
    step "3/8  Creating Kind cluster '$CLUSTER_NAME'"
    kind create cluster --name "$CLUSTER_NAME" --wait 60s
    info "Cluster created"
fi

# Point kubectl at the kind cluster
kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1 \
    || fail "Cannot connect to kind cluster. Run: kubectl config use-context kind-${CLUSTER_NAME}"

# ---------------------------------------------------------------------------
# Load images into Kind
# ---------------------------------------------------------------------------
step "4/8  Loading images into Kind cluster"

kind load docker-image "$LEAKY_IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
info "Loaded $LEAKY_IMAGE"

kind load docker-image "$THREAD_LEAKY_IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
info "Loaded $THREAD_LEAKY_IMAGE"

kind load docker-image "$GC_PRESSURE_IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
info "Loaded $GC_PRESSURE_IMAGE"

kind load docker-image "$NATIVE_LEAKY_IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
info "Loaded $NATIVE_LEAKY_IMAGE"

kind load docker-image "$LOADGEN_IMAGE" --name "$CLUSTER_NAME" 2>&1 | tail -1
info "Loaded $LOADGEN_IMAGE"

# ---------------------------------------------------------------------------
# Create namespace + Secret
# ---------------------------------------------------------------------------
step "5/8  Applying namespace and API key secret"

kubectl apply -f k8s/namespace.yaml

kubectl create secret generic datadog-api-key \
    --namespace "$NAMESPACE" \
    --from-literal=api-key="$DD_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
info "Secret 'datadog-api-key' applied"

# ---------------------------------------------------------------------------
# Apply manifests
# ---------------------------------------------------------------------------
step "6/8  Applying K8s manifests"

if kubectl get deployment -n "$NAMESPACE" datadog-agent-operator &>/dev/null; then
    info "Datadog Operator detected -- skipping agent DaemonSet (Operator manages it)"
else
    kubectl apply -f k8s/datadog-agent.yaml
    info "Agent DaemonSet applied"
fi
kubectl apply -f k8s/leaky-api-python.yaml
kubectl apply -f k8s/thread-leaky-api-python.yaml
kubectl apply -f k8s/gc-pressure-api-python.yaml
kubectl apply -f k8s/native-leaky-api-python.yaml
kubectl apply -f k8s/loadgen.yaml
info "All manifests applied"

# If rebuilding, restart deployments to pick up new images
if $IS_REBUILD; then
    step "  Restarting deployments for image refresh"
    kubectl rollout restart deployment/leaky-api-python -n "$NAMESPACE"
    kubectl rollout restart deployment/thread-leaky-api-python -n "$NAMESPACE"
    kubectl rollout restart deployment/gc-pressure-api-python -n "$NAMESPACE"
    kubectl rollout restart deployment/native-leaky-api-python -n "$NAMESPACE"
    kubectl rollout restart deployment/loadgen-leak-python -n "$NAMESPACE"
    kubectl rollout restart deployment/loadgen-thread-leak-python -n "$NAMESPACE"
    kubectl rollout restart deployment/loadgen-gc-pressure-python -n "$NAMESPACE"
    kubectl rollout restart deployment/loadgen-native-leak-python -n "$NAMESPACE"
fi

# ---------------------------------------------------------------------------
# Wait for rollout
# ---------------------------------------------------------------------------
step "7/8  Waiting for pods to be ready"

kubectl rollout status deployment/leaky-api-python -n "$NAMESPACE" --timeout=120s || \
    warn "leaky-api-python deployment not ready within 120s"

kubectl rollout status deployment/thread-leaky-api-python -n "$NAMESPACE" --timeout=120s || \
    warn "thread-leaky-api-python deployment not ready within 120s"

kubectl rollout status deployment/gc-pressure-api-python -n "$NAMESPACE" --timeout=120s || \
    warn "gc-pressure-api-python deployment not ready within 120s"

kubectl rollout status deployment/native-leaky-api-python -n "$NAMESPACE" --timeout=120s || \
    warn "native-leaky-api-python deployment not ready within 120s"

kubectl rollout status daemonset/datadog-agent -n "$NAMESPACE" --timeout=120s || \
    warn "datadog-agent daemonset not ready within 120s"

kubectl rollout status deployment/loadgen-leak-python -n "$NAMESPACE" --timeout=60s || \
    warn "loadgen-leak-python deployment not ready within 60s"

kubectl rollout status deployment/loadgen-thread-leak-python -n "$NAMESPACE" --timeout=60s || \
    warn "loadgen-thread-leak-python deployment not ready within 60s"

kubectl rollout status deployment/loadgen-gc-pressure-python -n "$NAMESPACE" --timeout=60s || \
    warn "loadgen-gc-pressure-python deployment not ready within 60s"

kubectl rollout status deployment/loadgen-native-leak-python -n "$NAMESPACE" --timeout=60s || \
    warn "loadgen-native-leak-python deployment not ready within 60s"

echo ""
kubectl get pods -n "$NAMESPACE" -o wide
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
step "8/8  Ready"

LEAKY_POD=$(kubectl get pods -n "$NAMESPACE" -l app=leaky-api-python -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "unknown")

echo ""
echo "  Cluster:   kind-${CLUSTER_NAME}"
echo "  Namespace: ${NAMESPACE}"
echo ""
echo "  Services running:"
echo "    leaky-api-python          — heap leak (OOM ~13 min)"
echo "    thread-leaky-api-python   — thread count grows"
echo "    gc-pressure-api-python    — GC gen2 collections grow"
echo "    native-leaky-api-python   — native malloc leak (RSS >> heap)"
echo ""
echo "  Profiling data will appear on Datadog within 1-2 minutes."
echo ""
echo "  Links (switch to profiling-public-symbols org after opening):"
echo "    Staging:  https://app.datad0g.com/apm/entity/service%3Aleaky-api-python?env=prod"
echo "    Local:    https://app-dev-local.datad0g.com/apm/entity/service%3Aleaky-api-python?env=prod#profiling"
echo ""
echo "  Persistent feature flags (run once in browser console):"
echo "    localStorage.setItem('set_config_profiling-memory-leaks-tab-for-python', 'true');"
echo "    localStorage.setItem('set_config_profiling-memory-leaks-tab-generic-orchestrators', 'true');"
echo ""
echo "  Useful commands:"
echo "    Status:   $0 --status"
echo "    Rebuild:  $0 --rebuild                    # all services"
echo "    Rebuild:  $0 --rebuild leaky-api-python   # single service"
echo "    Logs:     kubectl logs -n $NAMESPACE $LEAKY_POD -f"
echo "    Agent:    kubectl exec -n $NAMESPACE \$(kubectl get pods -n $NAMESPACE -l app=datadog-agent -o jsonpath='{.items[0].metadata.name}') -- agent status"
echo "    Tear down: $0 --stop"
echo ""
