#!/usr/bin/env bash
#
# Start the Python profiling demo on a local Kind (Kubernetes in Docker) cluster.
#
# Usage:
#   ./start-python-k8s-demo.sh              # create cluster, build, deploy, print URLs
#   ./start-python-k8s-demo.sh --stop       # delete the kind cluster
#   ./start-python-k8s-demo.sh --rebuild    # rebuild images + rollout restart (cluster stays)
#   ./start-python-k8s-demo.sh --status     # show pod status
#
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEMO_DIR"

CLUSTER_NAME="profiling-demo"
NAMESPACE="profiling-demo"
LEAKY_IMAGE="leaky-api-python:latest"
LOADGEN_IMAGE="loadgen-python:latest"

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
kubectl apply -f k8s/loadgen.yaml
info "All manifests applied"

# If rebuilding, restart deployments to pick up new images
if $IS_REBUILD; then
    step "  Restarting deployments for image refresh"
    kubectl rollout restart deployment/leaky-api-python -n "$NAMESPACE"
    kubectl rollout restart deployment/loadgen-leak-python -n "$NAMESPACE"
fi

# ---------------------------------------------------------------------------
# Wait for rollout
# ---------------------------------------------------------------------------
step "7/8  Waiting for pods to be ready"

kubectl rollout status deployment/leaky-api-python -n "$NAMESPACE" --timeout=120s || \
    warn "leaky-api-python deployment not ready within 120s"

kubectl rollout status daemonset/datadog-agent -n "$NAMESPACE" --timeout=120s || \
    warn "datadog-agent daemonset not ready within 120s"

kubectl rollout status deployment/loadgen-leak-python -n "$NAMESPACE" --timeout=60s || \
    warn "loadgen-leak-python deployment not ready within 60s"

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
echo "  Leaky pod: ${LEAKY_POD}"
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
echo "    Rebuild:  $0 --rebuild"
echo "    Logs:     kubectl logs -n $NAMESPACE $LEAKY_POD -f"
echo "    Agent:    kubectl exec -n $NAMESPACE \$(kubectl get pods -n $NAMESPACE -l app=datadog-agent -o jsonpath='{.items[0].metadata.name}') -- agent status"
echo "    Tear down: $0 --stop"
echo ""
