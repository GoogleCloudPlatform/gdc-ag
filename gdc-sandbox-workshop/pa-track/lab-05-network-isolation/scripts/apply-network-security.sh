#!/usr/bin/env bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

DRY_RUN=""
KUBECONFIG_ARG=""
TARGET_NAMESPACES=("tenant-a" "tenant-b" "frontend-project" "backend-api-project" "shared-services")

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Applies GDC Air-Gapped Zero-Trust Network Isolation Policies:
  1. Default Deny NetworkPolicy across all tenant namespaces (DNS egress allowed)
  2. Intra-Namespace Pod-to-Pod communication NetworkPolicy
  3. Explicit Cross-Tenant Service NetworkPolicies
  4. MetalLB Ingress VIP Pool allocations

Options:
  --dry-run                 Perform client-side validation without applying changes
  --kubeconfig <path>       Specify custom kubeconfig path
  --namespaces <ns1,ns2>    Comma-separated list of tenant namespaces (default: tenant-a,tenant-b,frontend-project,backend-api-project,shared-services)
  --help, -h                Display this help message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="--dry-run=client"
      shift
      ;;
    --kubeconfig)
      KUBECONFIG_ARG="--kubeconfig=$2"
      shift 2
      ;;
    --namespaces)
      IFS=',' read -r -a TARGET_NAMESPACES <<< "$2"
      shift 2
      ;;
    --help|-h)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

KUBECTL="kubectl ${KUBECONFIG_ARG}"

echo "===================================================================="
echo "  GDC Air-Gapped Platform Admin: Applying Network Security Policies"
echo "===================================================================="
echo "Manifests Directory : ${MANIFESTS_DIR}"
echo "Target Namespaces   : ${TARGET_NAMESPACES[*]}"
if [[ -n "${DRY_RUN}" ]]; then
  echo "Execution Mode      : DRY RUN (No changes will be written)"
fi
echo "--------------------------------------------------------------------"

# 1. Ensure target namespaces exist
echo "[1/4] Validating and provisioning tenant namespaces..."
for ns in "${TARGET_NAMESPACES[@]}"; do
  if ${KUBECTL} get namespace "${ns}" >/dev/null 2>&1; then
    echo "  ✓ Namespace '${ns}' exists."
  else
    echo "  + Creating namespace '${ns}' with standard isolation labels..."
    ${KUBECTL} create namespace "${ns}" ${DRY_RUN} || true
    ${KUBECTL} label namespace "${ns}" \
      "kubernetes.io/metadata.name=${ns}" \
      "gdc.google.com/tenant-id=${ns}" \
      --overwrite ${DRY_RUN} || true
  fi
done

# 2. Apply Baseline Default Deny to all tenant namespaces
echo ""
echo "[2/4] Applying Baseline Default-Deny NetworkPolicy..."
for ns in "${TARGET_NAMESPACES[@]}"; do
  echo "  -> Applying default-deny to namespace '${ns}'..."
  ${KUBECTL} apply -n "${ns}" -f "${MANIFESTS_DIR}/01-default-deny-networkpolicy.yaml" ${DRY_RUN}
done

# 3. Apply Intra-Namespace Allow Policy
echo ""
echo "[3/4] Applying Intra-Namespace Communication Policy..."
for ns in "${TARGET_NAMESPACES[@]}"; do
  echo "  -> Applying intra-namespace allow to namespace '${ns}'..."
  ${KUBECTL} apply -n "${ns}" -f "${MANIFESTS_DIR}/02-allow-same-namespace.yaml" ${DRY_RUN}
done

# 4. Apply Cross-Tenant Service Contracts
echo ""
echo "[4/4] Applying Explicit Cross-Tenant Service Contracts..."
${KUBECTL} apply -f "${MANIFESTS_DIR}/03-allow-cross-tenant-service.yaml" ${DRY_RUN}

# 5. Apply MetalLB LoadBalancer VIP Pools if CRD exists or if dry run
echo ""
echo "[INFO] Checking MetalLB CRD availability for VIP pools..."
if ${KUBECTL} get crd ipaddresspools.metallb.io >/dev/null 2>&1; then
  echo "  -> MetalLB CRD detected. Applying LoadBalancer VIP pools..."
  ${KUBECTL} apply -f "${MANIFESTS_DIR}/04-loadbalancer-vip-pool.yaml" ${DRY_RUN}
else
  echo "  ! Note: MetalLB CRD not found in target cluster. Applying VIP pools in dry-run or skipping platform CRs."
  if [[ -n "${DRY_RUN}" ]]; then
    ${KUBECTL} apply -f "${MANIFESTS_DIR}/04-loadbalancer-vip-pool.yaml" ${DRY_RUN} || true
  fi
fi

echo ""
echo "===================================================================="
echo "  ✓ Network security policies successfully applied!"
echo "  Verify active policies with: kubectl get networkpolicy -A"
echo "===================================================================="
