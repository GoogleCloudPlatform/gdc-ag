# Lab 06: Platform Auditing, Compliance Tracking, and Tenant Resource Utilization Metering

## Overview & Architecture

In mission-critical and highly regulated Google Distributed Cloud (GDC) Air-Gapped deployments, Platform Administrators must maintain continuous visibility over:
1. **Security & Compliance Auditing**: Tracking all administrative actions, IAM role modifications, secret accesses, and unauthorized policy tampering across tenant boundaries.
2. **Multi-Tenant Resource Metering**: Monitoring compute (vCPU), memory (GiB), and persistent storage (GiB) consumption per project to enforce capacity quotas, prevent starvation, and generate chargeback reports.

```
       +-----------------------------------------------------------------------------+
       |                         GDC Air-Gapped Control Plane                        |
       |                                                                             |
       |  +--------------------+     Audit Events     +---------------------------+  |
       |  | kube-apiserver     | ===================> | GDC Platform Audit Engine |  |
       |  |  - RBAC Mutations  |                      |  - RequestResponse Tiers  |  |
       |  |  - Secret Accesses |                      |  - Centralized SIEM Sink  |  |
       |  +--------------------+                      +-------------+-------------+  |
       |                                                            |                |
       |                                                            v                |
       |                                              [inspect-audit-logs.py]        |
       |                                                                             |
       |  +--------------------+     Kube Metrics     +---------------------------+  |
       |  | Kubelet / CAdvisor | ===================> | Prometheus / Monarch      |  |
       |  |  - CPU Usage/Req   |                      |  - Recording Rules        |  |
       |  |  - Memory WorkSet  |                      |  - Saturation Alerts      |  |
       |  |  - PVC Storage     |                      +-------------+-------------+  |
       |  +--------------------+                                    |                |
       |                                                            v                |
       |                                              [calculate-tenant-metering.py] |
       +-----------------------------------------------------------------------------+
```

### Key Learning Objectives
1. **Configure GDC API Audit Policy**: Define audit log levels (`RequestResponse`, `Metadata`, `None`) to capture security-sensitive events without saturating disk I/O.
2. **Establish Centralized Audit Sinks**: Route compliance audit logs to secure air-gapped SIEM and long-term immutable object storage vaults.
3. **Forensic Security Inspection**: Use `inspect-audit-logs.py` to identify privilege escalation attempts, secret probing, and security policy tampering.
4. **Deploy Multi-Tenant Prometheus Recording Rules**: Aggregate per-tenant resource metrics (`tenant:cpu_usage_rate:cores`, `tenant:memory_working_set:bytes`, `tenant:storage_pvc_requested:bytes`).
5. **Compute Tenant Metering & Quota Headroom**: Generate chargeback and allocation unit reports using `calculate-tenant-metering.py` to support capacity planning.

---

## Lab Artifacts & Manifests

All manifests and tools are located in this directory:
- [manifests/01-audit-sink-config.yaml](./manifests/01-audit-sink-config.yaml) - Kubernetes audit policy and centralized SIEM/storage export sink configuration.
- [manifests/02-metering-prometheus-rules.yaml](./manifests/02-metering-prometheus-rules.yaml) - Prometheus/Monarch recording rules and quota exhaustion alert definitions.
- [scripts/inspect-audit-logs.py](./scripts/inspect-audit-logs.py) - CLI inspection tool detecting security violations and IAM anomalies.
- [scripts/calculate-tenant-metering.py](./scripts/calculate-tenant-metering.py) - Resource utilization, quota headroom, and chargeback calculation engine.

---

## Step-by-Step Exercise

### Step 1: Review and Apply Audit Policy Configuration

Review the audit policy tiers in [manifests/01-audit-sink-config.yaml](./manifests/01-audit-sink-config.yaml).

In GDC Air-Gapped:
- **`RequestResponse` Level**: Captures complete request and response payloads for critical mutations (e.g. creating `ClusterRoleBindings`, altering `NetworkPolicies`, accessing `Secrets`, or invoking `pods/exec`).
- **`Metadata` Level**: Records timestamps, user identities, namespaces, and HTTP response codes for normal workload creation (`Deployments`, `StatefulSets`, `PersistentVolumeClaims`).
- **`None` Level**: Suppresses high-frequency health probes (`/healthz`, `/livez`) and leader election leases.

Apply the audit sink configuration:
```bash
ku apply -f pa-track/lab-06-audit-and-metering/manifests/01-audit-sink-config.yaml
```

---

### Step 2: Run Audit Security & Compliance Inspection

Execute the audit inspection tool to query security events:

```bash
./pa-track/lab-06-audit-and-metering/scripts/inspect-audit-logs.py
```

To filter for high/critical security events only:
```bash
./pa-track/lab-06-audit-and-metering/scripts/inspect-audit-logs.py --severity HIGH
```

To output results as Markdown for inclusion in security compliance tickets:
```bash
./pa-track/lab-06-audit-and-metering/scripts/inspect-audit-logs.py --format markdown
```

