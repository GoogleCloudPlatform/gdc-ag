# Application Workshop (Multi-Workload GitOps Delivery)

A hands-on **Application Delivery Workshop** on **Google Distributed Cloud - Air Gapped (GDC Sandbox)** and **Google Cloud (GKE Autopilot)** that builds directly upon the **[GitOps Workshop](../gitops-workshop/)**.

Once your GitOps platform is bootstrapped and you have provisioned a project repository (`<group>/<project>.git`) in `gitops-workshop`, this workshop demonstrates how application teams package, transfer, and ship real-world workloads—both **stateless microservices** (`translate-api`) and **stateful storage workloads** (`upload-api`)—into their dedicated GitLab manifest repositories.

### 🎯 What You Will Learn

- **Clear Separation Between Platform Onboarding & App Delivery**: How `gitops-workshop` (`provision_project.py`) provisions the tenant GitLab repository and ArgoCD App-of-Apps boundary once per project, while `application-workshop` requires only your target repository (`-r <group>/<project>`) to ship the workload manifests.
- **Automatic Multi-Image `Dockerfile` Discovery (`apps/<app-name>/`)**: How `scripts/build_and_push.py` recursively searches `apps/<app-name>/` for `Dockerfile`s—building and pushing multiple service images (`frontend:<tag>` + `api:<tag>`) for multi-container apps like `translate-api`, or a single image (`upload-api:<tag>`) for single-container apps like `upload-api`—with no per-app build scripts to maintain.
- **Pure Manifest GitOps Repositories (`manifests/` Only)**: How container images are built and pushed to Harbor / Artifact Registry in Step 1, while high-side GitLab holds **only** the declarative Kustomize manifests (`manifests/`), making repeated runs with no manifest changes a clean no-op.
- **Stateless vs. Stateful Infrastructure via GitOps**:
  - **App 1 — `translate-api` (Multi-Image Stateless Deployment)**: `frontend/Dockerfile` (React 19 + MUI v7 TypeScript SPA + non-root Nginx) and `api/Dockerfile` (Python Flask API) deployed as a two-container Kubernetes `Deployment` and `Service`.
  - **App 2 — `upload-api` (Single-Image Stateful Storage Vault)**: `app/Dockerfile` (Python Flask + Boto3 archive ingestion service) deployed as a Kubernetes `StatefulSet` with a dynamically provisioned `10Gi` `PersistentVolumeClaim` (`volumeClaimTemplates`, `standard-rwo`), RBAC `RoleBinding`, and optional GDC Object Storage (S3) replication.
- **Two-Step Delivery Lifecycle per Application**:
  1. **Step 1 (`scripts/build_and_push.py`)**: Search `apps/<app-name>/` for all `Dockerfile`s, build and push each container image to Harbor (`GDC`) or Artifact Registry (`GCP`), and configure the namespace pull secret.
  2. **Step 2 (`scripts/push_manifests.py`)**: Clone your existing `<group>/<project>.git` repository in a temporary workspace, overwrite `manifests/` with `<app-name>`'s declarative Kustomize overlays (preserving `manifests/project.yaml`), and push a Merge Request only when manifest changes are detected.

---

## 📂 Repository Layout

```text
application-workshop/
├── apps/
│   ├── translate-api/                  # App 1: Multi-Image Stateless Translation Portal
│   │   ├── frontend/                   # Service 1: React 19 Vite SPA + Nginx (Dockerfile -> frontend:<tag>)
│   │   ├── api/                        # Service 2: Python Flask API (Dockerfile -> api:<tag>)
│   │   └── manifests/                  # Kustomize base/ & overlays/{gdc,gcp} (IMAGE_FRONTEND + IMAGE_API)
│   └── upload-api/                     # App 2: Single-Image Stateful Archive Storage Vault
│       ├── app/                        # Flask + Boto3 archive vault UI/API (Dockerfile -> upload-api:<tag>)
│       └── manifests/                  # Kustomize base/ (StatefulSet, 10Gi PVC, RoleBinding) & overlays/{gdc,gcp}
├── scripts/
│   ├── build_and_push.py               # Step 1: Discover Dockerfiles in apps/<app>/ & push to Harbor / GAR
│   ├── push_manifests.py               # Step 2: Clone GitLab repo, overwrite manifests/, and push MR
│   └── cleanup.py                      # Remove deployed workload(s) from cluster
└── docs/                               # Architectural deep dives & step-by-step workflow
```

