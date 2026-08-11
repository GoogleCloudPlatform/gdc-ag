#!/bin/bash
#
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
MANIFESTS_DIR="$(cd "${SCRIPT_DIR}/../manifests" && pwd)"
TEMPLATES_DIR="${MANIFESTS_DIR}/templates"
CONSTRAINTS_DIR="${MANIFESTS_DIR}/constraints"

# Load environment configuration if available
if [[ -f "${SCRIPT_DIR}/../../../.env" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../../../.env"
fi

# Determine Kubeconfig / kubectl command
KUBECTL_CMD=("kubectl")
if [[ -n "${CLUSTER_NAME:-}" && -f "${HOME}/${CLUSTER_NAME}-kubeconfig" ]]; then
    KUBECTL_CMD=("kubectl" "--kubeconfig=${HOME}/${CLUSTER_NAME}-kubeconfig")
elif [[ -f "${HOME}/org-1-admin-kubeconfig" ]]; then
    KUBECTL_CMD=("kubectl" "--kubeconfig=${HOME}/org-1-admin-kubeconfig")
elif [[ -n "${KUBECONFIG:-}" && -f "${KUBECONFIG}" ]]; then
    KUBECTL_CMD=("kubectl" "--kubeconfig=${KUBECONFIG}")
fi

echo "============================================================"
echo " GDC Air-Gapped: Policy Controller Guardrails Deployment"
echo "============================================================"
echo "Kubeconfig target: ${KUBECTL_CMD[*]}"
echo ""

# Step 1: Deploy Constraint Templates
echo "▶ Step 1: Applying Gatekeeper ConstraintTemplates..."
for template_file in "${TEMPLATES_DIR}"/*.yaml; do
    echo "  Applying template: $(basename "${template_file}")"
    "${KUBECTL_CMD[@]}" apply -f "${template_file}"
done

echo ""
echo "▶ Step 2: Waiting for Constraint CRDs to be registered..."
CRD_LIST=(
    "k8srequiredregistries.constraints.gatekeeper.sh"
    "k8sdisallowprivilegeds.constraints.gatekeeper.sh"
    "k8sdisallowhostpaths.constraints.gatekeeper.sh"
    "k8srequiredresources.constraints.gatekeeper.sh"
)

for crd in "${CRD_LIST[@]}"; do
    echo -n "  Waiting for CRD ${crd}... "
    for i in {1..30}; do
        if "${KUBECTL_CMD[@]}" get crd "${crd}" >/dev/null 2>&1; then
            echo "Ready!"
            break
        fi
        if [[ $i -eq 30 ]]; then
            echo "Timeout waiting for CRD ${crd}"
            exit 1
        fi
        sleep 2
    done
done

echo ""
# Step 3: Deploy Policy Constraints
echo "▶ Step 3: Applying Enterprise Policy Constraints..."
for constraint_file in "${CONSTRAINTS_DIR}"/*.yaml; do
    echo "  Applying constraint: $(basename "${constraint_file}")"
    "${KUBECTL_CMD[@]}" apply -f "${constraint_file}"
done

echo ""
# Step 4: Verification and Status
echo "▶ Step 4: Verifying deployed constraint status..."
echo "------------------------------------------------------------"
for crd in "${CRD_LIST[@]}"; do
    echo "Inspecting ${crd}:"
    "${KUBECTL_CMD[@]}" get "${crd}" -o wide || true
    echo ""
done

echo "============================================================"
echo " Policy Guardrails deployment complete."
echo " Run ./test-policies.sh to validate admission enforcement."
echo "============================================================"
