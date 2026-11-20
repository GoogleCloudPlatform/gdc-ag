---
name: app-workshop-guide
description: >-
  Interactive end-to-end guide for the Application Workshop (application-workshop).
  Walks participants through configuring .env with their existing GitLab project repository (provisioned in gitops-workshop), shipping App 1 (translate-api, stateless Deployment) via Step 1 (build_and_push.py) and Step 2 (push_manifests.py), and shipping App 2 (upload-api, StatefulSet with 10Gi PersistentVolumeClaim) into the same project repository.
---

# Application Workshop Guided Delivery Runbook

Welcome to the **Application Workshop Guided Delivery Runbook**!

This skill orchestrates the build, registry push, and GitOps deployment of two reference workloads—**`translate-api`** (stateless web & translation API) and **`upload-api`** (stateful archive vault with a `10Gi` `PersistentVolumeClaim`)—into the GitLab project repository you provisioned in `gitops-workshop`, following [**`docs/workflow.md`**](../../../docs/workflow.md).

---

## 📖 Educational Overview & Roadmap

### How This Builds on `gitops-workshop`:
In `gitops-workshop`, you bootstrapped the GitOps platform and ran `provision_project.py`, which gave you a GitLab project repository (`<group>/<project>.git`) wired to ArgoCD (`<project>-apps`) with a starter `nginx` placeholder.

In this workshop, you act as the **Application Team** shipping multiple workloads into that repository:
1. **App 1 (`apps/translate-api/`)**: Stateless React 19 + MUI TypeScript SPA & Python Flask API (`Deployment` + `Service`).
2. **App 2 (`apps/upload-api/`)**: Stateful Archive Storage Vault (`StatefulSet` + `10Gi` `PersistentVolumeClaim` + `RoleBinding`).

### High-Level Workshop Steps:
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 0: Verify Existing GitLab Project Repo & .env Configuration           │
│ Part 1:  Ship App 1 (translate-api: Stateless Deployment)                   │
│          • Step 1: build_and_push.py -a translate-api                       │
│          • Step 2: push_manifests.py -a translate-api -> Sync & Verify :8082│
│ Part 2:  Ship App 2 (upload-api: StatefulSet + 10Gi PVC)                    │
│          • Step 1: build_and_push.py -a upload-api                          │
│          • Step 2: push_manifests.py -a upload-api    -> Sync & Verify :8083│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Terminal Session & Interaction Mode Setup

> [!CAUTION]
> ### 🛑 STRICT INSTRUCTION: Output Welcome Text BEFORE Calling Any Tools
> In your VERY FIRST response message, you **MUST write the Educational Overview and Workshop Steps above as visible chat text** BEFORE invoking any tool calls.

Follow the shared [**`app-interaction-guide`**](../app-interaction-guide/SKILL.md):
1. Resolve `WORKSHOP_DIR` to `application-workshop/`.
2. Detect `tmux` session and create or select the adjacent execution pane (`<target-pane>`).
3. Prompt the user via `ask_question` to choose **Autonomous Mode** (`-y -m`) or **Guided Mode** (staged commands without `-y` or `-m`).
4. Verify that the `gitops-workshop` platform port-forwards (`8080`/`8088` for ArgoCD, `8081` for GitLab Web) are active.

---

## 2. Target Repository & `.env` Configuration

1. Ask the user for the `<group>/<project>` repository they provisioned at the end of `gitops-workshop` (defaulting to `GITLAB_GROUP`/`GITLAB_PROJECT` in `.env`, e.g. `workloads/translate-project`).
2. Verify that `<group>/<project>` exists in GitLab. If they haven't run `provision_project.py` in `gitops-workshop` yet, help them run it from `../gitops-workshop` first.

---

## 3. Part 1: Ship `translate-api` (Stateless Deployment)

Ensure the target GitLab project repository (e.g., `workloads/translate-project`) has been provisioned in `gitops-workshop`.

1. **Step 1 — Build & Push Image**:
   - **Autonomous**: `python3 scripts/build_and_push.py -r workloads/translate-project -a translate-api -y`
   - **Guided**: `python3 scripts/build_and_push.py -r workloads/translate-project -a translate-api`
2. **Step 2 — Overwrite Manifests & Push to GitLab**:
   - **Autonomous**: `python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api --configure-remote -y -m`
   - **Guided**: `python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api --configure-remote`
3. **Sync in ArgoCD & Verify on Port `8082`**:
   - Sync `translate-project-apps` $\rightarrow$ `translate-api` in ArgoCD.
   - Port-forward `kubectl port-forward -n translate-api svc/translate-api 8082:80` and verify [http://localhost:8082](http://localhost:8082).

---

## 4. Part 2: Ship `upload-api` (StatefulSet + 10Gi Persistent Storage)

Ensure the second GitLab project repository (e.g., `workloads/upload-project`) has been provisioned in `gitops-workshop` (`python3 scripts/project_provision/provision_project.py -g workloads -p upload-project -a upload-api`).

1. **Step 1 — Build & Push Image**:
   - **Autonomous**: `python3 scripts/build_and_push.py -r workloads/upload-project -a upload-api -y`
   - **Guided**: `python3 scripts/build_and_push.py -r workloads/upload-project -a upload-api`
2. **Step 2 — Overwrite Manifests & Push to GitLab**:
   - **Autonomous**: `python3 scripts/push_manifests.py -r workloads/upload-project -a upload-api -y -m`
   - **Guided**: `python3 scripts/push_manifests.py -r workloads/upload-project -a upload-api`
3. **Sync in ArgoCD & Verify StatefulSet + PVC on Port `8083`**:
   - Sync `upload-project-apps` $\rightarrow$ `upload-api` in ArgoCD.
   - Inspect `kubectl get statefulset,pods,pvc -n upload-api`.
   - Port-forward `kubectl port-forward -n upload-api svc/upload-api 8083:80` and verify [http://localhost:8083](http://localhost:8083).
