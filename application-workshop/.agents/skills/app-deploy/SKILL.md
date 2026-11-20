---
name: app-deploy
description: >-
  Fast-track iterative build, push, and GitOps deployment skill for application-workshop.
  Use when deploying or updating a workload under apps/<app-name>/ (translate-api or upload-api) into an existing GitLab project repository via Step 1 (build_and_push.py) and Step 2 (push_manifests.py).
---

# Iterative Application Build & GitOps Ship Runbook (`/app-deploy`)

Welcome to the **Iterative Application Build & GitOps Deployment** guide!

Use this skill whenever you want to ship or update one of the workloads in `apps/` (`translate-api` or `upload-api`) into your GitLab project repository.

---

## 1. Session Setup & Orientation

> [!CAUTION]
> ### 🛑 Output Welcome Text BEFORE Calling Any Tools
> Always greet the user and explain the 2-step release flow before invoking any tool calls, following [**`app-interaction-guide`**](../app-interaction-guide/SKILL.md).

1. Resolve `WORKSHOP_DIR` to `application-workshop/`.
2. Detect `tmux` and select `<target-pane>`.
3. Ask the user via `ask_question` for:
   - Which application to ship (`-a translate-api` or `-a upload-api`)
   - Target GitLab project repository (`-r <group>/<project>`)
   - Image tag (`-t v1.0.0`)
   - Execution mode (**Autonomous Mode** `-y -m` vs **Guided Mode**)

---

## 2. Two-Step Release Execution

### Step 1: Build & Push Container Image (`scripts/build_and_push.py`)
- **Autonomous Mode**:
  ```bash
  python3 scripts/build_and_push.py -r <group>/<project> -a <app-name> -t <tag> -y
  ```
- **Guided Mode**:
  ```bash
  python3 scripts/build_and_push.py -r <group>/<project> -a <app-name> -t <tag>
  ```

### Step 2: Integrate Manifests & Push to GitLab (`scripts/push_manifests.py`)
- **Autonomous Mode**:
  ```bash
  python3 scripts/push_manifests.py -r <group>/<project> -a <app-name> -t <tag> -y -m
  ```
- **Guided Mode**:
  ```bash
  python3 scripts/push_manifests.py -r <group>/<project> -a <app-name> -t <tag>
  ```

### Step 3: Sync in ArgoCD & Verify Rollout
1. Sync `<project>-apps` $\rightarrow$ `<app-name>` in ArgoCD.
2. Verify the rollout in namespace `<app-name>` (`kubectl get pods,svc,pvc -n <app-name>`) and port-forward (`8082:80` for `translate-api`, `8083:80` for `upload-api`).
