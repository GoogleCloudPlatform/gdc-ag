# Application Delivery Workflow Guide

This document details the end-to-end workflow for building and shipping workloads (`translate-api` and `upload-api`) into dedicated GitLab project repositories provisioned by [`gitops-workshop`](../../gitops-workshop/).

---

## 🗺️ How `gitops-workshop` and `application-workshop` Fit Together

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. COMPLETED IN gitops-workshop (Project Repository Provisioning)            │
│    # Provision Repo 1 for translate-api:                                     │
│    python3 scripts/project_provision/provision_project.py \                  │
│      -g workloads -p translate-project -a translate-api                      │
│                                                                              │
│    # Provision Repo 2 for upload-api:                                        │
│    python3 scripts/project_provision/provision_project.py \                  │
│      -g workloads -p upload-project -a upload-api                            │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. EXECUTED IN application-workshop (2-Step Build & Manifest Push per App)   │
│                                                                              │
│    Step 1 (build_and_push.py -r <group>/<project> -a <app-name>):            │
│      • Builds apps/<app-name>/app/ -> Pushes image to Harbor / GAR           │
│      • Ensures namespace <app-name> & harbor-pull-secret                     │
│                                                                              │
│    Step 2 (push_manifests.py -r <group>/<project> -a <app-name>):            │
│      • Clones <group>/<project>.git into a temp workspace                    │
│      • Preserves manifests/project.yaml & overwrites manifests/ with         │
│        manifests/<app-name>/, <app-name>-app.yaml, and kustomization.yaml    │
│      • No-ops if no manifest changes exist; otherwise opens/merges MR        │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 3. SYNCHRONIZED BY ARGOCD                                                    │
│    translate-project-apps ──► translate-api (Stateless Deployment + Service) │
│    upload-project-apps    ──► upload-api    (StatefulSet + 10Gi PVC + Svc)   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Step 0: Configure `.env`

```bash
cd application-workshop
cp .env.gdc.example .env   # Or .env.gcp.example for GCP GKE Autopilot
```

---

## 🚀 Shipping Application 1: `translate-api` $\rightarrow$ `workloads/translate-project`

### Step 1: Build & Push Image to Registry
```bash
python3 scripts/build_and_push.py -r workloads/translate-project -a translate-api
```
- Automatically discovers `apps/translate-api/frontend/Dockerfile` and `apps/translate-api/api/Dockerfile`.
- Builds and pushes `<HARBOR_URL>/<HARBOR_PROJECT>/frontend:v1.0.0` and `<HARBOR_URL>/<HARBOR_PROJECT>/api:v1.0.0` (or Artifact Registry equivalents).
- Configures namespace `translate-api` and `secret/harbor-pull-secret`.

### Step 2: Overwrite Manifests in `workloads/translate-project`
```bash
python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api --configure-remote
```
- Clones `workloads/translate-project.git` into a temporary directory.
- Preserves `manifests/project.yaml` and replaces the starter `nginx` manifests with `manifests/translate-api/` (`base/`, `overlays/gdc/`, `overlays/gcp/`), `manifests/translate-api-app.yaml`, and `manifests/kustomization.yaml`.
- Pushes a feature branch and opens (or with `-m`, merges) a Merge Request.
- Re-running this command when no manifests or image tags have changed is a **no-op** (`[EXISTS/SKIP]`).

### Verify `translate-api`
1. In ArgoCD, sync `translate-project-apps` $\rightarrow$ `translate-api`.
2. Port-forward and test:
   ```bash
   kubectl port-forward -n translate-api svc/translate-api 8082:80
   curl -s http://localhost:8082/healthz
   curl -s -X POST http://localhost:8082/translate \
     -H "Content-Type: application/json" \
     -d '{"text": "Hello World", "target_language": "es"}'
   ```

---

## 🗄️ Shipping Application 2: `upload-api` $\rightarrow$ `workloads/upload-project`

### Step 1: Build & Push Image to Registry
```bash
python3 scripts/build_and_push.py -r workloads/upload-project -a upload-api
```
- Builds the Python Flask + Gunicorn + Boto3 container from `apps/upload-api/app/`.
- Pushes `<HARBOR_URL>/<HARBOR_PROJECT>/upload-api:v1.0.0`.
- Configures namespace `upload-api` and `secret/harbor-pull-secret`.

### Step 2: Overwrite Manifests in `workloads/upload-project`
```bash
python3 scripts/push_manifests.py -r workloads/upload-project -a upload-api
```
- Clones `workloads/upload-project.git` into a temporary directory.
- Preserves `manifests/project.yaml` and overwrites `manifests/` with `manifests/upload-api/` (`StatefulSet` with `10Gi` `volumeClaimTemplates`, `Service`, `RoleBinding`), `manifests/upload-api-app.yaml`, and `manifests/kustomization.yaml`.
- Pushes a feature branch and opens (or with `-m`, merges) a Merge Request.

### Verify `upload-api` & Persistent Storage
1. In ArgoCD, sync `upload-project-apps` $\rightarrow$ `upload-api`.
2. Inspect the `StatefulSet` and dynamically provisioned `10Gi` `PersistentVolumeClaim`:
   ```bash
   kubectl get statefulset,pods,pvc,svc -n upload-api
   ```
3. Port-forward to `localhost:8083` and test archive persistence:
   ```bash
   kubectl port-forward -n upload-api svc/upload-api 8083:80
   curl -s http://localhost:8083/healthz
   curl -s -X POST http://localhost:8083/upload \
     -H "Content-Type: application/json" \
     -d '{"generate_sample": true}'
   curl -s http://localhost:8083/files
   ```

---

## 🧹 Cleanup (`scripts/cleanup.py`)

```bash
# Remove a single application:
python3 scripts/cleanup.py -a upload-api -y

# Or remove all workshop applications (translate-api and upload-api):
python3 scripts/cleanup.py --all-apps -y
```