---

## 🛠️ Prerequisites

1. **Completed `gitops-workshop` + Provisioned Project Repositories**:
   - You have completed the **[GitOps Workshop](../gitops-workshop/README.md)** (ArgoCD on `localhost:8080` or `8088`, GitLab Web on `localhost:8081`, GitLab SSH on `localhost:2222`).
   - You have provisioned a dedicated GitLab project repository for each application using `gitops-workshop`:
     ```bash
     cd ../gitops-workshop
     python3 scripts/project_provision/provision_project.py -g workloads -p translate-project -a translate-api
     python3 scripts/project_provision/provision_project.py -g workloads -p upload-project -a upload-api
     ```
2. **Workstation CLI Tools**:
   - **`docker`**, **`kubectl`**, **`git`**, and **Python 3.10+** (`pip install -r requirements.txt`).
   - **`gcloud`**: Required only when running in `TARGET_PLATFORM="gcp"` mode.

---

## ⚡ Quick Start (Manual 2-Step CLI Execution)

```bash
cd application-workshop
cp .env.gdc.example .env   # Or .env.gcp.example for GCP GKE mode

# --- Deploy App 1: translate-api -> workloads/translate-project ---
# Step 1: Build image and push to Harbor / Artifact Registry
python3 scripts/build_and_push.py -r workloads/translate-project -a translate-api

# Step 2: Clone workloads/translate-project, overwrite manifests/, and push MR
python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api

# --- Deploy App 2: upload-api -> workloads/upload-project ---
# Step 1: Build image and push to Harbor / Artifact Registry
python3 scripts/build_and_push.py -r workloads/upload-project -a upload-api

# Step 2: Clone workloads/upload-project, overwrite manifests/, and push MR
python3 scripts/push_manifests.py -r workloads/upload-project -a upload-api
```

---

## 🚀 Interactive Guided Workshop (`tmux` + Antigravity)

```bash
cd application-workshop
tmux
agy
```
Then prompt the agent:
> *"Start the application workshop"* or *"`/app-workshop-guide`"*

---

## 🌐 Local Access & Port Summary

| Service | Local URL / Port | Purpose |
| :--- | :--- | :--- |
| **ArgoCD Web UI** | `http://localhost:8080` *(GCP)* / `https://localhost:8088` *(GDC)* | Sync `<project>-apps` $\rightarrow$ `translate-api` & `upload-api` |
| **GitLab Web UI** | [http://localhost:8081](http://localhost:8081) | Review & merge project Merge Requests |
| **App 1: `translate-api`** | [http://localhost:8082](http://localhost:8082) | `kubectl port-forward -n translate-api svc/translate-api 8082:80` |
| **App 2: `upload-api`** | [http://localhost:8083](http://localhost:8083) | `kubectl port-forward -n upload-api svc/upload-api 8083:80` |

---

## 📚 Documentation

- **[Multi-Application Delivery Workflow](docs/workflow.md)**: Complete walkthrough of shipping `translate-api` and `upload-api` into a `gitops-workshop` project repository.
- **[Application & Manifest Architecture](docs/app-architecture.md)**: Deep dive into `apps/translate-api/` (`Deployment`) and `apps/upload-api/` (`StatefulSet` + `10Gi` PVC + S3 Object Storage).
- **[CLI UX & Formatting Guidelines](docs/cli-ux-guidelines.md)**: Output styling, badges, parameter tables, and confirmation prompt standards.
- **[FAQ & Troubleshooting](docs/FAQ.md)**: Direct Git remote workflow (`git push gitlab ...`), Harbor registry auth, and PVC troubleshooting.
- **[Repository Guidelines](AGENTS.md)**: Architectural rules and idempotency standards.
