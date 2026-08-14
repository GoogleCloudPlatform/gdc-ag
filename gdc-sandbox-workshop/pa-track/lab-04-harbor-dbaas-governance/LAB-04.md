# Module 4: Shared Platform Services Governance: Harbor & DBaaS

## Overview

In Google Distributed Cloud (GDC) Air-Gapped, Platform Administrators manage shared core platform services that tenant applications consume. Two foundational platform services are:

1. **Harbor Enterprise Container Registry:** Provides secure, sovereign artifact storage, vulnerability scanning, and supply-chain governance.
2. **Database as a Service (DBaaS / Managed PostgreSQL / AlloyDB Omni):** Provides declarative, enterprise-grade relational database provisioning with built-in high availability, automated credential lifecycle management, and snapshot backup policies.

This lab teaches Platform Administrators how to establish security governance on Harbor projects and provision, govern, and audit tenant databases in GDC Air-Gapped.

---

## Learning Objectives

By completing this module, you will:
1. **Automate Harbor Project Governance:** Enforce automatic Trivy vulnerability scanning, block vulnerable image deployments using CVE severity gating, and implement tag immutability and retention rules.
2. **Manage Least-Privilege Robot Accounts:** Automate the provisioning of scoped pull secrets for tenant project workloads.
3. **Deploy Managed DBaaS Clusters:** Declaratively provision highly available PostgreSQL / AlloyDB Omni database clusters using GDC Custom Resources.
4. **Configure Automated Snapshot & Backup Schedules:** Establish recovery point objectives (RPO) and point-in-time recovery (PITR) with automated WAL archiving to GDC Object Storage.
5. **Integrate Tenant Applications:** Connect a microservice application securely using automatically injected database credentials.

---

## Architecture

### 1. Harbor Security Governance Workflow

```
+-----------------------------------------------------------------------------------+
|                        Harbor Enterprise Registry in GDC                         |
|                                                                                   |
|  Developer / CI-CD          +-------------------+        +--------------------+   |
|  (docker push myapp:v1.0)-> |   Harbor Core     | -----> |  Trivy Scanner     |   |
|                             +-------------------+        |  (Auto Vulnerability|  |
|                                       |                  |   Scan on Push)    |   |
|                                       v                  +--------------------+   |
|                             +-------------------+                   |             |
|                             | Immutable Tag     |                   v             |
|                             | Rule Engine       |        +--------------------+   |
|                             | (Blocks Overwrite |        | Security Gating    |   |
|                             |  on v*, release-*)|        | (Blocks Pull if    |   |
|                             +-------------------+        |  CVE >= High)      |   |
|                                       |                  +--------------------+   |
|                                       v                                           |
|                             +-------------------+                                 |
|                             | Retention Policy  |                                 |
|                             | (Retains Top 10,  |                                 |
|                             |  Purges Stale CI) |                                 |
|                             +-------------------+                                 |
+---------------------------------------|-------------------------------------------+
                                        |
                 Verified Image Pull    v
               +----------------------------------+
               |  GDC Tenant Kubernetes Cluster   |
               |  (kubelet with Robot Account)    |
               +----------------------------------+
```

### 2. GDC DBaaS Operator & Tenant Consumer Topology

