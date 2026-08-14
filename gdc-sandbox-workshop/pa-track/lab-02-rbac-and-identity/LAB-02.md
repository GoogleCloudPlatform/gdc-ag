# Lab 02: Air-Gapped RBAC, Keycloak OIDC Integration, and Pipeline Identity Governance in GDC

## 📌 Overview & Learning Objectives

In an air-gapped or restricted Google Distributed Cloud (GDC) infrastructure, identity management and access control cannot rely on public cloud identity providers. Instead, GDC integrates with on-premises OpenID Connect (OIDC) identity providers—most commonly **Keycloak** or Active Directory Federation Services (ADFS)—to federate authentication and govern authorization.

As a **Platform Administrator (PA)**, your mission is to enforce the principle of least privilege, strict tenant boundary isolation, and secure automated delivery pipeline credentials.

In this lab, you will learn how to:
1. **Understand Air-Gapped Identity Federation**: Trace how Keycloak OIDC tokens (JWTs) pass group claims (`groups`) to the Kubernetes API server for authorization.
2. **Author Granular Role-Based Access Control (RBAC)**: Define custom `ClusterRole` manifests for **Tenant Administrators**, **Application Developers**, **Compliance Auditors**, and **CI/CD Automation Agents**.
3. **Map Identity Groups to Tenant Namespaces**: Bind enterprise OIDC groups (`finance-admins-grp`, `developers-grp`, `auditors-grp`, `data-scientists-grp`) to specific namespaces with precise privilege levels.
4. **Provision CI/CD Pipeline ServiceAccounts**: Generate scoped `ServiceAccount` identities, long-lived token secrets, and automated deployment bindings for external CI/CD systems (GitLab CI, Jenkins, ArgoCD).
5. **Automate RBAC Provisioning**: Use the production-grade Python provisioner ([`provision-rbac.py`](./scripts/provision-rbac.py)) to bulk-apply governance mappings.
6. **Audit & Verify Authorization Boundaries**: Run the comprehensive RBAC test suite ([`test-permissions.sh`](./scripts/test-permissions.sh)) with `kubectl auth can-i` impersonation.

---

## 🔐 Air-Gapped Identity Architecture & OIDC Flow

```
+---------------------------------------------------------------------------------------------------+
|                                Air-Gapped Keycloak Identity Provider                              |
|                                (Issues OIDC JWTs with "groups" claims)                            |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                    [ OIDC ID Token Bearer ]
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                  GDC Kubernetes API Server                                        |
|                          (Validates JWT signature & maps OIDC groups)                             |
+---------------------------------------------------------------------------------------------------+
                                                  |
         +----------------------------------------+----------------------------------------+
         |                                        |                                        |
         v                                        v                                        v
+---------------------------------+      +---------------------------------+      +---------------------------------+
| Namespace: finance-dev          |      | Namespace: finance-prod         |      | Namespace: analytics-lab        |
|---------------------------------|      |---------------------------------|      |---------------------------------|
| RoleBindings:                   |      | RoleBindings:                   |      | RoleBindings:                   |
|  - finance-admins-grp           |      |  - finance-admins-grp           |      |  - analytics-admins-grp         |
|    -> gdc-tenant-admin          |      |    -> gdc-tenant-admin          |      |    -> gdc-tenant-admin          |
|  - developers-grp               |      |  - finance-devs-grp             |      |  - data-scientists-grp          |
|    -> gdc-developer-role        |      |    -> gdc-auditor-role (READ!)  |      |    -> gdc-developer-role        |
|  - auditors-grp                 |      |  - auditors-grp                 |      |  - auditors-grp                 |
|    -> gdc-auditor-role          |      |    -> gdc-auditor-role          |      |    -> gdc-auditor-role          |
|  - SA: gitlab-deployer-sa       |      |  - SA: gitlab-deployer-sa       |      |  - SA: jenkins-analytics-sa     |
|    -> gdc-cicd-deployer-role    |      |    -> gdc-cicd-deployer-role    |      |    -> gdc-cicd-deployer-role    |
+---------------------------------+      +---------------------------------+      +---------------------------------+
```

---

## 📁 Artifacts & File Map

All manifests and automation scripts for this lab are located in [`pa-track/lab-02-rbac-and-identity/`](.):

