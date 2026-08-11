# GDC Sandbox Workshop

## About this repo

This repository provides a complete workshop environment for learning Google Distributed Cloud (GDC) Sandbox through hands-on labs. It includes setup automation, helper utilities, sample workloads, and guided exercises.

> [!WARNING]
> **Non-Production Environment:** This workshop and the associated GDC Sandbox environment are intended for **educational and testing purposes only**. They are NOT designed for production workloads.
>
> **Data Sensitivity:** Do NOT upload, process, or store any real sensitive, proprietary, or regulated data within this environment. Always use synthetic or publicly available data for your labs.

### Setup Scripts

Numbered scripts (`000-`, `001-`, `002-`, etc.) automate the initial GDC environment configuration:

- **`000-install-gdcloud.sh`** - Installs the `gdcloud` CLI tool and configures authentication certificates
- **`001-create-projects.py`** - Creates GDC projects based on `projects_config.yaml`
- **`002-apply-role-bindings.py`** - Applies IAM role bindings to projects and organizations
- **`003-createharborproject.sh`** - Sets up Harbor container registry projects
- **`004-addharborsecret.sh`** - Configures Harbor registry secrets for Kubernetes

### Helper Scripts

Convenience scripts to streamline common operations:

- **`sandbox.sh`** - Manages sandbox VM connections (SSH tunnels, file transfers, sshuttle VPN)
- **`login.sh`** - Authenticates to GDC clusters and Harbor registry
- **`build.sh`** - Builds Docker images and pushes them to Harbor
- **`pull.sh`** - Pulls public images and pushes them to your Harbor registry
- **`functions.sh`** - Bash functions for kubectl shortcuts (`ku`, `ko`, `kp`) and deployment helpers

### Lab Guide

The lab guide is available [here](./LabGuide.pdf).


## Set up Local Laptop

1. Clone the repo locally. 

2. Edit the `.env` file. 
```bash

cd ~/gdc-sandbox-workshop
cp .env.example .env

# edit .env for specifics
vi .env

source .env
```

3. Create tunnel to sandbox bootstrapper. 
```bash
./sandbox.sh tunnel
```

## Set up sandbox bootstrapper

1. Connect to the sandbox bootstrapper. 

2. Clone the repository on the sandbox bootstrapper and navigate to the workshop directory. 

```bash
git clone https://github.com/GoogleCloudPlatform/gdc-ag.git
cd gdc-ag/gdc-sandbox-workshop
```

3. On your local laptop, copy the `.env` file to the sandbox. 

```bash
./sandbox.sh env
```

4. On the sandbox bootstrapper, load environment variables. 
```bash
source .env
```

5. In the browser, login to sandbox console and download `gdcloud_cli.tar.gz` from the console.

6. Run `./000-install-gdcloud.sh` to install the `gdcloud` CLI tool and configure authentication certificates. 

7. Login to `gdcloud` cli. 

```bash
login
```

8. Edit `projects_config.yaml` to add your projects and user permissions. 

9. Run `./001-create-projects.py` to create the projects. 

10. Run `./002-apply-role-bindings.py` to apply IAM role bindings to projects and organizations. 

11. In console, attach project to `user-vm-1` cluster. 

12. Run `./003-createharborproject.sh` to create Harbor project.

13. In console, in Harbor project, create robot account and add to `.env`.  Re-run `source .env` and `login`. See [Lab guide](./LabGuide.pdf) for more details, screenshots and walk through. 

14. Run `./004-addharborsecret.sh` to add Harbor secret to `user-vm-1` cluster. 

15. You are now ready to start the labs.



## Learning Tracks

The GDC Sandbox Workshop offers two dedicated tracks tailored to different operational personas:

---

### Track 1: Application Operator (AO) Track

The Application Operator track focuses on deploying, scaling, and managing application microservices, containerization pipelines, and database backends in GDC.

- **[Lab 1 - Deploy HTML Server](./LAB-1.md)**: Containerize and deploy a baseline web server, establish Harbor image pull secrets, and configure LoadBalancer services.
- **[Lab 2 - Deploy API Server](./LAB-2.md)**: Deploy microservices with dependencies, manage ConfigMaps/Secrets, and test inter-service networking.
- **[Lab 3 - Deploy Elasticsearch Stack](./LAB-3.md)**: Deploy stateful analytics workloads with Elasticsearch and Kibana on GDC storage.

---

### Track 2: Platform Administrator (PA) Track

The **[Platform Administrator (PA) Track](./pa-track/README.md)** is designed for infrastructure engineers and security leads managing multi-tenant GDC Air-Gapped clusters, identity hierarchies, zero-trust network policies, compliance auditing, and capacity metering.

- **[Lab 01 - Multi-Tenant Landing Zones & Quotas](./pa-track/lab-01-landing-zone-quotas/LAB-01.md)**: Design multi-tier project topologies, configure ResourceQuotas/LimitRanges, and test quota exhaustion.
- **[Lab 02 - Air-Gapped RBAC & Identity Governance](./pa-track/lab-02-rbac-and-identity/LAB-02.md)**: Configure Keycloak OIDC group mappings, least-privilege RoleBindings, and automated CI/CD service account credentials.
- **[Lab 03 - Policy Controller Guardrails & Compliance](./pa-track/lab-03-policy-guardrails/LAB-03.md)**: Deploy Gatekeeper/OPA ConstraintTemplates and Constraints to enforce non-root execution, trusted Harbor registry provenance, and resource limits.
- **[Lab 04 - Harbor & DBaaS Shared Services Governance](./pa-track/lab-04-harbor-dbaas-governance/LAB-04.md)**: Configure Harbor vulnerability scanning with CVE severity gating, provision managed PostgreSQL/AlloyDB Omni instances, and manage backup policies.
- **[Lab 05 - Zero-Trust Network Isolation & VIPs](./pa-track/lab-05-network-isolation/LAB-05.md)**: Enforce baseline default-deny NetworkPolicies, cross-tenant service contracts, and dedicated MetalLB LoadBalancer VIP pools.
- **[Lab 06 - Platform Auditing & Capacity Metering](./pa-track/lab-06-audit-and-metering/LAB-06.md)**: Configure API server audit policy sinks, inspect security events with `inspect-audit-logs.py`, and compute multi-tenant resource utilization with `calculate-tenant-metering.py`.

👉 **[Explore the Master PA Track Curriculum Guide](./pa-track/README.md)**