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
# verify-quotas.sh
# ----------------
# Verifies real-time resource consumption against hard limits across
# GDC tenant namespaces, highlighting utilization rates and capacity alerts.
# ==============================================================================

set -euo pipefail

# ANSI Color Codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

KUBECONFIG_FLAG=""
TARGET_NS=""
DEFAULT_NAMESPACES=("finance-dev" "finance-prod" "analytics-lab")

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  -n, --namespace <ns>   Verify quota for a specific namespace only"
  echo "  -k, --kubeconfig <path> Specify path to kubeconfig file"
  echo "  -h, --help             Display this help message"
  echo ""
  echo "Examples:"
  echo "  $0"
  echo "  $0 -n finance-dev"
  echo "  $0 --kubeconfig ~/.kube/gdc-config"
  exit 0
}

# Parse Command-line Arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--namespace)
      TARGET_NS="$2"
      shift 2
      ;;
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

# Check kubectl availability
if ! command -v kubectl &> /dev/null; then
  echo -e "${RED}[ERROR] 'kubectl' binary not found in PATH.${NC}"
  exit 1
fi

echo -e "${BOLD}================================================================================${NC}"
echo -e "${BOLD}📊 GDC Tenant Resource Quota & Capacity Verification${NC}"
echo -e "${BOLD}================================================================================${NC}"

NAMESPACES_TO_CHECK=()
if [[ -n "${TARGET_NS}" ]]; then
  NAMESPACES_TO_CHECK+=("${TARGET_NS}")
else
  # Discover or use defaults
  for ns in "${DEFAULT_NAMESPACES[@]}"; do
    if kubectl ${KUBECONFIG_FLAG} get namespace "${ns}" &> /dev/null; then
      NAMESPACES_TO_CHECK+=("${ns}")
    fi
  done
  if [[ ${#NAMESPACES_TO_CHECK[@]} -eq 0 ]]; then
    # Fallback to all namespaces with a quota
    mapfile -t NAMESPACES_TO_CHECK < <(kubectl ${KUBECONFIG_FLAG} get resourcequota -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\n"}{end}' | sort -u)
  fi
fi

if [[ ${#NAMESPACES_TO_CHECK[@]} -eq 0 ]]; then
  echo -e "${YELLOW}[WARN] No namespaces with ResourceQuotas found.${NC}"
  exit 0
fi

# Print Table Header
printf "\n${BOLD}%-16s %-26s %-12s %-12s %-12s %-10s${NC}\n" "NAMESPACE" "RESOURCE" "USED" "HARD" "UTILIZATION" "STATUS"
printf "%s\n" "-----------------------------------------------------------------------------------------------"

for ns in "${NAMESPACES_TO_CHECK[@]}"; do
  quotas=$(kubectl ${KUBECONFIG_FLAG} get resourcequota -n "${ns}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
  
  if [[ -z "${quotas}" ]]; then
    printf "%-16s %-26s %-12s %-12s %-12s %-10s\n" "${ns}" "(No Quota Configured)" "-" "-" "-" "${YELLOW}UNBOUND${NC}"
    continue
  fi

  for q in ${quotas}; do
    # Extract hard and used metrics
    hard_keys=$(kubectl ${KUBECONFIG_FLAG} get resourcequota "${q}" -n "${ns}" -o jsonpath='{range .status.hard}{@}{"\n"}{end}' 2>/dev/null || true)
    
    # Process key resources with python helper for clean arithmetic
    python3 -c "
import subprocess, json, sys

ns = '${ns}'
q = '${q}'
k_flag = '${KUBECONFIG_FLAG}'.split() if '${KUBECONFIG_FLAG}' else []

cmd = ['kubectl'] + k_flag + ['get', 'resourcequota', q, '-n', ns, '-o', 'json']
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    hard = data.get('status', {}).get('hard', {})
    used = data.get('status', {}).get('used', {})

    def parse_unit(v):
        if not v: return 0.0
        v = str(v).strip()
        if v.endswith('m'): return float(v[:-1])/1000.0
        if v.endswith('Ki'): return float(v[:-2])*1024
        if v.endswith('Mi'): return float(v[:-2])*1024*1024
        if v.endswith('Gi'): return float(v[:-2])*1024*1024*1024
        if v.endswith('Ti'): return float(v[:-2])*1024*1024*1024*1024
        try: return float(v)
        except: return 0.0

    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    GREEN = '\033[0;32m'
    NC = '\033[0m'

    for rk in sorted(hard.keys()):
        h_val = hard[rk]
        u_val = used.get(rk, '0')
        h_num = parse_unit(h_val)
        u_num = parse_unit(u_val)
        
        if h_num > 0:
            pct = (u_num / h_num) * 100.0
            pct_str = f'{pct:5.1f}%'
            if pct >= 95.0:
                status = f'{RED}CRITICAL{NC}'
            elif pct >= 75.0:
                status = f'{YELLOW}WARNING{NC}'
            else:
                status = f'{GREEN}HEALTHY{NC}'
        else:
            pct_str = 'N/A'
            status = f'{GREEN}HEALTHY{NC}'

        print(f'{ns:<16} {rk:<26} {u_val:<12} {h_val:<12} {pct_str:<12} {status}')
except Exception as e:
    print(f'{ns:<16} {q:<26} ERROR: {e}', file=sys.stderr)
"
  done
  printf "%s\n" "-----------------------------------------------------------------------------------------------"
done

echo ""
echo -e "${CYAN}[TIP]${NC} To inspect detailed event logs for quota admission rejections, run:"
echo -e "      ${BOLD}kubectl get events -n <namespace> --field-selector reason=FailedCreate${NC}"
echo ""
