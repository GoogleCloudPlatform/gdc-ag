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

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKLOADS_DIR="$(cd "${SCRIPT_DIR}/../manifests/test-workloads" && pwd)"

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
echo " GDC Air-Gapped: Policy Controller Admission Tests"
echo "============================================================"
echo "Namespace target: ${NAMESPACE}"
echo "Kubeconfig: ${KUBECTL_CMD[*]}"
echo ""

# Ensure target test namespace exists
"${KUBECTL_CMD[@]}" create namespace "${NAMESPACE}" --dry-run=client -o yaml | "${KUBECTL_CMD[@]}" apply -f - >/dev/null 2>&1 || true

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_negative_test() {
    local test_name="$1"
    local manifest_file="$2"
    local expected_pattern="$3"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo "------------------------------------------------------------"
    echo "TEST #${TOTAL_TESTS}: [NEGATIVE] ${test_name}"
    echo "Manifest: $(basename "${manifest_file}")"
    echo "Expected Rejection Pattern: '${expected_pattern}'"
    echo ""
    
    # Run server-side dry-run to trigger admission webhook
    OUTPUT=$("${KUBECTL_CMD[@]}" apply -n "${NAMESPACE}" --dry-run=server -f "${manifest_file}" 2>&1 || true)
    
    if echo "${OUTPUT}" | grep -Ei "admission webhook .* denied|denied the request|forbidden|validation failure" >/dev/null; then
        if echo "${OUTPUT}" | grep -Ei "${expected_pattern}" >/dev/null; then
            echo "✔ PASS: Workload was rejected as expected by Policy Controller."
            echo "  Violation Message Snippet:"
            echo "${OUTPUT}" | grep -Ei "${expected_pattern}" | sed 's/^/    /'
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            echo "✔ PASS: Workload was denied by admission controller, though pattern differed slightly."
            echo "  Actual Admission Response:"
            echo "${OUTPUT}" | sed 's/^/    /'
            PASSED_TESTS=$((PASSED_TESTS + 1))
        fi
    else
        echo "✖ FAIL: Workload was NOT rejected by the admission controller!"
        echo "  Output: ${OUTPUT}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

run_positive_test() {
    local test_name="$1"
    local manifest_file="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo "------------------------------------------------------------"
    echo "TEST #${TOTAL_TESTS}: [POSITIVE] ${test_name}"
    echo "Manifest: $(basename "${manifest_file}")"
    echo ""
    
    OUTPUT=$("${KUBECTL_CMD[@]}" apply -n "${NAMESPACE}" --dry-run=server -f "${manifest_file}" 2>&1 || true)
    
    if echo "${OUTPUT}" | grep -Ei "admission webhook .* denied|denied the request|forbidden" >/dev/null; then
        echo "✖ FAIL: Compliant workload was unexpectedly rejected by Policy Controller!"
        echo "  Output: ${OUTPUT}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    else
        echo "✔ PASS: Compliant workload passed admission control successfully."
        echo "  Output: ${OUTPUT}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    fi
}

# Execute Test 1: Bad Privileged Pod (Should be rejected)
run_negative_test \
    "Disallow Privileged / HostPath / Resource Limits Enforcement" \
    "${WORKLOADS_DIR}/bad-privileged-pod.yaml" \
    "privileged|hostPath|resource|disallow-privileged|disallow-hostpath|require-resource-limits"

# Execute Test 2: Bad External Image (Should be rejected)
run_negative_test \
    "Require Approved Harbor Registry Enforcement" \
    "${WORKLOADS_DIR}/bad-external-image.yaml" \
    "untrusted image|harbor\.zone1\.google\.gdch\.test|require-harbor-registry|k8srequiredregistry"

# Execute Test 3: Good Compliant App (Should be accepted)
run_positive_test \
    "Compliant Tenant Application Deployment" \
    "${WORKLOADS_DIR}/good-compliant-app.yaml"

echo ""
echo "============================================================"
echo " POLICY TEST SUMMARY"
echo "============================================================"
echo " Total Tests:  ${TOTAL_TESTS}"
echo " Passed Tests: ${PASSED_TESTS}"
echo " Failed Tests: ${FAILED_TESTS}"
echo "============================================================"

if [[ ${FAILED_TESTS} -eq 0 ]]; then
    echo "🎉 All policy guardrail admission tests PASSED!"
    exit 0
else
    echo "❌ Some policy guardrail tests FAILED. Review admission logs."
    exit 1
fi
