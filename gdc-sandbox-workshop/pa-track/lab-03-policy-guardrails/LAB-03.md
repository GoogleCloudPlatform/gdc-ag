# Module 3: Enforcing Enterprise Policy Guardrails with Policy Controller

## Overview

In a multi-tenant Google Distributed Cloud (GDC) Air-Gapped environment, the **Platform Administrator (PA)** is responsible for establishing enterprise compliance, platform security, and operational guardrails across all tenant clusters. 

Without centralized admission control, tenant teams could deploy vulnerable container images, request unbounded cluster compute, or mount host operating system filesystems, compromising workload isolation and compliance in air-gapped zones.

This lab provides hands-on experience configuring and operating **Policy Controller** (built on Open Policy Agent Gatekeeper) within GDC Air-Gapped. You will author declarative Constraint Templates using Rego, enforce constraints across tenant namespaces, and validate real-time admission rejection of non-compliant workloads.

---

## Learning Objectives

By completing this module, you will:
1. **Understand Policy Controller Architecture:** How Kubernetes Admission Webhooks intercept and evaluate workload specifications against Open Policy Agent (OPA) Rego rules.
2. **Deploy Reusable Constraint Templates:** Author Custom Resource Definitions (CRDs) that encapsulate validation logic for registry provenance, privilege escalation, volume isolation, and resource quotas.
3. **Apply Targeted Constraints:** Bind templates to tenant project namespaces while exempting core platform system namespaces.
4. **Test & Validate Guardrails:** Execute positive and negative test cases verifying that non-compliant workloads are blocked with descriptive violation messages.
5. **Automate Policy Operations:** Use deployment and validation scripts for CI/CD and platform bootstrapping.

---

## Policy Architecture in GDC Air-Gapped

```
+-----------------------------------------------------------------------------------+
|                              Kubernetes API Server                                |
|                                                                                   |
|  Tenant User / CI-CD       +-------------------------+      +------------------+  |
|  (kubectl apply -f pod) -> | Authentication / AuthZ  | ---> | Mutating Webhook |  |
|                            +-------------------------+      +------------------+  |
|                                                                      |            |
|                                                                      v            |
|                                                        +-----------------------+  |
|                                                        |   Validating Webhook  |  |
|                                                        | (Gatekeeper Admission)|  |
|                                                        +-----------------------+  |
+--------------------------------------------------------------------|--------------+
                                                                     |
                                  Evaluate Object against Constraints|
                                                                     v
                                                   +------------------------------------+
                                                   |      OPA / Policy Controller       |
                                                   |                                    |
                                                   | 1. Image Registry (Harbor only)    |
                                                   | 2. No Privileged / CAP_SYS_ADMIN   |
                                                   | 3. No hostPath Mounts              |
                                                   | 4. Explicit CPU / Memory Limits    |
                                                   +------------------------------------+
                                                          /                      \
                                               [DENY]    /                        \   [ALLOW]
                                                        v                          v
                                           +------------------------+    +--------------------+
                                           | Admission Rejected     |    | Persisted to etcd  |
                                           | (HTTP 403 Forbidden)   |    | (Pod Scheduled)    |
                                           +------------------------+    +--------------------+
```

### Core Security Guardrails

| Policy Name | Constraint Template | Purpose & Threat Mitigated |
| :--- | :--- | :--- |
| **Harbor Registry Only** | [`k8srequiredregistry`](./manifests/templates/k8srequiredregistry-template.yaml) | Blocks images from unauthorized or external registries. Enforces supply-chain trust and ensures images pass internal Harbor Trivy vulnerability scanning. |
| **Disallow Privileged** | [`k8sdisallowprivileged`](./manifests/templates/k8sdisallowprivileged-template.yaml) | Prevents containers from running with `privileged: true`, `allowPrivilegeEscalation: true`, or sensitive capabilities like `CAP_SYS_ADMIN`. |
| **Disallow HostPath** | [`k8sdisallowhostpath`](./manifests/templates/k8sdisallowhostpath-template.yaml) | Forbids pods from mounting host node directories (`hostPath`), preventing breakout attacks and container-to-host file access. |
| **Require Resource Limits** | [`k8srequiredresources`](./manifests/templates/k8srequiredresources-template.yaml) | Mandates both CPU/memory requests and limits on every container, preventing noisy-neighbor starvation and ensuring QoS. |

