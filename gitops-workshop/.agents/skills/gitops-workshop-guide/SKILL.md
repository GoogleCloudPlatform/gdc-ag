---
name: gitops-workshop-guide
description: >-
  Interactive end-to-end orchestrator and guide for bootstrapping and operating the GitOps Workshop environment (GCP Project, GKE, ArgoCD, GitLab, and App-of-Apps GitOps).
  Manages mode selection, tmux pane command staging, .env configuration validation/interview, automated background port-forwarding & recreation, and step-by-step execution following docs/bootstrap-workflow.md.
---

# GitOps Workshop Guided Bootstrap & Operating Runbook

Welcome to the **GitOps Workshop Bootstrap & Operating Guide**!

This skill orchestrates the end-to-end deployment of an enterprise-grade GitOps Platform on Google Cloud Platform according to the authoritative documentation in [**`docs/bootstrap-workflow.md`**](../../../docs/bootstrap-workflow.md).

---

## 📖 Educational Overview & Roadmap

### What We Are Building:
Throughout this workshop, we will build a complete, production-ready GitOps control plane that hosts:
1. **Google Kubernetes Engine (GKE Autopilot)** cluster with VPC networking.
2. **ArgoCD GitOps Controller** configured with Google Cloud OAuth 2.0 (OIDC) Single Sign-On.
3. **Internal GitLab Git Server** for hosting platform manifests and team repositories.
4. **App-of-Apps GitOps Loop** that establishes continuous, declarative cluster reconciliation.