Sample Output:
```
==============================================================================================================
  GDC Air-Gapped Platform Security & Compliance Audit Log Inspector
==============================================================================================================
  Total Events Analyzed: 5 | Filter Minimum Severity: HIGH
  Critical: 0 | High: 3 | Medium: 1 | Low: 0 | Info: 1
--------------------------------------------------------------------------------------------------------------
Timestamp           | Sev      | Rule                                 | Tenant           | User                   | Status
--------------------------------------------------------------------------------------------------------------------------
2026-08-10 23:49:57 | HIGH     | UNAUTHORIZED_PRIVILEGE_ESCALATION_ATTEMPT | cluster-wide     | contractor-dev@tenant- | 403   
2026-08-10 23:53:57 | HIGH     | UNAUTHORIZED_SECRET_ACCESS_DENIED    | shared-services  | suspicious-service-acc | 403   
2026-08-10 23:57:57 | HIGH     | UNAUTHORIZED_NETWORK_POLICY_TAMPERING | tenant-a         | developer-user@tenant- | 403   
==============================================================================================================
⚠️  SECURITY ACTION REQUIRED: Unauthorized privilege escalation or policy tampering detected!
```

---

### Step 3: Deploy Prometheus Multi-Tenant Metering Rules

Review [manifests/02-metering-prometheus-rules.yaml](./manifests/02-metering-prometheus-rules.yaml).

These Prometheus recording rules continuously aggregate container metrics by namespace:
- `tenant:cpu_requests:cores`
- `tenant:memory_requests:bytes`
- `tenant:storage_pvc_requested:bytes`
- `tenant:cpu_quota_utilization_ratio`

Apply the PrometheusRule:
```bash
ku apply -f pa-track/lab-06-audit-and-metering/manifests/02-metering-prometheus-rules.yaml
```

Verify Prometheus rule registration:
```bash
ku get prometheusrules.monitoring.coreos.com -n monitoring
```

---

### Step 4: Calculate Tenant Resource Metering & Chargeback

Run the tenant metering engine to analyze live or simulated cluster utilization:

```bash
./pa-track/lab-06-audit-and-metering/scripts/calculate-tenant-metering.py --mock
```

To run against a live cluster using your current kubeconfig:
```bash
./pa-track/lab-06-audit-and-metering/scripts/calculate-tenant-metering.py
```

To generate a CSV export for billing/finance systems:
```bash
./pa-track/lab-06-audit-and-metering/scripts/calculate-tenant-metering.py --mock --format csv
```

Sample Report Output:
```
============================================================================================================================
  GDC Air-Gapped Multi-Tenant Resource Utilization & Chargeback Metering Report
============================================================================================================================
  Active Tenants : 5    | Warning Saturation Threshold: 80.0%
  Allocated CPU  :  17.50 Cores | Allocated RAM:  39.20 GiB | Storage:  500.0 GiB
  Cluster Total Allocation Units: 27.80 AU/hour (~20294 AU/month)
----------------------------------------------------------------------------------------------------------------------------
Tenant Project       | Org     | Tier             | Pods | CPU Req/Quota | CPU %    | RAM Req/Quota  | RAM %    | Storage | AU/hr  | Status  
----------------------------------------------------------------------------------------------------------------------------
frontend-project     | org-1   | Standard         | 6    | 3.0/8.0c      | 37.5%    | 6.0/16.0G      | 37.5%    | 50 GiB  | 4.55   | OK      
backend-api-project  | org-1   | Mission-Critical | 8    | 6.0/12.0c     | 50.0%    | 16.0/32.0G     | 50.0%    | 200 GiB | 10.20  | OK      
sample-project-1     | org-1   | Development      | 2    | 1.0/4.0c      | 25.0%    | 2.0/8.0G       | 25.0%    | 20 GiB  | 1.52   | OK      
shared-services      | org-platform | Infrastructure-Shared | 4    | 4.0/16.0c     | 25.0%    | 8.0/32.0G      | 25.0%    | 150 GiB | 6.15   | OK      
tenant-b             | org-2   | Isolated-Partner | 3    | 3.5/4.0c      | 87.5%    | 7.2/8.0G       | 90.0%    | 80 GiB  | 5.38   | CRITICAL
============================================================================================================================
⚠️  CAPACITY NOTICE: Tenants approaching or exceeding quota limits: tenant-b
```

---

## Administrator Guidance & Capacity Management

1. **Quota Tuning & Over-Subscription**:
   - In air-gapped sandboxes, CPU request over-subscription of 1.5x - 2.0x is acceptable for bursty dev workloads.
   - Memory requests should never be over-subscribed beyond 1.0x of physical node capacity to avoid kernel OOM panic.
2. **Audit Log Retention & Storage**:
   - Ensure object storage sinks have lifecycle policies enabled to compress audit segments into immutable yearly archives for regulatory compliance (e.g. NIST 800-53 AU-6).
3. **Automated Alerting Integration**:
   - Connect `TenantResourceQuotaNearExhaustion` alerts to your internal platform escalation channel to proactively adjust tenant quotas before workloads fail.

---

## Summary

In this lab, you established robust enterprise auditing and capacity management for GDC Air-Gapped:
1. Implemented tiered audit policies to capture security and IAM mutations.
2. Configured centralized audit logging for SIEM and object storage archival.
3. Inspected forensic event streams to identify privilege escalation and policy tampering.
4. Deployed Prometheus multi-tenant recording rules for compute and storage metering.
5. Calculated resource allocation, quota headroom, and chargeback metrics.
