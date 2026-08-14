#!/usr/bin/env bash

# Copyright 2026 Google LLC
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

# ==============================================================================
# test-permissions.sh
# -------------------
# Automated verification script testing RBAC enforcement, least-privilege
# access, and cross-tenant isolation in GDC using `kubectl auth can-i`.
# ==============================================================================

set -euo pipefail

# ANSI Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

KUBECONFIG_FLAG=""
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  -k, --kubeconfig <path> Specify path to kubeconfig file"
  echo "  -h, --help             Display this help message"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -k|--kubeconfig)
      KUBECONFIG_FLAG="--kubeconfig $2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      usage
      ;;
  esac
done

if ! command -v kubectl &> /dev/null; then
  echo -e "${RED}[ERROR] 'kubectl' binary not found in PATH.${NC}"
  exit 1
fi

assert_permission() {
  local user="$1"
  local group="$2"
  local verb="$3"
  local resource="$4"
  local namespace="$5"
  local expected="$6" # "yes" or "no"
  local description="$7"

  TOTAL_TESTS=$((TOTAL_TESTS + 1))

  local cmd=("kubectl" "auth" "can-i" "${verb}" "${resource}" "-n" "${namespace}")
  if [[ -n "${KUBECONFIG_FLAG}" ]]; then
    cmd+=(${KUBECONFIG_FLAG})
  fi
  if [[ -n "${user}" ]]; then
    cmd+=("--as=${user}")
  fi
  if [[ -n "${group}" ]]; then
    cmd+=("--as-group=${group}")
  fi

  local actual
  actual=$("${cmd[@]}" 2>/dev/null || echo "no")
  actual=$(echo "${actual}" | tr '[:upper:]' '[:lower:]' | xargs)

  local display_subject="${user:-<no-user>}"
  if [[ -n "${group}" ]]; then
    display_subject="${display_subject} [${group}]"
  fi

  if [[ "${actual}" == "${expected}" ]]; then
    PASSED_TESTS=$((PASSED_TESTS + 1))
    printf "  ${GREEN}✔ PASS${NC} | %-32s | %-14s | %-16s | %-4s (got %-3s) | %s\n" \
      "${display_subject:0:32}" "${namespace}" "${verb} ${resource}" "${expected}" "${actual}" "${description}"
  else
    FAILED_TESTS=$((FAILED_TESTS + 1))
    printf "  ${RED}✘ FAIL${NC} | %-32s | %-14s | %-16s | %-4s (got %-3s) | %s\n" \
      "${display_subject:0:32}" "${namespace}" "${verb} ${resource}" "${expected}" "${actual}" "${description}"
  fi
}

echo -e "${BOLD}========================================================================================================${NC}"
echo -e "${BOLD}🛡️  GDC Air-Gapped RBAC & Tenant Isolation Test Matrix${NC}"
echo -e "${BOLD}========================================================================================================${NC}"
printf "\n  ${BOLD}%-6s | %-32s | %-14s | %-16s | %-10s | %s${NC}\n" "STATUS" "SUBJECT (USER / GROUP)" "NAMESPACE" "ACTION" "EXP (ACT)" "TEST DESCRIPTION"
printf "%s\n" "  ------------------------------------------------------------------------------------------------------"

# ==============================================================================
# SUITE 1: Developer Persona (alice-dev@example.com / developers-grp)
# ==============================================================================
echo -e "\n${BOLD}${CYAN}▶ Test Suite 1: Developer Persona Permissions & Boundaries${NC}"
assert_permission "alice-dev@example.com" "developers-grp" "create" "pods" "finance-dev" "yes" "Dev can create pods in finance-dev"
assert_permission "alice-dev@example.com" "developers-grp" "create" "deployments.apps" "finance-dev" "yes" "Dev can create deployments in finance-dev"
assert_permission "alice-dev@example.com" "developers-grp" "delete" "pods" "finance-dev" "yes" "Dev can delete pods in finance-dev"
assert_permission "alice-dev@example.com" "developers-grp" "create" "roles.rbac.authorization.k8s.io" "finance-dev" "no" "Dev CANNOT modify RBAC roles in finance-dev"
assert_permission "alice-dev@example.com" "developers-grp" "delete" "resourcequotas" "finance-dev" "no" "Dev CANNOT delete ResourceQuota in finance-dev"

# Production Access Check for Developers (Strictly Read-Only / Auditor)
assert_permission "alice-dev@example.com" "finance-devs-grp" "get" "pods" "finance-prod" "yes" "Dev can view pods in finance-prod (Auditor role)"
assert_permission "alice-dev@example.com" "finance-devs-grp" "create" "pods" "finance-prod" "no" "Dev CANNOT create pods in finance-prod"
assert_permission "alice-dev@example.com" "finance-devs-grp" "delete" "deployments.apps" "finance-prod" "no" "Dev CANNOT delete deployments in finance-prod"

# Cross-Tenant Isolation
assert_permission "alice-dev@example.com" "developers-grp" "get" "pods" "analytics-lab" "no" "Dev CANNOT access analytics-lab (Cross-tenant boundary)"