```
+-----------------------------------------------------------------------------------+
|                           Tenant Project: sample-project-1                        |
|                                                                                   |
|  +-------------------------------------+    +----------------------------------+  |
|  |  DatabaseCluster Custom Resource    |    |  DatabaseBackupSchedule CR       |  |
|  |  (PostgreSQL 15 / AlloyDB Omni)     |    |  (Daily at 02:00 UTC, 30d Keep)  |  |
|  +-------------------------------------+    +----------------------------------+  |
|                     |                                         |                   |
|                     v (DBaaS Operator Reconciles)             v (Scheduled Job)   |
|  +-------------------------------------------------+  +------------------------+  |
|  |  [Primary Instance]  <---sync---> [Standby]     |  | Snapshot + WAL Archive |  |
|  |  (Read/Write)                     (Failover HA) |  | to GDC Object Storage  |  |
|  +-------------------------------------------------+  +------------------------+  |
|                     ^                                                             |
|                     | Connects via internal service                               |
|                     |                                                             |
|  +------------------|----------------------------------------------------------+  |
|  |  order-processing-service (Tenant Workload)                                  |  |
|  |  - Injects credentials from Secret 'tenant-db-credentials'                  |  |
|  |  - Pre-flight initContainer database health validation                       |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## Lab Artifacts & Manifests

- **Harbor Governance:**
  - [`01-harbor-project-policy.yaml`](./manifests/01-harbor-project-policy.yaml): Declarative Harbor project security and retention configuration.
  - [`configure-harbor-governance.py`](./scripts/configure-harbor-governance.py): REST API automation script for Harbor security settings.
- **Database as a Service (DBaaS):**
  - [`02-tenant-database-cluster.yaml`](./manifests/02-tenant-database-cluster.yaml): Managed PostgreSQL / AlloyDB Omni cluster custom resource.
  - [`03-database-backup-schedule.yaml`](./manifests/03-database-backup-schedule.yaml): Automated snapshot backup policy with WAL archiving for PITR.
  - [`04-app-database-consumer.yaml`](./manifests/04-app-database-consumer.yaml): Tenant application consuming the managed database with secure secret injection.
  - [`provision-tenant-db.sh`](./scripts/provision-tenant-db.sh): End-to-end DBaaS provisioning and validation automation script.

---

## Hands-On Lab Walkthrough

### Part 1: Harbor Enterprise Security Governance

#### Step 1.1: Review Declarative Harbor Governance Policy

Inspect the declarative policy in [`01-harbor-project-policy.yaml`](./manifests/01-harbor-project-policy.yaml):

```bash
cat pa-track/lab-04-harbor-dbaas-governance/manifests/01-harbor-project-policy.yaml
```

Key governance settings:
- **`autoScanOnPush: true`**: Automatically runs Trivy vulnerability scanning whenever a new artifact is pushed.
- **`preventVulnerableImages: true`** & **`severityThreshold: high`**: Prevents containers from pulling images containing unresolved High or Critical CVEs.
- **`immutableTagRules`**: Prevents tag mutation for production versions matching `v*` and `release-*`.
- **`retentionPolicy`**: Automatically cleans up stale untagged test artifacts while preserving release candidates.

#### Step 1.2: Apply Harbor Governance via REST API

Execute the Python governance automation script:

```bash
cd pa-track/lab-04-harbor-dbaas-governance/scripts
chmod +x configure-harbor-governance.py provision-tenant-db.sh

# Run dry-run simulation
./configure-harbor-governance.py --dry-run

# Apply configuration to live Harbor instance
./configure-harbor-governance.py
```

**Expected Output:**
```text
============================================================
 GDC Air-Gapped: Harbor Project Governance Configuration
============================================================
Harbor URL:           https://harbor.zone1.google.gdch.test
Target Project:       sample-project-1
Severity Threshold:   HIGH
Dry Run Mode:         False
------------------------------------------------------------

▶ Step 1: Checking Harbor project 'sample-project-1'...
  ✔ Target Project ID: 1

▶ Step 2: Applying Vulnerability Gating & Auto-Scan Policies...
  ✔ Successfully enforced vulnerability gating (Threshold: HIGH).
  ✔ Images with High/Critical CVEs will be blocked from deployment.

▶ Step 3: Configuring Immutable Tag Rules...
  ✔ Added immutable tag rule for pattern: 'v*'
  ✔ Added immutable tag rule for pattern: 'release-*'

▶ Step 4: Provisioning Least-Privilege Robot Pull Account...
  ✔ Created robot account 'robot-sample-project-1-pull'.
    Secret Token generated: abc12345********

============================================================
 Harbor Governance configuration completed successfully.
