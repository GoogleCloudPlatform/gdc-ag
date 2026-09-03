# Lab 01: Multi-Tenant Landing Zone, Resource Quotas, and LimitRanges in Google Distributed Cloud (GDC)

## 📌 Overview & Learning Objectives

In an enterprise Google Distributed Cloud (GDC) deployment, the **Platform Administrator (PA)** is responsible for establishing a resilient, secure, and governed multi-tenant landing zone. Without strict capacity guardrails, unconstrained workloads can cause cluster-wide compute exhaustion, noisy-neighbor starvation, runaway infrastructure costs, and security boundary breaches.

In this lab, you will learn how to:
1. **Model Multi-Tenant Hierarchies**: Define isolated tenant namespaces representing distinct enterprise business units and lifecycle environments (`finance-dev`, `finance-prod`, and `analytics-lab`).
2. **Implement Multi-Tier ResourceQuotas**: Allocate bounded vCPU, memory, storage, object counts, hardware accelerators (NVIDIA GPUs), and network load balancers across different service tiers.
3. **Enforce Baseline Guardrails with LimitRanges**: Guarantee default CPU/memory requests and limits for unconfigured pods while establishing minimum and maximum sizing boundaries.
4. **Automate Landing Zone Provisioning**: Deploy declarative manifests manually and execute a production-grade Python automation engine ([`apply-landing-zone.py`](./scripts/apply-landing-zone.py)).
5. **Test Admission Controller Enforcement**: Intentionally trigger quota exhaustion and LimitRange violations to observe Kubernetes admission rejection mechanisms and event logs.
6. **Audit Live Cluster Capacity**: Run real-time quota verification tooling ([`verify-quotas.sh`](./scripts/verify-quotas.sh)) to evaluate consumption thresholds.

---

## 🏛️ Landing Zone Architecture & Tier Hierarchy

```
+---------------------------------------------------------------------------------------------------+
|                                 Google Distributed Cloud (GDC) Cluster                            |
+---------------------------------------------------------------------------------------------------+
                                                  |
         +----------------------------------------+----------------------------------------+
         |                                        |                                        |
         v                                        v                                        v
+---------------------------------+      +---------------------------------+      +---------------------------------+
| Namespace: finance-dev          |      | Namespace: finance-prod         |      | Namespace: analytics-lab        |
|---------------------------------|      |---------------------------------|      |---------------------------------|
| Tier: Standard Dev              |      | Tier: Mission-Critical Prod     |      | Tier: GPU Analytics Lab         |
| Cost Center: CC-FIN-1042        |      | Cost Center: CC-FIN-1042        |      | Cost Center: CC-DATA-8890       |
| Data Class: Internal            |      | Data Class: Restricted-Fin      |      | Data Class: Confidential-Data   |
|                                 |      |                                 |      |                                 |
| Compute Quota:                  |      | Compute Quota:                  |      | Compute Quota:                  |
|  - requests.cpu: 4 vCPU         |      |  - requests.cpu: 16 vCPU        |      |  - requests.cpu: 32 vCPU        |
|  - limits.cpu: 8 vCPU           |      |  - limits.cpu: 32 vCPU          |      |  - limits.cpu: 64 vCPU          |
|  - requests.memory: 8Gi         |      |  - requests.memory: 32Gi        |      |  - requests.memory: 64Gi        |
|  - limits.memory: 16Gi          |      |  - limits.memory: 64Gi          |      |  - limits.memory: 128Gi         |
|  - storage: 50Gi                |      |  - storage: 250Gi               |      |  - storage: 500Gi               |
|  - GPU: 0 (Disallowed)          |      |  - GPU: 0 (Disallowed)          |      |  - GPU: 4 NVIDIA GPUs           |
|  - LoadBalancers: 1             |      |  - LoadBalancers: 5             |      |  - LoadBalancers: 2             |
|                                 |      |                                 |      |                                 |
| LimitRange:                     |      | LimitRange:                     |      | LimitRange:                     |
|  - Default: 1 CPU / 2Gi         |      |  - Default: 2 CPU / 4Gi         |      |  - Default: 8 CPU / 16Gi        |
|  - DefaultReq: 250m / 512Mi     |      |  - DefaultReq: 500m / 1Gi       |      |  - DefaultReq: 1 CPU / 4Gi      |
|  - Min: 100m / 128Mi            |      |  - Min: 200m / 256Mi            |      |  - Min: 500m / 1Gi              |
|  - Max: 4 CPU / 8Gi             |      |  - Max: 8 CPU / 16Gi            |      |  - Max: 16 CPU / 32Gi / 2 GPU   |
+---------------------------------+      +---------------------------------+      +---------------------------------+
```

---

## 📁 Artifacts & File Map

All manifests and automation scripts for this lab are located in [`pa-track/lab-01-landing-zone-quotas/`](.):