| File Path | Description |
| :--- | :--- |
| [`manifests/01-custom-roles.yaml`](./manifests/01-custom-roles.yaml) | Declarative `ClusterRole` specifications (`gdc-tenant-admin`, `gdc-developer-role`, `gdc-auditor-role`, `gdc-cicd-deployer-role`). |
| [`manifests/02-tenant-rolebindings.yaml`](./manifests/02-tenant-rolebindings.yaml) | Scoped `RoleBinding` definitions connecting Keycloak OIDC groups and users to tenant namespaces. |
| [`manifests/03-cicd-serviceaccounts.yaml`](./manifests/03-cicd-serviceaccounts.yaml) | `ServiceAccount`, declarative token `Secret`, and pipeline `RoleBinding` manifests for GitLab CI and Jenkins. |
| [`scripts/identity_mappings.yaml`](./scripts/identity_mappings.yaml) | Declarative YAML specification mapping OIDC groups, users, and service accounts per namespace. |
| [`scripts/provision-rbac.py`](./scripts/provision-rbac.py) | Python automation script to validate and bulk-apply RBAC policies and credentials across tenant projects. |
| [`scripts/test-permissions.sh`](./scripts/test-permissions.sh) | Automated test suite validating least-privilege access, audit guardrails, and cross-tenant isolation. |

---

## 🛠️ Step-by-Step Instructions

### Step 1: Examine Custom RBAC Roles

Inspect [`manifests/01-custom-roles.yaml`](./manifests/01-custom-roles.yaml):

```bash
cat pa-track/lab-02-rbac-and-identity/manifests/01-custom-roles.yaml
```

Notice the specific design considerations for each role:
1. **`gdc-tenant-admin`**: Grants full management of workloads, services, and local `RoleBindings` within the tenant namespace, but restricts modification of `ResourceQuotas` and `LimitRanges` (which are reserved for Platform Admins).
2. **`gdc-developer-role`**: Allows deployment, scaling, log tailing, port-forwarding, and container execution for iterative development, but forbids modifying RBAC or network security policies.
3. **`gdc-auditor-role`**: Provides pure read-only (`get`, `list`, `watch`) access across workloads and configurations, while strictly denying `pods/exec`, `pods/portforward`, and mutation.
4. **`gdc-cicd-deployer-role`**: Specifically scoped for CI/CD runners to perform zero-downtime rolling updates and manage configuration secrets without elevated cluster privileges.

---

### Step 2: Review Multi-Tenant Group Bindings

Inspect [`manifests/02-tenant-rolebindings.yaml`](./manifests/02-tenant-rolebindings.yaml):

```bash
cat pa-track/lab-02-rbac-and-identity/manifests/02-tenant-rolebindings.yaml
```

#### Key Separation of Duties Pattern:
- In **`finance-dev`**: Developers (`developers-grp`) have full **`gdc-developer-role`** to deploy and iterate.
- In **`finance-prod`**: Developers (`finance-devs-grp`) are bound ONLY to **`gdc-auditor-role`**. This prevents manual, un-audited changes to production while allowing engineers to inspect logs and verify health. Production changes must go through approved CI/CD pipelines!

---

### Step 3: Review CI/CD Service Account Provisioning

Inspect [`manifests/03-cicd-serviceaccounts.yaml`](./manifests/03-cicd-serviceaccounts.yaml):

```bash
cat pa-track/lab-02-rbac-and-identity/manifests/03-cicd-serviceaccounts.yaml
```

In Kubernetes 1.24+, ServiceAccount secrets are not auto-generated by default. GDC Platform Administrators provision declarative token secrets annotated with `kubernetes.io/service-account.name: <sa-name>`, providing deterministic credentials for pipeline runners.

---

### Step 4: Provision RBAC and Identity Mappings

You can apply the RBAC policies using the automated provisioner or raw manifests.

#### Method A: Using the Python Provisioner (Recommended)
The [`provision-rbac.py`](./scripts/provision-rbac.py) script reads [`identity_mappings.yaml`](./scripts/identity_mappings.yaml), generates the full governance matrix, and applies it to the cluster.

1. **Perform a Dry Run**:
   ```bash
   python3 pa-track/lab-02-rbac-and-identity/scripts/provision-rbac.py --dry-run
   ```