---

## Lab Artifacts & Manifests

- **Constraint Templates:**
  - [`k8srequiredregistry-template.yaml`](./manifests/templates/k8srequiredregistry-template.yaml)
  - [`k8sdisallowprivileged-template.yaml`](./manifests/templates/k8sdisallowprivileged-template.yaml)
  - [`k8sdisallowhostpath-template.yaml`](./manifests/templates/k8sdisallowhostpath-template.yaml)
  - [`k8srequiredresources-template.yaml`](./manifests/templates/k8srequiredresources-template.yaml)
- **Constraints:**
  - [`require-harbor-registry.yaml`](./manifests/constraints/require-harbor-registry.yaml)
  - [`disallow-privileged.yaml`](./manifests/constraints/disallow-privileged.yaml)
  - [`disallow-hostpath.yaml`](./manifests/constraints/disallow-hostpath.yaml)
  - [`require-resource-limits.yaml`](./manifests/constraints/require-resource-limits.yaml)
- **Test Workloads:**
  - [`bad-privileged-pod.yaml`](./manifests/test-workloads/bad-privileged-pod.yaml)
  - [`bad-external-image.yaml`](./manifests/test-workloads/bad-external-image.yaml)
  - [`good-compliant-app.yaml`](./manifests/test-workloads/good-compliant-app.yaml)
- **Automation Scripts:**
  - [`deploy-guardrails.sh`](./scripts/deploy-guardrails.sh)
  - [`test-policies.sh`](./scripts/test-policies.sh)

---

## Hands-On Lab Walkthrough

### Step 1: Environment Login & Context Check

Authenticate and verify cluster connectivity:

```bash
cd ~/gdc-ag/gdc-sandbox-workshop
source .env
login

# Verify target user cluster
ku get nodes
```

---

### Step 2: Review Constraint Template Logic

Inspect the ConstraintTemplate for the trusted registry rule:

```bash
cat pa-track/lab-03-policy-guardrails/manifests/templates/k8srequiredregistry-template.yaml
```

Notice the Rego rule:
```rego
package k8srequiredregistry

violation[{"msg": msg}] {
  container := get_containers[_]
  satisfied := [good | repo := input.parameters.registries[_]; good := startswith(container.image, repo)]
  not any(satisfied)
  msg := sprintf("Container '%v' has an untrusted image '%v'. Images must originate from an approved registry prefix: %v", [container.name, container.image, input.parameters.registries])
}
```

This ensures that every container (including init containers and ephemeral containers) must have an image path beginning with one of the approved registry prefixes passed via parameters.

---

### Step 3: Deploy Policy Guardrails

Execute the deployment script to apply all Constraint Templates and wait for Gatekeeper to generate the underlying Custom Resource Definitions before applying the Constraints:

```bash
cd pa-track/lab-03-policy-guardrails/scripts
chmod +x deploy-guardrails.sh test-policies.sh
./deploy-guardrails.sh
```

**Expected Output:**
```text
============================================================
 GDC Air-Gapped: Policy Controller Guardrails Deployment
============================================================
▶ Step 1: Applying Gatekeeper ConstraintTemplates...
  Applying template: k8sdisallowhostpath-template.yaml
  Applying template: k8sdisallowprivileged-template.yaml
  Applying template: k8srequiredregistry-template.yaml
  Applying template: k8srequiredresources-template.yaml

▶ Step 2: Waiting for Constraint CRDs to be registered...
  Waiting for CRD k8srequiredregistries.constraints.gatekeeper.sh... Ready!
  Waiting for CRD k8sdisallowprivilegeds.constraints.gatekeeper.sh... Ready!
  Waiting for CRD k8sdisallowhostpaths.constraints.gatekeeper.sh... Ready!
  Waiting for CRD k8srequiredresources.constraints.gatekeeper.sh... Ready!

▶ Step 3: Applying Enterprise Policy Constraints...
  Applying constraint: disallow-hostpath.yaml
  Applying constraint: disallow-privileged.yaml
  Applying constraint: require-harbor-registry.yaml
  Applying constraint: require-resource-limits.yaml
============================================================
```

Verify that the active constraints are recognized by the cluster:

