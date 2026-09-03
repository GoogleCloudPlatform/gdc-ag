# Lab 05: Zero-Trust Network Isolation and LoadBalancer VIP Management

## Overview & Architecture

In Google Distributed Cloud (GDC) Air-Gapped environments, workloads from multiple organizational units and projects share common physical and virtual infrastructure. Ensuring strict multi-tenant boundary enforcement requires a **Zero-Trust Network Architecture**.

Platform Administrators are responsible for establishing baseline isolation policies that prevent lateral movement, data exfiltration, and unauthorized inter-tenant communication while enabling controlled microservice access and external ingress via dedicated virtual IP (VIP) pools.

```
                      +-------------------------------------------------------------+
                      |                 GDC Air-Gapped Cluster                     |
                      |                                                             |
                      |   +-------------------+             +-------------------+   |
                      |   | tenant-a          |             | tenant-b          |   |
                      |   |  (Frontend App)   |             | (Isolated App)    |   |
                      |   |    [client-a]     |             |    [client-b]     |   |
                      |   +---------+---------+             +---------+---------+   |
                      |             |                                 |             |
                      |             | (Allowed TCP 8080)              | (BLOCKED)   |
                      |             v                                 v             |
                      |   +-----------------------------------------------------+   |
                      |   |                 shared-services                     |   |
                      |   |                [shared-backend]                     |   |
                      |   +-----------------------------------------------------+   |
                      |                                                             |
                      |   +-----------------------------------------------------+   |
                      |   |                 MetalLB VIP Pools                   |   |
                      |   |   Frontend VIP Pool: 192.168.10.200 - 192.168.10.220|   |
                      |   |   Shared Svc Pool  : 192.168.10.221 - 192.168.10.240|   |
                      |   +-----------------------------------------------------+   |
                      +-------------------------------------------------------------+
```

### Key Learning Objectives
1. **Understand Zero-Trust in GDC**: Understand how NetworkPolicies enforce packet filtering at the CNI layer across tenant projects.
2. **Implement Baseline Default-Deny**: Apply strict ingress and egress deny rules while maintaining cluster-essential DNS resolution.
3. **Configure Intra-Namespace Routing**: Enable unrestricted pod-to-pod communication within isolated tenant boundaries.
4. **Establish Cross-Tenant Service Contracts**: Author precise cross-namespace ingress/egress rules allowing specific workloads to talk over designated ports.
5. **Manage LoadBalancer VIP Pools**: Configure MetalLB `IPAddressPool` and `L2Advertisement` to dedicate isolated IP ranges for tenant ingress.
6. **Automate Policy Verification**: Execute end-to-end network probes to mathematically prove isolation and contract enforcement.

---

## Lab Artifacts & Manifests

All manifests and helper scripts are located in this directory:
- [manifests/01-default-deny-networkpolicy.yaml](./manifests/01-default-deny-networkpolicy.yaml) - Baseline default-deny policy with DNS whitelist.
- [manifests/02-allow-same-namespace.yaml](./manifests/02-allow-same-namespace.yaml) - Policy permitting intra-namespace pod communication.
- [manifests/03-allow-cross-tenant-service.yaml](./manifests/03-allow-cross-tenant-service.yaml) - Cross-tenant service contract for frontend -> backend.
- [manifests/04-loadbalancer-vip-pool.yaml](./manifests/04-loadbalancer-vip-pool.yaml) - MetalLB VIP address pools and Layer 2 advertisement.
- [manifests/test-workloads/isolated-tenant-a.yaml](./manifests/test-workloads/isolated-tenant-a.yaml) - Tenant A probe workload.
- [manifests/test-workloads/isolated-tenant-b.yaml](./manifests/test-workloads/isolated-tenant-b.yaml) - Tenant B isolated workload.
- [manifests/test-workloads/shared-backend.yaml](./manifests/test-workloads/shared-backend.yaml) - Shared service HTTP backend.
- [scripts/apply-network-security.sh](./scripts/apply-network-security.sh) - Automated rollout script for network policies.
- [scripts/test-network-isolation.sh](./scripts/test-network-isolation.sh) - Automated probe script verifying connectivity matrix.

---

## Step-by-Step Exercise

### Step 1: Prepare Environment and Context

Ensure you are logged into your GDC sandbox cluster and have loaded your environment variables:

```bash
cd ~/gdc-ag/gdc-sandbox-workshop
source .env
login
```

Verify your cluster connection:
```bash
ku get nodes
```

---

### Step 2: Deploy Test Workloads

Deploy the three test workloads representing distinct tenant environments:
1. `tenant-a`: Simulating frontend client workloads.
2. `tenant-b`: Simulating an isolated third-party tenant workload.
3. `shared-services`: Simulating a shared platform backend service.

```bash
ku apply -f pa-track/lab-05-network-isolation/manifests/test-workloads/isolated-tenant-a.yaml
ku apply -f pa-track/lab-05-network-isolation/manifests/test-workloads/isolated-tenant-b.yaml
ku apply -f pa-track/lab-05-network-isolation/manifests/test-workloads/shared-backend.yaml
```

Wait for all probe pods to reach `Running` state:
```bash
ku get pods -A -l 'tier in (frontend, isolated, backend)'
```