# ==============================================================================
# SUITE 2: Tenant Administrator Persona (finance-lead@example.com / finance-admins-grp)
# ==============================================================================
echo -e "\n${BOLD}${CYAN}▶ Test Suite 2: Tenant Project Admin Persona${NC}"
assert_permission "finance-lead@example.com" "finance-admins-grp" "create" "deployments.apps" "finance-dev" "yes" "Tenant Admin can manage deployments in finance-dev"
assert_permission "finance-lead@example.com" "finance-admins-grp" "create" "rolebindings.rbac.authorization.k8s.io" "finance-dev" "yes" "Tenant Admin can delegate RBAC bindings in finance-dev"
assert_permission "finance-lead@example.com" "finance-admins-grp" "delete" "resourcequotas" "finance-dev" "no" "Tenant Admin CANNOT delete ResourceQuota (Platform Admin only)"
assert_permission "finance-lead@example.com" "finance-admins-grp" "create" "deployments.apps" "finance-prod" "yes" "Tenant Admin can manage deployments in finance-prod"
assert_permission "finance-lead@example.com" "finance-admins-grp" "create" "deployments.apps" "analytics-lab" "no" "Finance Admin CANNOT manage analytics-lab"

# ==============================================================================
# SUITE 3: Compliance & Security Auditor Persona (audit-bot@example.com / auditors-grp)
# ==============================================================================
echo -e "\n${BOLD}${CYAN}▶ Test Suite 3: Compliance Auditor Persona (Read-Only Guardrails)${NC}"
assert_permission "audit-bot@example.com" "auditors-grp" "get" "pods" "finance-dev" "yes" "Auditor can read pods in finance-dev"
assert_permission "audit-bot@example.com" "auditors-grp" "get" "resourcequotas" "finance-dev" "yes" "Auditor can inspect quotas in finance-dev"
assert_permission "audit-bot@example.com" "auditors-grp" "create" "pods" "finance-dev" "no" "Auditor CANNOT create pods in finance-dev"
assert_permission "audit-bot@example.com" "auditors-grp" "delete" "services" "finance-dev" "no" "Auditor CANNOT delete services in finance-dev"
assert_permission "audit-bot@example.com" "auditors-grp" "create" "pods/exec" "finance-dev" "no" "Auditor CANNOT exec into pods (Prevent container intrusion)"
assert_permission "audit-bot@example.com" "auditors-grp" "get" "pods" "finance-prod" "yes" "Auditor can read pods in finance-prod"
assert_permission "audit-bot@example.com" "auditors-grp" "get" "pods" "analytics-lab" "yes" "Auditor can read pods in analytics-lab"

# ==============================================================================
# SUITE 4: CI/CD Pipeline Automation ServiceAccounts
# ==============================================================================
echo -e "\n${BOLD}${CYAN}▶ Test Suite 4: Scoped CI/CD Pipeline Automation Identity${NC}"
assert_permission "system:serviceaccount:finance-dev:gitlab-deployer-sa" "" "create" "deployments.apps" "finance-dev" "yes" "GitLab SA can create deployments in finance-dev"
assert_permission "system:serviceaccount:finance-dev:gitlab-deployer-sa" "" "create" "secrets" "finance-dev" "yes" "GitLab SA can manage secrets in finance-dev"
assert_permission "system:serviceaccount:finance-dev:gitlab-deployer-sa" "" "create" "rolebindings.rbac.authorization.k8s.io" "finance-dev" "no" "GitLab SA CANNOT modify RBAC in finance-dev"
assert_permission "system:serviceaccount:finance-dev:gitlab-deployer-sa" "" "create" "deployments.apps" "finance-prod" "no" "Dev GitLab SA CANNOT deploy to finance-prod (Pipeline token isolation)"
assert_permission "system:serviceaccount:finance-prod:gitlab-deployer-sa" "" "create" "deployments.apps" "finance-prod" "yes" "Prod GitLab SA can deploy to finance-prod"

# ==============================================================================
# SUITE 5: Data Science / AI Analytics Persona
# ==============================================================================
echo -e "\n${BOLD}${CYAN}▶ Test Suite 5: Data Scientist Persona in Analytics Lab${NC}"
assert_permission "scientist-lead@example.com" "data-scientists-grp" "create" "jobs.batch" "analytics-lab" "yes" "Data Scientist can submit batch jobs in analytics-lab"
assert_permission "scientist-lead@example.com" "data-scientists-grp" "create" "pods" "analytics-lab" "yes" "Data Scientist can create pods in analytics-lab"
assert_permission "scientist-lead@example.com" "data-scientists-grp" "get" "pods" "finance-dev" "no" "Data Scientist CANNOT access finance-dev"
assert_permission "scientist-lead@example.com" "data-scientists-grp" "get" "pods" "finance-prod" "no" "Data Scientist CANNOT access finance-prod"

echo ""
echo -e "${BOLD}========================================================================================================${NC}"
echo -e "${BOLD}📊 Authorization Test Results: ${GREEN}${PASSED_TESTS} Passed${NC}, ${RED}${FAILED_TESTS} Failed${NC} (Total: ${TOTAL_TESTS})${NC}"
echo -e "${BOLD}========================================================================================================${NC}"

if [[ ${FAILED_TESTS} -gt 0 ]]; then
  echo -e "${RED}[WARN] Some RBAC permission tests failed. Ensure 'provision-rbac.py' has been applied.${NC}"
  exit 1
else
  echo -e "${GREEN}[SUCCESS] All RBAC boundaries, least-privilege rules, and tenant isolations verified!${NC}"
  exit 0
fi
