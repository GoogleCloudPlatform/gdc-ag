# GitOps Workshop End-to-End Bootstrap & Operations Workflow

This document defines the complete end-to-end execution sequence, script responsibilities, parameter requirements, port-forward lifecycles, visual verification milestones, and the pivotal GitOps handover milestone for the GitOps Workshop.

---

## High-Level Execution Sequence

```
[Phase 1: GCP Project & Billing]      ──► scripts/bootstrap/bootstrap.py
                 │                        (Verify in GCP Console)
                 ▼
[Phase 2: GKE Cluster & VPC]           ──► scripts/bootstrap/provision_cluster.py
                 │                        (Verify via kubectl get nodes & GKE Console)
                 ▼
[Phase 3: ArgoCD & Dex OIDC]           ──► scripts/bootstrap/argocd/install_argocd.py
                 │                        [PORT-FORWARD: 8080:80]
                 │                        (🛑 MILESTONE 1: Log in at http://localhost:8080)
                 ▼
[Phase 4: GitLab Omnibus Deployment]   ──► scripts/bootstrap/gitlab/install_gitlab.py
                 │                        [PORT-FORWARDS: 8081:80 & 2222:22]
                 │                        (🛑 MILESTONE 2: Log in at http://localhost:8081)
                 ▼
[Phase 5: GitLab Repo & Manifests MR]  ──► scripts/bootstrap/gitlab/setup_gitlab_repo.py
                 │                        scripts/bootstrap/gitlab/create_manifest_mr.py
                 │                        (🛑 MILESTONE 3: Review & Merge MR #1 in GitLab)
                 ▼
                 ▼
[Phase 6: GitOps SSH Authentication]   ──► scripts/bootstrap/gitops/setup_gitlab_auth.py
                 │                        [RESTART PORT-FORWARDS: 8080, 8081, 2222]
                 │                        (Verify repo-creds & known_hosts)
                 ▼
[Phase 7: Enable App-of-Apps GitOps]   ──► scripts/bootstrap/gitops/enable_gitops.py
                 │                        (Applies root-app manifest to ArgoCD)
                 ▼
[🛑 MANUAL SYNC: ArgoCD Web UI]        ──► Open http://localhost:8080
                 │                        1. SYNC 'root-app' (discovers child apps)
                 │                        2. SYNC 'argocd' & 'gitlab'
                 │                        (🎉 BIG MILESTONE 4: GitOps Platform Self-Managing!)
                 ▼
[Phase 8: Project & App Provisioning]  ──► scripts/project_provision/provision_project.py
                 │                        (🛑 MILESTONE 5A: Project Provisioned in Platform - Handover!)
                 │                        (🛑 MILESTONE 5B: Workload Deployment & Verification)
```

---

## Configuration & Environment Variables (`.env`)

All scripts must be executed from inside the `gitops-workshop/` directory and read their required infrastructure configuration, endpoints, and identity parameters strictly from a local `.env` file located in the execution directory (or specified via `-e` / `--env-file`).

To get started, enter the `gitops-workshop/` directory, copy the template for your target platform, and configure your project details:

```bash
cd gitops-workshop
cp .env.gcp.example .env
```

Refer directly to [`.env.gcp.example`](../.env.gcp.example) (or [`.env.gdc.example`](../.env.gdc.example) when targeting GDC-Sandbox) as the single source of truth for required Day-0 variables, optional Google OAuth/SSO settings (Phases 3 & 4), and advanced overrides.

---

## Detailed Phases & Verification Runbook

### Phase 1: GCP Project Verification, Creation & Billing
- **Script**: `python3 scripts/bootstrap/bootstrap.py`
- **Purpose**: Checks if the target GCP project exists in Google Cloud. If missing, automatically creates the project (`gcloud projects create`), links the active Billing Account, and binds `roles/owner` IAM permissions to `GCP_PROJECT_OWNER`.
- **Command**:
  ```bash
  python3 scripts/bootstrap/bootstrap.py
  ```