---

### Step 3: Apply Zero-Trust Network Policies

Execute the policy application script to rollout:
- The baseline Default-Deny rule.
- Intra-namespace communication rules.
- Explicit cross-tenant service rules.
- MetalLB VIP pools.

```bash
./pa-track/lab-05-network-isolation/scripts/apply-network-security.sh
```

Inspect the active NetworkPolicies across all tenant namespaces:
```bash
ku get networkpolicy -A
```

Output:
```
NAMESPACE         NAME                         POD-SELECTOR   AGE
backend-api-project allow-ingress-from-frontend app=backend-api 12s
frontend-project  allow-egress-to-backend-api  app=frontend   12s
shared-services   allow-ingress-shared-services app=shared-backend 12s
tenant-a          default-deny-all-traffic     <none>         12s
tenant-a          allow-same-namespace         <none>         12s
tenant-b          default-deny-all-traffic     <none>         12s
tenant-b          allow-same-namespace         <none>         12s
```

---

### Step 4: Configure Dedicated LoadBalancer VIP Pools

Review [manifests/04-loadbalancer-vip-pool.yaml](./manifests/04-loadbalancer-vip-pool.yaml).

In GDC Air-Gapped, MetalLB coordinates with the underlying physical switches (via BGP or Layer 2 ARP/NDP). Defining explicit `IPAddressPool` resources ensures that:
- Critical shared services receive IP addresses from a predictable range (`192.168.10.221-192.168.10.240`).
- Tenant frontends consume from a segregated pool (`192.168.10.200-192.168.10.220`), preventing IP starvation and aiding upstream firewall auditing.

Apply the VIP pool:
```bash
ku apply -f pa-track/lab-05-network-isolation/manifests/04-loadbalancer-vip-pool.yaml
```

Verify the address pool allocation:
```bash
ku get ipaddresspools.metallb.io -n metallb-system
ku get l2advertisements.metallb.io -n metallb-system
```

---

### Step 5: Execute Automated Network Isolation Verification

Run the automated probe script to test every path in the connectivity matrix:

```bash
./pa-track/lab-05-network-isolation/scripts/test-network-isolation.sh
```

If you are running in an environment without direct live cluster access, you can run with `--mock` to simulate the exact matrix:
```bash
./pa-track/lab-05-network-isolation/scripts/test-network-isolation.sh --mock
```

Expected Output:
```
==================================================================================
  GDC Air-Gapped Network Isolation Matrix & Policy Verification Probe
==================================================================================
  Mode: LIVE CLUSTER PROBE / SIMULATED
  Probe Timeout: 4s
----------------------------------------------------------------------------------
Test 1 : CoreDNS / Kube-DNS Resolution (tenant-a -> kube-dns)    ... PASS [DNS query resolved in 4ms - Expected: ALLOW, Got: ALLOW]
Test 2 : Intra-Tenant Communication (tenant-a -> client-a service) ... PASS [HTTP 200 OK (same namespace) - Expected: ALLOW, Got: ALLOW]
Test 3 : Cross-Tenant Isolation (tenant-a -> tenant-b service)   ... PASS [Connection timed out (policy drop) - Expected: DENY, Got: DENY]
Test 4 : Cross-Tenant Authorized Ingress (tenant-a -> shared-backend) ... PASS [HTTP 200 OK (cross-tenant rule active) - Expected: ALLOW, Got: ALLOW]
Test 5 : Cross-Tenant Unauthorized Ingress (tenant-b -> shared-backend) ... PASS [Connection timed out (cross-tenant blocked) - Expected: DENY, Got: DENY]
----------------------------------------------------------------------------------
Isolation Test Summary:
  Total Tests Executed : 5
  Passed               : 5
  Failed               : 0

✓ SUCCESS: Zero-Trust Network Isolation verification completed with zero policy leaks.
```

---

## Troubleshooting & Administrator Pitfalls

| Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| **DNS Lookups Fail in Tenant Pods** | Default-deny egress blocks UDP 53 to `kube-system`. | Verify `01-default-deny-networkpolicy.yaml` contains the `kube-dns` / `coredns` namespaceSelector and port 53 UDP/TCP rules. |
| **Cross-Tenant Connection Drops** | Mismatch in namespace labels or pod selector labels. | Check `kubectl get ns --show-labels` and verify `kubernetes.io/metadata.name` matches the `namespaceSelector`. |
| **Pending LoadBalancer Services** | Exhaustion in MetalLB `IPAddressPool` range or missing `L2Advertisement`. | Run `kubectl describe ipaddresspool -n metallb-system` and ensure the service's requested pool has free addresses. |
| **Hairpin NAT / Inter-pod Latency** | Missing intra-namespace allow rule causing packet drops on loopback. | Ensure `02-allow-same-namespace.yaml` is applied to every tenant namespace. |

---

## Summary

You have successfully established a zero-trust network perimeter across multi-tenant workloads in GDC Air-Gapped:
1. Enforced default-deny isolation to prevent unauthorized lateral traversal.
2. Preserved control-plane and DNS service discovery.
3. Implemented least-privilege cross-tenant service contracts.
4. Partitioned external LoadBalancer VIPs using MetalLB pools.
5. Proven network compliance using automated probing tools.
