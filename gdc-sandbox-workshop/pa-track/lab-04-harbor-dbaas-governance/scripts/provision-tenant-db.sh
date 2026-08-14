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

NAMESPACE="${NAMESPACE:-sample-project-1}"

echo "============================================================"
echo " GDC Air-Gapped: Tenant DBaaS Provisioning & Governance"
echo "============================================================"
echo "Target Namespace: ${NAMESPACE}"
echo "Kubeconfig:       ${KUBECTL_CMD[*]}"
echo ""

# Ensure target namespace exists
"${KUBECTL_CMD[@]}" create namespace "${NAMESPACE}" --dry-run=client -o yaml | "${KUBECTL_CMD[@]}" apply -f - >/dev/null 2>&1 || true

# Step 1: Provision Managed DatabaseCluster
echo "▶ Step 1: Provisioning Managed PostgreSQL / AlloyDB Omni Cluster..."
"${KUBECTL_CMD[@]}" apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/02-tenant-database-cluster.yaml"

echo ""
echo "▶ Step 2: Validating DatabaseCluster Resource & Credentials Secret..."
# If in a sandbox where the full DBaaS operator controller manages credentials:
if "${KUBECTL_CMD[@]}" get secret tenant-db-credentials -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "  ✔ Database credentials secret 'tenant-db-credentials' found."
else
    echo "  ℹ Provisioning mock secret 'tenant-db-credentials' for workshop verification..."
    "${KUBECTL_CMD[@]}" create secret generic tenant-db-credentials \
        -n "${NAMESPACE}" \
        --from-literal=host="tenant-order-db-rw.${NAMESPACE}.svc.cluster.local" \
        --from-literal=port="5432" \
        --from-literal=database="orderdb" \
        --from-literal=username="app_admin" \
        --from-literal=password="Secr3tP@ssw0rd123!" \
        --dry-run=client -o yaml | "${KUBECTL_CMD[@]}" apply -f -
    echo "  ✔ Credentials secret created."
fi

echo ""
# Step 3: Apply Database Backup Schedule
echo "▶ Step 3: Applying Automated Snapshot & Backup Policy..."
"${KUBECTL_CMD[@]}" apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/03-database-backup-schedule.yaml"
echo "  ✔ Applied DatabaseBackupSchedule 'tenant-order-db-daily-backup'."

echo ""
# Step 4: Deploy Tenant Application Consumer
echo "▶ Step 4: Deploying Tenant Database Consumer Workload..."
"${KUBECTL_CMD[@]}" apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/04-app-database-consumer.yaml"

echo ""
# Step 5: Verification
echo "▶ Step 5: Inspecting Deployed DBaaS Resources & Application Status..."
echo "------------------------------------------------------------"
echo "Database Clusters:"
"${KUBECTL_CMD[@]}" get databasecluster -n "${NAMESPACE}" 2>/dev/null || echo "  (DatabaseCluster CRD pending operator registration)"

echo ""
echo "Backup Schedules:"
"${KUBECTL_CMD[@]}" get databasebackupschedule -n "${NAMESPACE}" 2>/dev/null || echo "  (DatabaseBackupSchedule CRD pending operator registration)"

echo ""
echo "Tenant Workloads:"
"${KUBECTL_CMD[@]}" get pods -n "${NAMESPACE}" -l app=order-processor

echo ""
echo "============================================================"
echo " DBaaS tenant provisioning and validation complete."
echo "============================================================"