============================================================
```

---

### Part 2: Managed Database as a Service (DBaaS) Governance

#### Step 2.1: Inspect Database Cluster Custom Resource

Examine [`02-tenant-database-cluster.yaml`](./manifests/02-tenant-database-cluster.yaml):

```bash
cat pa-track/lab-04-harbor-dbaas-governance/manifests/02-tenant-database-cluster.yaml
```

Notice how the declarative spec defines:
- High availability with 2 instances (1 primary + 1 standby) and pod anti-affinity.
- Enforced SSL/TLS encryption.
- Automated secret generation for database credentials (`tenant-db-credentials`).
- Compute and memory resource requests/limits conforming to the policy guardrails established in Lab 03.

#### Step 2.2: Inspect Backup & Point-in-Time Recovery Schedule

Examine [`03-database-backup-schedule.yaml`](./manifests/03-database-backup-schedule.yaml):

```bash
cat pa-track/lab-04-harbor-dbaas-governance/manifests/03-database-backup-schedule.yaml
```

Key operational parameters:
- **Schedule:** `0 2 * * *` (Daily at 02:00 AM UTC during off-peak window).
- **Retention:** 30 daily snapshots maintained automatically.
- **PITR:** Continuous WAL archiving stored in air-gapped GDC Object Storage.

#### Step 2.3: Provision and Validate the DBaaS Stack

Run the automated provisioning script:

```bash
./provision-tenant-db.sh
```

**Expected Output:**
```text
============================================================
 GDC Air-Gapped: Tenant DBaaS Provisioning & Governance
============================================================
Target Namespace: sample-project-1
Kubeconfig:       kubectl --kubeconfig=/home/user/user-vm-1-kubeconfig

▶ Step 1: Provisioning Managed PostgreSQL / AlloyDB Omni Cluster...
databasecluster.db.gdc.goog/tenant-order-db created

▶ Step 2: Validating DatabaseCluster Resource & Credentials Secret...
  ✔ Database credentials secret 'tenant-db-credentials' found.

▶ Step 3: Applying Automated Snapshot & Backup Policy...
databasebackupschedule.db.gdc.goog/tenant-order-db-daily-backup created
  ✔ Applied DatabaseBackupSchedule 'tenant-order-db-daily-backup'.

▶ Step 4: Deploying Tenant Database Consumer Workload...
deployment.apps/order-processing-service created
service/order-processing-service created

▶ Step 5: Inspecting Deployed DBaaS Resources & Application Status...
------------------------------------------------------------
Database Clusters:
NAME              ENGINE       VERSION   INSTANCES   STATUS   AGE
tenant-order-db   postgresql   15.4      2           Ready    45s

Backup Schedules:
NAME                           SCHEDULE    RETENTION   STATUS   AGE
tenant-order-db-daily-backup   0 2 * * *   30d         Active   30s

Tenant Workloads:
NAME                                        READY   STATUS    RESTARTS   AGE
order-processing-service-6b78997c45-k9z2x   1/1     Running   0          25s
order-processing-service-6b78997c45-w8v1m   1/1     Running   0          25s

============================================================
 DBaaS tenant provisioning and validation complete.
============================================================
```

#### Step 2.4: Verify Application Connection & Logs

Inspect the consumer application logs to verify database connectivity:

```bash
ku logs -l app=order-processor -c order-processor
```

---

## Clean Up

To clean up resources created during this lab:

```bash
ku delete -f ../manifests/04-app-database-consumer.yaml --ignore-not-found=true
ku delete -f ../manifests/03-database-backup-schedule.yaml --ignore-not-found=true
ku delete -f ../manifests/02-tenant-database-cluster.yaml --ignore-not-found=true
```

---

## Summary & Platform Admin Best Practices

1. **Supply-Chain Integrity:** Combine Policy Controller (Lab 03) with Harbor Vulnerability Gating (Lab 04) to establish end-to-end supply-chain defense in depth.
2. **Immutable Releases:** Enforce immutable tag patterns (`v*`, `release-*`) to guarantee audit reproducibility and prevent accidental production overwrites.
3. **Automate Secret Lifecycle:** Use declarative DBaaS operators to generate and rotate connection credentials automatically without human credential handling.
4. **Standardize Backup Tiers:** Define enterprise backup tiers (Gold, Silver, Bronze) with automated WAL archiving to ensure tenant disaster recovery readiness.