- **What You Can See & Do Upon Completion**:
  1. **GCP Console**: Open [https://console.cloud.google.com/welcome](https://console.cloud.google.com/welcome) and select your target project.
  2. **Billing Verification**: Open [Billing Console](https://console.cloud.google.com/billing) and verify that the project is linked to an active, open billing account.
  3. **IAM & Admin**: Open [IAM Console](https://console.cloud.google.com/iam-admin/iam) and confirm that the configured `GCP_PROJECT_OWNER` user possesses the **Owner** (`roles/owner`) role.
     - *Note on Inherited Roles*: If your user account also holds organization-level privileges (such as **Organization Administrator**), the Cloud Console may display `Organization Administrator (Inherited)` alongside or in the principal drawer. Both direct `Owner` and inherited administrative roles grant full project permissions.
     - *Terminal Verification*: You can confirm direct project binding via:
       ```bash
       gcloud projects get-iam-policy <project_id> --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:<GCP_PROJECT_OWNER>"
       ```



---

### Phase 2: GKE Cluster & VPC Provisioning
- **Script**: `python3 scripts/bootstrap/provision_cluster.py`
- **Purpose**: Enables required GCP APIs (`container.googleapis.com`, `compute.googleapis.com`), creates private VPC network (`<cluster_name>-vpc`), Cloud Router, Cloud NAT, and provisions the GKE Autopilot cluster.
- **Command**:
  ```bash
  python3 scripts/bootstrap/provision_cluster.py
  ```
- **What You Can See & Do Upon Completion**:
  1. **Kubernetes Deployments**: Run `kubectl get deployments -A` to verify cluster API connectivity. *(Note: In GKE Autopilot, worker nodes scale up dynamically on demand as workloads deploy, so system deployments may initially show 0 ready replicas while nodes initialize).*
  2. **GKE Console**: Open [GKE Clusters Console](https://console.cloud.google.com/kubernetes/list) to see cluster status as **Healthy / Running**.

  3. **VPC Network**: Open [VPC Networks](https://console.cloud.google.com/net-vpc/networks/list) to confirm `<cluster_name>-vpc` exists.
  4. **Cloud NAT**: Open [Cloud NAT Console](https://console.cloud.google.com/net-services/nat/list) to verify outbound internet egress for private nodes.

---

### Phase 3: ArgoCD & GCP OIDC Installation
- **Script**: `scripts/bootstrap/argocd/install_argocd.py`
- **Purpose**: Applies ArgoCD base & overlay manifests into namespace `argocd`, injects Google Cloud OAuth credentials and Dex connector in `argocd-cm`, auto-generates the RBAC `policy.csv` mapping the project owner to `role:admin`, and sets up HTTP mode for `localhost:8080`.
- **Command**:
  ```bash
  python3 scripts/bootstrap/argocd/install_argocd.py
  ```
- **RBAC & Authorization (`policy.csv`)**:
  - The script checks for `manifests/argocd/base/policy.csv`. If not present, it initializes it from `policy.csv.example` and automatically binds your project owner identity (`GCP_PROJECT_OWNER` from `.env`) to the administrator role (`g, <project_owner_email>, role:admin`).
  - Kustomize packs `policy.csv` directly into the `argocd-rbac-cm` ConfigMap.
  - To grant administrative or read-only access to additional team members, add their email addresses to `manifests/argocd/base/policy.csv` and re-run `install_argocd.py`.
- **Port-Forward Action**:
  > **Start ArgoCD Port-Forward**:
  > ```bash
  > kubectl port-forward -n argocd svc/argocd-server 8080:80
  > ```
- **🛑 MILESTONE 1 — What You Can See & Do Upon Completion**:
  1. **Open ArgoCD UI**: Navigate to **[http://localhost:8080](http://localhost:8080)**.
  2. **Google OAuth Login**: Click **Log in via Google** and authenticate using your project owner Google account (`GCP_PROJECT_OWNER`).
  3. **ArgoCD Dashboard & Admin RBAC**: Verify that the ArgoCD applications view loads cleanly with full administrator privileges (ability to create/sync applications and manage repositories) and your username / email shown in the user panel.
  4. **Control Plane Pods**: Run `kubectl get pods -n argocd` to confirm `argocd-server`, `argocd-repo-server`, `argocd-dex-server`, `argocd-application-controller`, and `argocd-redis` are in `Running` state.

---

### Phase 4: GitLab Omnibus Installation & Storage
- **Script**: `scripts/bootstrap/gitlab/install_gitlab.py`
- **Purpose**: Deploys single-pod GitLab Omnibus CE with a 30Gi `PersistentVolumeClaim` (`gitlab-pvc`) to persist repositories and PostgreSQL state across pod restarts, and seeds the root Personal Access Token.
- **Command**:
  ```bash
  python3 scripts/bootstrap/gitlab/install_gitlab.py
  ```
- **Port-Forward Actions**:
  > **Start GitLab Port-Forwards**:
  > ```bash
  > # Web UI & REST API
  > kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80
  > 
  > # Git SSH Transport
  > kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22
  > ```
- **🛑 MILESTONE 2 — What You Can See & Do Upon Completion**:
  1. **Open GitLab UI**: Navigate to **[http://localhost:8081](http://localhost:8081)**.
  2. **Admin or OAuth Login**:
     - **Root Admin**: Username `root`, Password printed in the CLI completion panel (or `GITLAB_ROOT_PASSWORD_OVERRIDE` if set in `.env`).
     - **Google OAuth**: Click the **Google** button to sign in directly.
  3. **Welcome Page**: Confirm the GitLab welcome dashboard is visible and accessible.
  4. **Persistent Storage**: Run `kubectl get pvc -n gitlab` to verify the 30Gi `gitlab-pvc` is in `Bound` status.

---

### Phase 5: GitLab Repository Setup & Manifests Merge Request
- **Scripts**:
  1. `python3 scripts/bootstrap/gitlab/setup_gitlab_repo.py`
  2. `python3 scripts/bootstrap/gitlab/create_manifest_mr.py`
- **Purpose**:
  - `setup_gitlab_repo.py`: Uses the `python-gitlab` SDK to ensure group `gitops-platform`, project `manifests`, default branch `main`, and user `oscar` with workstation SSH key.
  - `create_manifest_mr.py`: Pushes initial Kubernetes manifests to branch `feature/initial-manifests` and opens Merge Request #1.
- **Commands**:
  ```bash
  python3 scripts/bootstrap/gitlab/setup_gitlab_repo.py
  python3 scripts/bootstrap/gitlab/create_manifest_mr.py
  ```
- **🛑 MILESTONE 3 — What You Can See & Do Upon Completion**:
  1. **Explore Repository**: Open **[http://localhost:8081/gitops-platform/manifests](http://localhost:8081/gitops-platform/manifests)** in GitLab.
  2. **Review Members**: Check **Project Settings > Members** to verify `oscar` has Owner permissions.
  3. **Review Merge Request #1**: Open **[http://localhost:8081/gitops-platform/manifests/-/merge_requests/1](http://localhost:8081/gitops-platform/manifests/-/merge_requests/1)**.
  4. **Inspect Changes**: View the file diffs (`manifests/apps/`, `manifests/argocd/`, `manifests/gitlab/`, `manifests/project.yaml`, `manifests/root-app.yaml`).
  5. **Merge**: Click **Merge** to merge the initial baseline into `main`.

---

### Phase 6: GitOps SSH Authentication Setup
- **Script**: `scripts/bootstrap/gitops/setup_gitlab_auth.py`
- **Purpose**: Configures machine-to-machine trust between ArgoCD and GitLab: creates `argocd-readonly` service user with Reporter permissions via `python-gitlab` SDK, preserves existing ED25519 deploy key in `creds-gitlab-ssh`, updates `argocd-ssh-known-hosts-cm` with active GitLab host key, restarts `argocd-repo-server`, and verifies connectivity.
- **Command**:
  ```bash
  python3 scripts/bootstrap/gitops/setup_gitlab_auth.py
  ```
- **⚠️ Port-Forward Action Required (Restart Port-Forwards)**:
  > Because `setup_gitlab_auth.py` restarts `argocd-repo-server` and `argocd-application-controller`, active port-forwards may be disconnected.
  > **Relaunch background port-forwards**:
  > ```bash
  > pkill -f "kubectl port-forward" || true
  > kubectl port-forward -n argocd svc/argocd-server 8080:80
  > kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80
  > kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22
  > ```
- **What You Can See & Do Upon Completion**:
  1. **Service User**: In GitLab Admin (**Admin > Users**), locate user `argocd-readonly` and verify the `ArgoCD Read-Only Key` SSH public key attached under their profile.
  2. **ArgoCD Credentials Secret**: Run `kubectl get secret -n argocd creds-gitlab-ssh` to confirm the pattern-based credential secret exists.
  3. **Known Hosts ConfigMap**: Run `kubectl get cm -n argocd argocd-ssh-known-hosts-cm` to verify the internal GitLab SSH host key is registered.
  4. **Reporter Access**: In GitLab, open **`gitops-platform` Group > Members** to confirm `argocd-readonly` has **Reporter** access.

---

### Phase 7: Enable App-of-Apps GitOps & Handover (The Pivotal Step)

> [!IMPORTANT]
> ### 🌟 Why This Step is Critical: The Declarative GitOps Handover
> Up until this point, all Kubernetes resources (ArgoCD, GitLab, ConfigMaps, Secrets) were created imperatively via local Python scripts executing `kubectl apply` commands.
>
> Running **`enable_gitops.py`** applies `manifests/project.yaml` and `manifests/root-app.yaml` to ArgoCD, establishing the **App-of-Apps control loop**.
> 
> When you click **SYNC** in ArgoCD during this milestone:
> - **ArgoCD officially adopts and takes over lifecycle management** of all cluster infrastructure (`root-app`, `argocd`, and `gitlab`) from Git.
> - Any future changes (configuration updates, scaling, new microservice deployments) will now be driven **declaratively by Git commits** rather than manual `kubectl` commands.
> - This represents the complete handover from initial bootstrapping to continuous GitOps operations.

- **Script**: `scripts/bootstrap/gitops/enable_gitops.py`
- **Command**:
  ```bash
  python3 scripts/bootstrap/gitops/enable_gitops.py
  ```

---

### 🛑 CRITICAL MANUAL ACTION: Initial ArgoCD GitOps Synchronization

> [!CAUTION]
> **ArgoCD sync operations are NEVER performed automatically by the scripts.**
> Manual synchronization is an intentional GitOps workshop principle (`syncPolicy.automated` is disabled) so participants actively review diffs and execute sync approvals.
>
> **You MUST perform the following 3 sync actions in the ArgoCD Web UI before proceeding to Phase 8:**

1. **Open ArgoCD Web UI**:
   Navigate to **[http://localhost:8080](http://localhost:8080)** in your browser. (Log in via Google OAuth or native `admin` credentials).

2. **Step 1 — Sync `root-app`**:
   - On the Applications dashboard, locate the **`root-app`** tile (it will show yellow `OutOfSync`).
   - Click the **`SYNC`** button on the `root-app` card $\rightarrow$ click **`SYNCHRONIZE`** in the confirmation panel.
   - Within 5-10 seconds, `root-app` transitions to green **`Synced`**.
   - **Observe**: Two new child platform application tiles dynamically appear on your dashboard: **`argocd`** and **`gitlab`**!

3. **Step 2 — Sync Child Platform Applications (`argocd` & `gitlab`)**:
   - Click **`SYNC`** on the **`argocd`** tile $\rightarrow$ click **`SYNCHRONIZE`** (transitions to **`Synced`** / **`Healthy`**).
   - Click **`SYNC`** on the **`gitlab`** tile $\rightarrow$ click **`SYNCHRONIZE`** (transitions to **`Synced`** / **`Healthy`**).

4. **Verify in Terminal**:
   Run the following command to confirm that all 3 applications are tracked, synchronized, and healthy:
   ```bash
   kubectl get applications -n argocd
   ```
   **Expected Output**:
   ```text
   NAME       SYNC STATUS   HEALTH STATUS
   argocd     Synced        Healthy
   gitlab     Synced        Healthy
   root-app   Synced        Healthy
   ```

5. 🎉 **Milestone 4 Complete!** ArgoCD and GitLab are now fully self-managing through the GitOps platform.

---

### Phase 8: Self-Service Workload Project & App Provisioning
- **Script**: `scripts/project_provision/provision_project.py`
- **Purpose**: Fully automated, self-service provisioning for development teams:
  1. Creates GitLab group and project repository.
  2. Assigns team owner (Owner: 50) and `argocd-readonly` (Reporter: 20) permissions via `python-gitlab` SDK.
  3. Renders starter microservice workload manifests (`-a <app-name>`) into the project repository.
  4. Creates dedicated ArgoCD AppProject and registers `<project>-apps` root in `gitops-platform/manifests`.
- **Command Syntax**:
  ```bash
  python3 scripts/project_provision/provision_project.py -g <group> -p <project> -a <app-name>
  ```

#### Provisioning Parameters:

| Parameter Flag | Name | Purpose & Description |
| :--- | :--- | :--- |
| **`-g` / `--group`** | GitLab Group | The top-level group or organization in GitLab (e.g. division, department, or business unit). |
| **`-p` / `--project`** | GitLab Project | The project repository under the group (e.g. team repository or service domain). |
| **`-a` / `--app-name`** | Application Name | The microservice workload name (required). Standardizes on starter container `nginx:1.27-alpine` on port 80. |
| **`-o` / `--owner`** | Group Owner Email | Optional: The user email assigned **Owner (50)** permissions. Defaults to `GCP_PROJECT_OWNER` from `.env`. |

---

### 🛑 MANUAL ACTION: Tenant Workload Multi-Level Sync in ArgoCD

After running `provision_project.py` and merging any open Merge Requests in GitLab, deploy your new workload via the ArgoCD Web UI (**[http://localhost:8080](http://localhost:8080)**):

#### 🌟 Milestone 5A — Project Provisioned in GitOps Platform (The Delegation Handover)

1. **Step 1 — Sync `root-app`**:
   - In ArgoCD UI, click **`SYNC`** on `root-app` $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: `root-app` reads the updated platform repository (`gitops-platform/manifests`) and dynamically discovers the new project App-of-Apps tile: **`<project>-apps`**.

2. **Step 2 — Sync `<project>-apps`**:
   - Click **`SYNC`** on the **`<project>-apps`** tile $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: Creates the team AppProject (setting security boundaries) and dynamically connects directly to the tenant's own repository (`<group>/<project>.git`), discovering the child workload application tile: **`<app-name>`**.

> [!IMPORTANT]
> ### 🏆 Key Architectural Milestone: Platform Handover Complete!
> At this exact point — after syncing `<project>-apps` and **BEFORE** syncing the individual workload manifest:
> - **The project is officially provisioned in the GitOps Platform.**
> - **The platform repository (`gitops-platform/manifests`) is NEVER touched again for this project.**
> - All future microservices, configuration updates, replica scaling, and CI/CD pipelines are managed **EXCLUSIVELY within the team's project repository (`<group>/<project>`)**.
> - The platform engineering team has completely delegated control to the application development team.

---

#### 🌟 Milestone 5B — Workload Deployment & Verification

3. **Step 3 — Sync `<app-name>`**:
   - Click **`SYNC`** on the **`<app-name>`** tile $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: ArgoCD syncs manifests directly from `<group>/<project>` and deploys the microservice deployment, service, and namespace into the GKE cluster!

4. **Port-Forward & Access Live Microservice**:
   - **Start Workload Port-Forward**:
     ```bash
     kubectl port-forward -n <app-name> svc/<app-name> 8082:80
     ```
   - **Open Microservice Web Page**:
     Navigate to **[http://localhost:8082](http://localhost:8082)** in your browser (or run `curl http://localhost:8082`) to verify the live running workload!
   - **Inspect Pods & Services in Terminal**:
     ```bash
     kubectl get pods,svc -n <app-name>
     ```

5. **Add More Microservices (Multi-App Self-Service)**:
   - To add a second microservice (e.g. `billing-service`), the development team simply adds manifests to their own repository (or runs `provision_project.py -g <group> -p <project> -a <new-app-name>`).
   - Syncing `<project>-apps` discovers the new service immediately — with **zero platform PRs or admin tickets required**!