| File Path | Description |
| :--- | :--- |
| [`manifests/01-projects.yaml`](./manifests/01-projects.yaml) | Declarative GDC project and namespace specifications with enterprise metadata labels. |
| [`manifests/02-resource-quotas.yaml`](./manifests/02-resource-quotas.yaml) | Multi-tier `ResourceQuota` policies (Standard Dev, Mission-Critical Prod, GPU Analytics). |
| [`manifests/03-limit-ranges.yaml`](./manifests/03-limit-ranges.yaml) | `LimitRange` guardrails enforcing default container requests, limits, and min/max constraints. |
| [`manifests/04-test-overquota-workload.yaml`](./manifests/04-test-overquota-workload.yaml) | Test workloads designed to intentionally trigger quota exhaustion and admission blocking. |
| [`scripts/projects_config.yaml`](./scripts/projects_config.yaml) | Central YAML configuration defining tenant project schemas, quotas, and baseline limits. |
| [`scripts/apply-landing-zone.py`](./scripts/apply-landing-zone.py) | Production-grade Python automation script validating configurations and provisioning the landing zone. |
| [`scripts/verify-quotas.sh`](./scripts/verify-quotas.sh) | Shell script calculating live tenant resource consumption vs hard limits in tabular format. |

---

## 🛠️ Step-by-Step Instructions

### Step 1: Initialize Environment & Verify Access

1. Open your terminal on the GDC sandbox workstation or bootstrapper.
2. Navigate to the repository directory and load the environment variables:
   ```bash
   cd ~/gdc-ag/gdc-sandbox-workshop
   source .env
   ```
3. Confirm cluster connectivity:
   ```bash
   kubectl cluster-info
   ```

---

### Step 2: Review Declarative Manifests

#### 1. Namespace Hierarchy ([`manifests/01-projects.yaml`](./manifests/01-projects.yaml))
Examine how governance labels are applied to track cost centers, data classifications, and lifecycle tiers:
```bash
cat pa-track/lab-01-landing-zone-quotas/manifests/01-projects.yaml
```

#### 2. ResourceQuotas ([`manifests/02-resource-quotas.yaml`](./manifests/02-resource-quotas.yaml))
Notice the three distinct service tiers:
- **`finance-dev`**: 4 vCPU requests / 8 vCPU limits, 8Gi memory, 1 LoadBalancer, 0 GPUs.
- **`finance-prod`**: 16 vCPU requests / 32 vCPU limits, 32Gi memory, 5 LoadBalancers, 0 GPUs.
- **`analytics-lab`**: 32 vCPU requests / 64 vCPU limits, 64Gi memory, 4 NVIDIA GPUs.

#### 3. LimitRanges ([`manifests/03-limit-ranges.yaml`](./manifests/03-limit-ranges.yaml))
Notice how `LimitRange` automatically applies default requests (e.g., `250m` CPU in dev) to any container submitted without explicit requests, preventing the container from failing quota admission.

---

### Step 3: Provision the Landing Zone

You can provision the landing zone using either the raw declarative manifests or the Python automation engine.

#### Method A: Using the Python Automation Script (Recommended)
The [`apply-landing-zone.py`](./scripts/apply-landing-zone.py) tool validates CPU/memory quantities, verifies that `min <= default <= max`, and deploys the entire configuration.

1. **Perform a Dry Run Validation**:
   ```bash
   python3 pa-track/lab-01-landing-zone-quotas/scripts/apply-landing-zone.py --dry-run
   ```
2. **Apply the Landing Zone**:
   ```bash
   python3 pa-track/lab-01-landing-zone-quotas/scripts/apply-landing-zone.py
   ```

#### Method B: Using `kubectl` Directly
Alternatively, apply the manifests in sequence:
```bash
kubectl apply -f pa-track/lab-01-landing-zone-quotas/manifests/01-projects.yaml
kubectl apply -f pa-track/lab-01-landing-zone-quotas/manifests/02-resource-quotas.yaml
kubectl apply -f pa-track/lab-01-landing-zone-quotas/manifests/03-limit-ranges.yaml
```

---

### Step 4: Verify Initial Quota Allocations

Run the quota verification utility to confirm that all three tenant namespaces are active with zero baseline utilization:

```bash
./pa-track/lab-01-landing-zone-quotas/scripts/verify-quotas.sh
```