2. **Apply the RBAC Policies**:
   ```bash
   python3 pa-track/lab-02-rbac-and-identity/scripts/provision-rbac.py
   ```

#### Method B: Using `kubectl` Directly
```bash
kubectl apply -f pa-track/lab-02-rbac-and-identity/manifests/01-custom-roles.yaml
kubectl apply -f pa-track/lab-02-rbac-and-identity/manifests/02-tenant-rolebindings.yaml
kubectl apply -f pa-track/lab-02-rbac-and-identity/manifests/03-cicd-serviceaccounts.yaml
```

---

### Step 5: Extract CI/CD Pipeline Credentials

To configure an external GitLab CI runner or Jenkins job, extract the ServiceAccount token and generate a scoped `KUBECONFIG`:

```bash
# 1. Retrieve the CA certificate from the cluster
kubectl get secret gitlab-deployer-sa-token -n finance-dev -o jsonpath='{.data.ca\.crt}' | base64 --decode > /tmp/ca.crt

# 2. Extract the bearer token
export GITLAB_DEV_TOKEN=$(kubectl get secret gitlab-deployer-sa-token -n finance-dev -o jsonpath='{.data.token}' | base64 --decode)

# 3. View the extracted token prefix
echo "Extracted Bearer Token: ${GITLAB_DEV_TOKEN:0:20}..."
```

---

### Step 6: Test Permissions & Tenant Isolation

Run the automated authorization testing suite to verify every persona across all namespaces:

```bash
./pa-track/lab-02-rbac-and-identity/scripts/test-permissions.sh
```