### High-Level Workshop Phases:
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: GCP Project Verification, Creation & Billing                       │
│ Phase 2: GKE Autopilot Cluster & VPC Network Provisioning                  │
│ Phase 3: ArgoCD & Google Cloud OAuth Setup (🛑 Milestone 1: Login)          │
│ Phase 4: GitLab Omnibus Internal Git Server (🛑 Milestone 2: Login)         │
│ Phase 5: Seed GitLab Platform Manifests (🛑 Milestone 3: Merge MR #1)       │
│ Phase 6: ArgoCD <-> GitLab Machine Trust & SSH Auth Reconciliation          │
│ Phase 7: App-of-Apps GitOps Handover (🛑 Milestone 4: Manual Sync in UI)    │
│ Phase 8: Tenant Workload Self-Service (via /gitops-provision-project skill) │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Terminal Session & Interaction Mode Setup

The agent **MUST initialize the terminal session and execution mode** following the shared [**`gitops-interaction-guide`**](../gitops-interaction-guide/SKILL.md):

1. **Tmux Detection & Pane Selection**:
   - Detect tmux session (`tmux display-message -p '#{session_name}'`).
   - Create (`tmux split-window -h -c "#{pane_current_path}"`) or select the adjacent execution pane (`<target-pane>`).
   - If not in tmux, recommend tmux or offer standard terminal execution.

2. **Execution Mode Selection (`ask_question`)**:
   - **Autonomous Mode**: The agent appends `-y` (auto-approve prompts) and `-m` (auto-merge GitLab MRs) and dispatches commands with Enter so you can watch live execution in the adjacent pane.
   - **Guided Mode**: The agent stages commands in the pane without `-y` and without `-m` (and without Enter), letting you review parameters, press Enter, confirm in the terminal, and review MR diffs in GitLab manually.

3. **Command Dispatch Standards**:
   - Autonomous: `tmux send-keys -t <target-pane> "<command> -y -m" C-m`
   - Guided (No `-y`, No `-m`): `tmux send-keys -t <target-pane> -l "<command>"`
     - After staging, prompt the user via `ask_question`: **1. Done - The script finished successfully**, or **2. There are issues. Help me troubleshoot.**
   - Output Verification: `tmux capture-pane -t <target-pane> -p -S -50`



---

## 2. `.env` Validation, Initialization & Interactive Interview

Once mode and tmux setup are complete, the agent **MUST manage the `.env` configuration** before executing any provisioning scripts.

### Step 2.1: Existing `.env` Check & Mode Selection (`ask_question`)

1. **Check if `.env` exists in workspace**:
   - **If `.env` exists**: Prompt the user using `ask_question`:
     > *"An existing `.env` file was found. Would you like to use your existing configuration or start fresh with a new `.env` for this workshop?"*
     - **Option 1**: *(Recommended) Use existing `.env` file.*
     - **Option 2**: *Start fresh with a new `.env` file.*

2. **If Starting Fresh (or `.env` does not exist)**:
   - **Backup the old `.env`**:
     ```bash
     if [ -f .env ]; then
       PROJ=$(grep -E "^GCP_PROJECT=" .env | cut -d '=' -f2 | tr -d '"'\'' ' || echo "unknown")
       cp .env ".env.bak.${PROJ:-unknown}.$(date +%Y%m%d_%H%M%S)"
     fi
     ```
   - **Preserve Existing Google OAuth / OIDC Credentials**:
     - Check if the previous `.env` contains populated `GCP_OIDC_CLIENT_ID` and `GCP_OIDC_CLIENT_SECRET`.
     - If found, prompt the user using `ask_question`:
       > *"Google OAuth 2.0 / OIDC credentials were found in your previous `.env`. Would you like to preserve them in the new `.env` file?"*
       - **Option 1**: *(Recommended) Yes, preserve existing Google OAuth / OIDC credentials.*
       - **Option 2**: *No, start with clean/empty OIDC credentials.*
   - **Initialize new `.env`**:
     - Copy [`.env.gcp.example`](../../../.env.gcp.example) (or [`.env.gdc.example`](../../../.env.gdc.example) if targeting GDC-Sandbox) to `.env`.
     - If the user chose to preserve OIDC credentials, inject the preserved `GCP_OIDC_CLIENT_ID` and `GCP_OIDC_CLIENT_SECRET` into the new `.env`.
   - **Interview User for Required Day-0 Variables**:
     - Prompt the user for their workshop parameters: `GCP_PROJECT`, `GCP_PROJECT_OWNER`, `GCP_REGION`, and `GKE_CLUSTER_NAME`.

### Step 2.2: Display Current `.env` Parameters
Read `.env` (using [`.env.gcp.example`](../../../.env.gcp.example) as the schema definition) and present the current values in a formatted markdown summary table grouped into:
1. **Section 1: Required Day-0 Bootstrap Parameters** (`GCP_PROJECT`, `GCP_PROJECT_OWNER`, `GCP_REGION`, `GKE_CLUSTER_NAME`, `ARGOCD_SERVER_URL`, `GITLAB_HTTP_URL`, optional `GCP_BILLING_ACCOUNT`).
2. **Section 2: User Authentication (OAuth / OIDC)** (`GCP_OIDC_CLIENT_ID`, `GCP_OIDC_CLIENT_SECRET`).
3. **Section 3: Advanced Overrides** (`GCP_VPC_NETWORK_OVERRIDE`, `GITLAB_ROOT_PASSWORD_OVERRIDE`, `GITLAB_ROOT_TOKEN_OVERRIDE`).

### Step 2.3: Configuration Confirmation & Optional OIDC Setup (`ask_question`)

1. **Inspect OIDC Status**:
   - Check if `GCP_OIDC_CLIENT_ID` or `GCP_OIDC_CLIENT_SECRET` is missing or empty in `.env`.
   - If missing, inform the user:
     > *"Google OAuth 2.0 / OIDC is not yet configured in `.env`. You can either proceed with native admin accounts (`admin` & `root`) or configure Google Single Sign-On for 1-click browser login."*

2. **Prompt for Configuration Confirmation**:
   Ask the user if the current `.env` settings are valid for this run:
   - **Option 1**: *(Recommended) Yes, the current `.env` is ready to use.*
   - **Option 2**: *I want to set up Google Cloud OAuth / OIDC (Single Sign-On).*
   - **Option 3**: *I want to change the GCP Project ID.*
   - **Option 4**: *I want to change the Project Owner email.*
   - **Option 5**: *I want to update multiple configuration values.*

3. **Guided Google OAuth Setup (if selected)**:
   If the user selects Option 2 (Set up Google Cloud OAuth / OIDC):
   - Direct the user to configure the OAuth consent screen:
     1. Open [OAuth Consent Screen Console](https://console.cloud.google.com/apis/credentials/consent) and select User Type **Internal** (or External).
   - Direct the user to create the Web Application client:
     2. Open [Credentials Console](https://console.cloud.google.com/apis/credentials) $\rightarrow$ **Create Credentials** $\rightarrow$ **OAuth client ID** $\rightarrow$ **Web application**.
     3. Add **Authorized redirect URIs**:
        - `http://localhost:8080/api/dex/callback` (ArgoCD Dex)
        - `http://localhost:8081/users/auth/google_oauth2/callback` (GitLab OmniAuth)
   - Prompt the user to provide the generated **Client ID** and **Client Secret**, and update `.env`.

4. **Apply Updates & Re-display Table**:
   If any `.env` changes were made, re-display the summary table to confirm before proceeding to Phase 1.

---

## 3. Automated Port-Forwarding Lifecycle & Dedicated Window (`port-forwards`)

Kubernetes `port-forward` connections attach to specific pod endpoints and automatically terminate whenever a pod or deployment is restarted, rolled out, or patched. 

The agent **MUST automatically manage and recreate** background port-forward daemons in dedicated labeled panes within a single tmux window named `port-forwards` (following Section 5 of [**`gitops-interaction-guide`**](../gitops-interaction-guide/SKILL.md)):

### 3.1 Initial Port-Forward Launches:
- **Phase 3 (ArgoCD)**: After `install_argocd.py` completes, create/attach pane `argocd-web` in window `port-forwards`:
  ```bash
  kubectl port-forward -n argocd svc/argocd-server 8080:80
  ```
- **Phase 4 (GitLab)**: After `install_gitlab.py` completes, create/attach panes `gitlab-web` and `gitlab-ssh` in window `port-forwards`:
  ```bash
  # Pane: gitlab-web
  kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80
  # Pane: gitlab-ssh
  kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22
  ```

### 3.2 Mandatory Port-Forward Recreation After Restarts:
Whenever an operation restarts or patches ArgoCD or GitLab deployments:
- **Phase 6 (`setup_gitlab_auth.py`)**: Restarts `argocd-repo-server` and `argocd-application-controller`.
- **Any Service Re-installation or Rollout**:

**The agent MUST proactively:**
1. Clean up stale port-forward processes:
   ```bash
   pkill -f "kubectl port-forward -n argocd" || true
   pkill -f "kubectl port-forward -n gitlab" || true
   ```
2. Re-launch the port-forwards in the `port-forwards` window with labeled panes:
   - Pane `argocd-web`: `kubectl port-forward -n argocd svc/argocd-server 8080:80`
   - Pane `gitlab-web`: `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80`
   - Pane `gitlab-ssh`: `kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22`
3. Prompt the user to verify the UI dashboards are accessible before proceeding.


---

## 4. Step-by-Step Execution Sequence (Phases 1 to 7)

The agent MUST read and execute following the authoritative phases, parameter tables, and visual verification gates defined in [**`docs/bootstrap-workflow.md`**](../../../docs/bootstrap-workflow.md):

- **Phase 1**: GCP Project Verification, Creation & Billing (`scripts/bootstrap/bootstrap.py`)
- **Phase 2**: GKE Autopilot Cluster & VPC Network (`scripts/bootstrap/provision_cluster.py`)
- **Phase 3**: ArgoCD & GCP OIDC Installation (`scripts/bootstrap/argocd/install_argocd.py`) $\rightarrow$ **Milestone 1** (Port-forward `8080`, login)
- **Phase 4**: GitLab Omnibus Internal Git Server (`scripts/bootstrap/gitlab/install_gitlab.py`) $\rightarrow$ **Milestone 2** (Port-forwards `8081` & `2222`, login)
- **Phase 5**: Seed GitLab Manifests Repository (`scripts/bootstrap/gitlab/seed_gitlab.py`) $\rightarrow$ **Milestone 3** (Merge Request in GitLab)
- **Phase 6**: Reconcile ArgoCD $\leftrightarrow$ GitLab SSH Authentication (`scripts/bootstrap/gitops/setup_gitlab_auth.py`) $\rightarrow$ Recreate port-forwards
- **Phase 7**: Handover to Root App-of-Apps GitOps Loop (`scripts/bootstrap/gitops/enable_gitops.py`)
- **🛑 CRITICAL MILESTONE 4 (Manual ArgoCD UI Sync)**: The agent **MUST STOP and instruct the user** to open [http://localhost:8080](http://localhost:8080), click **SYNC** on `root-app` (which dynamically discovers child platform apps), and then click **SYNC** on `argocd` and `gitlab`. The agent confirms all 3 applications are `Synced` and `Healthy` via `kubectl get applications -n argocd` before continuing.

---

## 5. Next Steps: Tenant Workload Onboarding

Once Milestone 4 is verified:
🎉 **The GitOps Platform Bootstrap is COMPLETE!**

Direct the user to the dedicated **`gitops-provision-project`** skill ([`.agents/skills/gitops-provision-project/SKILL.md`](../gitops-provision-project/SKILL.md)) for developer self-service project and microservice provisioning:
- Triggered directly via the `/gitops-provision-project` skill.
- Interactively gathers team details (`-g <group> -p <project> -a <app-name>`).
- Guides Milestone 5A (Platform Handover) and Milestone 5B (Tenant Workload Deployment).