**Sample Output:**
```
================================================================================
📊 GDC Tenant Resource Quota & Capacity Verification
================================================================================

NAMESPACE        RESOURCE                   USED         HARD         UTILIZATION  STATUS    
-----------------------------------------------------------------------------------------------
finance-dev      count/configmaps           0            30             0.0%       HEALTHY
finance-dev      count/deployments.apps     0            10             0.0%       HEALTHY
finance-dev      limits.cpu                 0            8              0.0%       HEALTHY
finance-dev      limits.memory              0            16Gi           0.0%       HEALTHY
finance-dev      pods                       0            10             0.0%       HEALTHY
finance-dev      requests.cpu               0            4              0.0%       HEALTHY
finance-dev      requests.memory            0            8Gi            0.0%       HEALTHY
finance-dev      requests.nvidia.com/gpu    0            0              0.0%       HEALTHY
finance-dev      services.loadbalancers     0            1              0.0%       HEALTHY
-----------------------------------------------------------------------------------------------
finance-prod     requests.cpu               0            16             0.0%       HEALTHY
finance-prod     requests.memory            0            32Gi           0.0%       HEALTHY
-----------------------------------------------------------------------------------------------
analytics-lab    requests.nvidia.com/gpu    0            4              0.0%       HEALTHY
-----------------------------------------------------------------------------------------------
```

---

### Step 5: Test Quota Exhaustion & Admission Rejection

Now, test that Kubernetes admission controllers and GDC quota controllers properly reject workloads that violate resource boundaries.

#### Test 1: CPU Quota Exhaustion in Development
In [`manifests/04-test-overquota-workload.yaml`](./manifests/04-test-overquota-workload.yaml), `overquota-cpu-app` requests 3 replicas of 2 vCPU each (total 6 vCPU requests), exceeding `finance-dev`'s 4 vCPU limit.

1. Attempt to deploy the over-quota deployment:
   ```bash
   kubectl apply -f pa-track/lab-01-landing-zone-quotas/manifests/04-test-overquota-workload.yaml
   ```
2. Check the Deployment and ReplicaSet status:
   ```bash
   kubectl get deployment overquota-cpu-app -n finance-dev
   kubectl describe rs -l app=overquota-cpu-app -n finance-dev
   ```
3. **Observe the Admission Failure in Events**:
   ```bash
   kubectl get events -n finance-dev --field-selector reason=FailedCreate
   ```
   **Expected Error Message:**
   ```
   Warning  FailedCreate  replicaset/overquota-cpu-app-...  Error creating: pods "overquota-cpu-app-..." is forbidden: exceeded quota: finance-dev-quota, requested: requests.cpu=2, used: requests.cpu=4, limited: requests.cpu=4
   ```

#### Test 2: Unauthorized GPU Request in Non-GPU Tenant
`unauthorized-gpu-pod` requests `nvidia.com/gpu: 1` in `finance-dev` where GPU quota is `0`.

1. Observe the Pod status:
   ```bash
   kubectl get pod unauthorized-gpu-pod -n finance-dev
   ```
2. **Expected Rejection Message:**
   ```
   Error from server (Forbidden): error when creating "...": pods "unauthorized-gpu-pod" is forbidden: exceeded quota: finance-dev-quota, requested: requests.nvidia.com/gpu=1, used: requests.nvidia.com/gpu=0, limited: requests.nvidia.com/gpu=0
   ```

#### Test 3: LoadBalancer Service Limit Breach
`test-lb-service-1` and `test-lb-service-2` request two `type: LoadBalancer` services where quota is `1`.

1. Check the services in `finance-dev`:
   ```bash
   kubectl get svc -n finance-dev
   ```
2. Notice that `test-lb-service-1` is created, while `test-lb-service-2` fails with:
   ```
   Forbidden: exceeded quota: finance-dev-quota, requested: services.loadbalancers=1, used: services.loadbalancers=1, limited: services.loadbalancers=1
   ```

---

### Step 6: Clean Up Test Workloads

Remove the violating test workloads:
```bash
kubectl delete -f pa-track/lab-01-landing-zone-quotas/manifests/04-test-overquota-workload.yaml --ignore-not-found
```

Re-run the verification script to ensure clean capacity:
```bash
./pa-track/lab-01-landing-zone-quotas/scripts/verify-quotas.sh -n finance-dev
```

---

## 🏆 Lab Summary & Platform Administrator Best Practices

1. **Always Pair ResourceQuota with LimitRange**: If a `ResourceQuota` requires CPU/memory limits, any pod without explicit `resources:` will be rejected at admission unless a `LimitRange` automatically injects default values.
2. **Enforce Overcommit Ratios Safely**: In development tiers, a 2:1 ratio (`limits.cpu` vs `requests.cpu`) enables cost-effective resource sharing. In mission-critical production tiers, keep the ratio closer to 1:1 or 1.5:1 to avoid CPU throttling under load spikes.
3. **Disallow Hardware Accelerators by Default**: Explicitly set `requests.nvidia.com/gpu: "0"` in standard application tiers to prevent accidental or unauthorized consumption of expensive GPU hardware pools.
4. **Restrict Ingress Anti-Patterns**: Set `services.nodeports: "0"` in tenant quotas to prevent developers from exposing unauthenticated direct node ports bypassing central ingress security gateways.

---
👉 **Next Lab**: Proceed to [Lab 02: Air-Gapped RBAC, Keycloak OIDC Integration, and Pipeline Identity Governance](../lab-02-rbac-and-identity/LAB-02.md).