**Sample Output:**
```
========================================================================================================
🛡️  GDC Air-Gapped RBAC & Tenant Isolation Test Matrix
========================================================================================================

  STATUS | SUBJECT (USER / GROUP)           | NAMESPACE      | ACTION           | EXP (ACT)  | TEST DESCRIPTION
  ------------------------------------------------------------------------------------------------------

▶ Test Suite 1: Developer Persona Permissions & Boundaries
  ✔ PASS | alice-dev@example.com [develope | finance-dev    | create pods      | yes  (got yes) | Dev can create pods in finance-dev
  ✔ PASS | alice-dev@example.com [develope | finance-dev    | create deploymen | yes  (got yes) | Dev can create deployments in finance-dev
  ✔ PASS | alice-dev@example.com [develope | finance-dev    | delete pods      | yes  (got yes) | Dev can delete pods in finance-dev
  ✔ PASS | alice-dev@example.com [develope | finance-dev    | create roles.rba | no   (got no ) | Dev CANNOT modify RBAC roles in finance-dev
  ✔ PASS | alice-dev@example.com [develope | finance-dev    | delete resourceq | no   (got no ) | Dev CANNOT delete ResourceQuota in finance-dev
  ✔ PASS | alice-dev@example.com [finance- | finance-prod   | get pods         | yes  (got yes) | Dev can view pods in finance-prod (Auditor role)
  ✔ PASS | alice-dev@example.com [finance- | finance-prod   | create pods      | no   (got no ) | Dev CANNOT create pods in finance-prod
  ✔ PASS | alice-dev@example.com [finance- | finance-prod   | delete deploymen | no   (got no ) | Dev CANNOT delete deployments in finance-prod
  ✔ PASS | alice-dev@example.com [develope | analytics-lab  | get pods         | no   (got no ) | Dev CANNOT access analytics-lab (Cross-tenant boundary)

▶ Test Suite 2: Tenant Project Admin Persona
  ✔ PASS | finance-lead@example.com [finan | finance-dev    | create deploymen | yes  (got yes) | Tenant Admin can manage deployments in finance-dev
  ✔ PASS | finance-lead@example.com [finan | finance-dev    | create rolebindi | yes  (got yes) | Tenant Admin can delegate RBAC bindings in finance-dev
  ✔ PASS | finance-lead@example.com [finan | finance-dev    | delete resourceq | no   (got no ) | Tenant Admin CANNOT delete ResourceQuota (Platform Admin only)
  ✔ PASS | finance-lead@example.com [finan | finance-prod   | create deploymen | yes  (got yes) | Tenant Admin can manage deployments in finance-prod
  ✔ PASS | finance-lead@example.com [finan | analytics-lab  | create deploymen | no   (got no ) | Finance Admin CANNOT manage analytics-lab

▶ Test Suite 3: Compliance Auditor Persona (Read-Only Guardrails)
  ✔ PASS | audit-bot@example.com [auditors | finance-dev    | get pods         | yes  (got yes) | Auditor can read pods in finance-dev
  ✔ PASS | audit-bot@example.com [auditors | finance-dev    | get resourcequot | yes  (got yes) | Auditor can inspect quotas in finance-dev
  ✔ PASS | audit-bot@example.com [auditors | finance-dev    | create pods      | no   (got no ) | Auditor CANNOT create pods in finance-dev
  ✔ PASS | audit-bot@example.com [auditors | finance-dev    | delete services  | no   (got no ) | Auditor CANNOT delete services in finance-dev
  ✔ PASS | audit-bot@example.com [auditors | finance-dev    | create pods/exec | no   (got no ) | Auditor CANNOT exec into pods (Prevent container intrusion)
  ✔ PASS | audit-bot@example.com [auditors | finance-prod   | get pods         | yes  (got yes) | Auditor can read pods in finance-prod
  ✔ PASS | audit-bot@example.com [auditors | analytics-lab  | get pods         | yes  (got yes) | Auditor can read pods in analytics-lab

▶ Test Suite 4: Scoped CI/CD Pipeline Automation Identity
  ✔ PASS | system:serviceaccount:finance-d | finance-dev    | create deploymen | yes  (got yes) | GitLab SA can create deployments in finance-dev
  ✔ PASS | system:serviceaccount:finance-d | finance-dev    | create secrets   | yes  (got yes) | GitLab SA can manage secrets in finance-dev
  ✔ PASS | system:serviceaccount:finance-d | finance-dev    | create rolebindi | no   (got no ) | GitLab SA CANNOT modify RBAC in finance-dev
  ✔ PASS | system:serviceaccount:finance-d | finance-prod   | create deploymen | no   (got no ) | Dev GitLab SA CANNOT deploy to finance-prod (Pipeline token isolation)
  ✔ PASS | system:serviceaccount:finance-p | finance-prod   | create deploymen | yes  (got yes) | Prod GitLab SA can deploy to finance-prod

▶ Test Suite 5: Data Scientist Persona in Analytics Lab
  ✔ PASS | scientist-lead@example.com [dat | analytics-lab  | create jobs.batc | yes  (got yes) | Data Scientist can submit batch jobs in analytics-lab
  ✔ PASS | scientist-lead@example.com [dat | analytics-lab  | create pods      | yes  (got yes) | Data Scientist can create pods in analytics-lab
  ✔ PASS | scientist-lead@example.com [dat | finance-dev    | get pods         | no   (got no ) | Data Scientist CANNOT access finance-dev
  ✔ PASS | scientist-lead@example.com [dat | finance-prod   | get pods         | no   (got no ) | Data Scientist CANNOT access finance-prod

========================================================================================================
📊 Authorization Test Results: 24 Passed, 0 Failed (Total: 24)
========================================================================================================
[SUCCESS] All RBAC boundaries, least-privilege rules, and tenant isolations verified!
```

---

## 🏆 Lab Summary & Security Governance Best Practices

1. **Bind OIDC Groups, Not Individual Users**: Maintain group memberships inside Keycloak or enterprise Active Directory. In Kubernetes, bind to `kind: Group` subjects to avoid manual RBAC churn when engineers join or leave teams.
2. **Enforce Read-Only Developer Access in Production**: Direct manual write access to production namespaces violates compliance frameworks (SOC 2, FedRAMP, PCI-DSS). Developers should have `gdc-auditor-role` in production for troubleshooting, while automated CI/CD ServiceAccounts execute deployments.
3. **Isolate Pipeline ServiceAccount Tokens by Namespace**: Never reuse a single CI/CD ServiceAccount across multiple environments (e.g., dev and prod). Scope tokens strictly to their target namespace to prevent lateral movement during supply-chain attacks.
4. **Audit RBAC Continuously**: Use `kubectl auth can-i` test suites in continuous integration to prevent accidental permission regressions.

---
🎉 **Congratulations!** You have completed Modules 1 and 2 of the GDC Platform Administrator Track. Return to the [PA Track Overview](../README.md) or explore the remaining workshop modules.
