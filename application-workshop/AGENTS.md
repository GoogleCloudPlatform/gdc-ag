# Repository Guidelines for AI Agents & Developers (`application-workshop`)

This document defines the architectural standards, operational boundaries, and design structure for `application-workshop`.

## Core Architectural Principles

1. **Strict Boundary Between `gitops-workshop` and `application-workshop`**:
   - **`gitops-workshop` Owns Platform & Project Provisioning**: Bootstrapping ArgoCD/GitLab, creating GitLab groups and repositories, granting `argocd-readonly` permissions, and registering `<project>-apps.yaml` in `gitops-platform/manifests` are handled **exclusively** by `gitops-workshop` (`provision_project.py`).
   - **`application-workshop` Owns Application Delivery into an Existing Repo**: The only required target input for `application-workshop` is the existing GitLab project repository (`<group>/<project>`) and the workload name (`-a translate-api` or `-a upload-api`). `application-workshop` scripts must **never** create GitLab groups/projects or modify `gitops-platform/manifests`.

2. **Multi-Workload & Multi-Image Directory Standard (`apps/<app-name>/`)**:
   - Workloads live one folder deeper under `apps/<app-name>/`:
     - **Service `Dockerfile`(s)**: `scripts/build_and_push.py` recursively searches `apps/<app-name>/` for `Dockerfile`s (excluding `manifests/`).
       - If a `Dockerfile` is in a service directory such as `apps/<app-name>/frontend/Dockerfile` or `apps/<app-name>/api/Dockerfile`, it builds `<service>:<tag>` (`frontend:<tag>`, `api:<tag>`) and exports `IMAGE_FRONTEND` and `IMAGE_API` into `app.properties`.
       - If a `Dockerfile` is in `apps/<app-name>/app/Dockerfile` or `apps/<app-name>/Dockerfile`, it builds `<app-name>:<tag>` and exports `IMAGE` (and `IMAGE_<APP_NAME>`) into `app.properties`.
     - **`apps/<app-name>/manifests/`**: Kustomize `base/`, environment overlays (`overlays/gdc/`, `overlays/gcp/`), and the ArgoCD `Application` template (`<app-name>-app.yaml`).
   - Included reference workloads:
     - **`apps/translate-api/`**: Multi-image stateless Translation Portal (`frontend/Dockerfile` + `api/Dockerfile`, deployed via `Deployment` + `Service` + `ConfigMap` + `Secret`).
     - **`apps/upload-api/`**: Single-image stateful Archive Ingestion & Storage Vault (`app/Dockerfile`, deployed via `StatefulSet` + `10Gi` `PersistentVolumeClaim` via `volumeClaimTemplates` + `Service` + `RoleBinding` + optional S3 / GDC Object Storage replication).

3. **Two-Step Delivery & Pure-Manifest Repository Workflow**:
   - **Step 1 (`scripts/build_and_push.py`)**: Discovers all `Dockerfile`s under `apps/<app-name>/`, builds and pushes each container image to Harbor (`gdc`) or Artifact Registry (`gcp`), configures the `<app-name>` namespace and `harbor-pull-secret`, and stages rendered Kustomize properties in `.deployed-manifests/<app-name>/`.
   - **Step 2 (`scripts/push_manifests.py`)**:
     1. Verifies the target GitLab repository (`<group>/<project>.git`) already exists (provisioned via `gitops-workshop`).
     2. Clones `<group>/<project>.git` into a temporary directory.
     3. Preserves `manifests/project.yaml` and overwrites `manifests/` with `manifests/<app-name>/` (`base/` + `overlays/`), `manifests/<app-name>-app.yaml`, and `manifests/kustomization.yaml` (holding **only** declarative manifests in GitLab, never raw application source code).
     4. Checks `git status --porcelain`: if no manifest changes exist, exits cleanly as a no-op (`[EXISTS/SKIP]`); otherwise commits, pushes a feature branch, and opens (or with `-m`, merges) a Merge Request.

4. **Read-Only `.env` Sourcing & Idempotency**:
   - `.env` files are **strictly read-only**: Python scripts MUST NEVER modify or overwrite `.env` files.
   - All scripts (`build_and_push.py`, `push_manifests.py`, `cleanup.py`) must be strictly idempotent and support `-e`, `-r`, `-a`, `-y`, `-m`, `--dry-run`, and `--check-prereqs`.