```bash
ku get constraints
```

---

### Step 4: Test Negative Case 1 - Privileged Pod & HostPath Mount

Attempt to deploy [`bad-privileged-pod.yaml`](./manifests/test-workloads/bad-privileged-pod.yaml) which requests `privileged: true`, `CAP_SYS_ADMIN`, a `/var/run/docker.sock` `hostPath` mount, and has no resource limits:

```bash
ku apply -f ../manifests/test-workloads/bad-privileged-pod.yaml
```

**Expected Admission Controller Output:**
```text
Error from server (Forbidden): error when creating "../manifests/test-workloads/bad-privileged-pod.yaml": 
admission webhook "validation.gatekeeper.sh" denied the request: 
[disallow-privileged] Container 'privileged-container' is running in privileged mode (securityContext.privileged: true), which is strictly prohibited.
[disallow-privileged] Container 'privileged-container' specifies forbidden Linux capability 'SYS_ADMIN'.
[disallow-hostpath] Volume 'host-docker-sock' uses forbidden hostPath volume source '/var/run/docker.sock'. HostPath mounts are strictly disallowed in GDC tenant namespaces.
[require-resource-limits] Container 'privileged-container' is missing required resource definition 'resources.requests.cpu'.
```

The request is rejected at the API server before any pod or container process is created.

---

### Step 5: Test Negative Case 2 - External Image Registry

Attempt to deploy [`bad-external-image.yaml`](./manifests/test-workloads/bad-external-image.yaml) which pulls directly from `docker.io/library/nginx`:

```bash
ku apply -f ../manifests/test-workloads/bad-external-image.yaml
```

**Expected Admission Controller Output:**
```text
Error from server (Forbidden): error when creating "../manifests/test-workloads/bad-external-image.yaml": 
admission webhook "validation.gatekeeper.sh" denied the request: 
[require-harbor-registry] Container 'nginx-external' has an untrusted image 'docker.io/library/nginx:1.25.4'. Images must originate from an approved registry prefix: ["harbor.zone1.google.gdch.test/"]
```

---

### Step 6: Test Positive Case - Compliant Application

Deploy the compliant application [`good-compliant-app.yaml`](./manifests/test-workloads/good-compliant-app.yaml) which satisfies all four guardrails:

```bash
ku apply -f ../manifests/test-workloads/good-compliant-app.yaml
```

**Expected Output:**
```text
deployment.apps/secure-frontend-app created
service/secure-frontend-app created
```

Inspect the deployed workload:
```bash
ku get pods -l app=secure-frontend
ku get deployment secure-frontend-app
```

---

### Step 7: Run Automated Test Suite

Run the full automated test suite to verify all guardrail admission rules:

```bash
./test-policies.sh
```

**Expected Output:**
```text
============================================================
 GDC Air-Gapped: Policy Controller Admission Tests
============================================================
TEST #1: [NEGATIVE] Disallow Privileged / HostPath / Resource Limits Enforcement
✔ PASS: Workload was rejected as expected by Policy Controller.

TEST #2: [NEGATIVE] Require Approved Harbor Registry Enforcement
✔ PASS: Workload was rejected as expected by Policy Controller.

TEST #3: [POSITIVE] Compliant Tenant Application Deployment
✔ PASS: Compliant workload passed admission control successfully.

============================================================
 POLICY TEST SUMMARY
============================================================
 Total Tests:  3
 Passed Tests: 3
 Failed Tests: 0
============================================================
🎉 All policy guardrail admission tests PASSED!
```

---

## Clean Up

To clean up the test resources:

```bash
ku delete -f ../manifests/test-workloads/good-compliant-app.yaml --ignore-not-found=true
```

---

## Summary & Platform Admin Key Takeaways

1. **Shift Security Left:** Admission control prevents non-compliant workloads from ever reaching worker nodes, eliminating runtime attack surfaces.
2. **Standardize on Internal Harbor:** Restricting image registries guarantees all production images are scanned for CVEs by Harbor Trivy and subject to retention governance.
3. **Enforce Least Privilege by Default:** Removing `privileged` access and `hostPath` volumes ensures strong multi-tenant kernel separation.
4. **Protect Platform Capacity:** Mandating CPU and memory requests/limits guarantees Kubernetes QoS predictability.
