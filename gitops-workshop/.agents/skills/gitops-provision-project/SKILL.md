---
name: gitops-provision-project
description: >-
  Interactive, beginner-friendly guide for self-service tenant project and microservice workload provisioning in GitLab and ArgoCD App-of-Apps GitOps.
  Explains GitOps multi-tenancy concepts, conducts interactive parameter interview, provisions repositories/AppProjects, and guides GitLab MRs, Milestone 5A (Platform Handover), and Milestone 5B (Workload Sync).
---

# Developer Self-Service Project & Workload Provisioning Runbook

Welcome to the **Developer Self-Service Workload Provisioning** guide! 

This skill teaches you how development teams onboard new microservices into a production-grade Kubernetes cluster using declarative GitOps and the **App-of-Apps pattern**.

---

## 📖 Educational Overview & Roadmap

### What We Are Going to Do:
In an enterprise GitOps platform, developers don't write manual `kubectl` scripts or request platform tickets to deploy workloads. Instead, they use self-service automation that:
1. Creates a dedicated team repository and group in **GitLab**.
2. Establishes isolated security boundaries via an **ArgoCD `AppProject`**.
3. Seeds starter microservice manifests into the team's repository.
4. Registers the project in the platform's root GitOps catalog.

### The 4 Journey Steps:
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1: Session & Interaction Setup                                        │
│   - Connect or configure tmux pane and choose Autonomous vs. Guided mode.  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Step 2: Interactive Parameter Interview                                     │
│   - Define your GitLab Group, Project, Application Name, and Owner.         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Step 3: Automated Provisioning & Merge Request Reviews                      │
│   - Run provision_project.py and review/merge MRs in GitLab.                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Step 4: ArgoCD Multi-Level Synchronization                                  │
│   - Milestone 5A: Platform Handover (Project provisioned in GitOps).        │
│   - Milestone 5B: Workload Deployment (Live running microservice).          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Session & Interaction Setup

> [!CAUTION]
> ### 🛑 STRICT INSTRUCTION: Output Welcome Text BEFORE Calling Any Tools
> In your VERY FIRST response message, you **MUST write the Educational Overview and 4 Journey Steps above as visible chat text**.
>
> **DO NOT make a bare tool call** (such as `run_command` with `tmux` or `kubectl`) without accompanying user-facing explanation text in that turn.
>
> Your initial message must explain:
> 1. Welcome to the Developer Self-Service Onboarding guide.
> 2. What GitOps multi-tenancy is and what we're going to build.
> 3. The 4 roadmap steps.
> 4. That you are now checking the terminal environment for an active `tmux` session.

1. **Initial Greeting & Orientation**:
   Send the educational overview and roadmap to the participant in visible markdown text.

2. **Tmux Detection & Execution Mode Selection**:
   Follow the shared [**`gitops-interaction-guide`**](../gitops-interaction-guide/SKILL.md):
   - State to the user: *"Checking terminal environment for an active `tmux` session..."*
   - Detect tmux (`tmux display-message -p '#{session_name}'`) and configure the adjacent execution pane (`<target-pane>`).
   - Prompt user via `ask_question` for **Autonomous Mode** vs. **Guided Mode**.

3. **Prerequisites & Port-Forward Verification**:
   - Inform user: *"Verifying that ArgoCD (http://localhost:8080) and GitLab (http://localhost:8081) port-forwards are active..."*
   - Check if endpoints are reachable; if not, launch the background port-forward daemons in the `port-forwards` tmux window (following Section 5 of `gitops-interaction-guide`):
     ```bash
     # In window: port-forwards
     # Pane argocd-web: kubectl port-forward -n argocd svc/argocd-server 8080:80
     # Pane gitlab-web: kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80
     # Pane gitlab-ssh: kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22
     ```

---

## Step 2: Interactive Parameter Discovery & Interview (`ask_question`)

### 2.1 Information Needed
To provision your project and microservice, we need 4 pieces of information:

| Parameter | Flag | Description & Examples |
| :--- | :--- | :--- |
| **GitLab Group** | `-g` / `--group` | Top-level division or domain in GitLab (e.g. `core-banking`, `ecommerce`, `payments`). |
| **GitLab Project** | `-p` / `--project` | Team repository under the group (e.g. `checkout-team`, `orders`, `ledger`). |
| **Application Name** | `-a` / `--app-name` | Starter microservice name (e.g. `payment-processor`, `frontend-ui`). Deployed to namespace `<app-name>`. |
| **Owner Email** | `-o` / `--owner` | User with Owner (50) access in GitLab. Defaults to `GCP_PROJECT_OWNER` from `.env`. |

---

### 2.2 Discovery Mode Choice (`ask_question`)

Prompt the user using `ask_question`:
> *"Would you like to query and inspect existing GitLab groups and projects first, or do you already know what names you want to use?"*
- **Option 1**: *(Recommended) I already know the Group, Project, and Application names to use.*
- **Option 2**: *Query and list existing GitLab Groups and Projects first.*

---

### 2.3 Query Existing GitLab Entities (if Option 2 selected)

If the user selects Option 2, the agent queries GitLab through the active port-forward:
```python
import gitlab, os
gl = gitlab.Gitlab(os.getenv("GITLAB_HTTP_URL", "http://localhost:8081"), private_token=root_token)
groups = [g.full_path for g in gl.groups.list(all=True)]
projects = [p.path_with_namespace for p in gl.projects.list(all=True)]
```

Present the existing hierarchy in a formatted summary table:

| Type | Existing Entity Path | Description |
| :--- | :--- | :--- |
| **Group** | `gitops-platform` | Platform Root Group |
| **Project** | `gitops-platform/manifests` | Platform Manifests Catalog |
| *(Other)* | `<discovered-group>/<discovered-project>` | Active Tenant Projects |

---

### 2.4 Prompt for Final Parameter Values

Prompt the user for their chosen values:
1. **GitLab Group (`-g`)**: Choose an existing group or specify a new group name.
2. **GitLab Project (`-p`)**: Choose an existing project or specify a new project name.
3. **Application Name (`-a`)**: Specify the starter microservice name (standardizes on container `nginx:1.27-alpine` on port 80).
4. **Owner Email (`-o`)**: Confirm using active `GCP_PROJECT_OWNER` or provide a custom email.

---

## Step 3: Execution & GitLab Merge Requests

### 3.1 Provisioning Command
The agent stages or executes the provisioning command in `<target-pane>`:

- **Autonomous Mode** (includes `-y -m`):
  ```bash
  python3 scripts/project_provision/provision_project.py -g <group> -p <project> -a <app-name> -y -m
  ```

- **Guided Mode** (stages WITHOUT `-y` and WITHOUT `-m` so the participant reviews parameters and confirms interactively):
  ```bash
  python3 scripts/project_provision/provision_project.py -g <group> -p <project> -a <app-name>
  ```
  - After staging, prompt the user via `ask_question`:
    - **Option 1**: *(Recommended) Done - The script finished successfully.*
    - **Option 2**: *There are issues. Help me troubleshoot.*



### 3.2 Review and Merge GitLab Merge Requests
When the script completes, open the GitLab UI ([http://localhost:8081](http://localhost:8081)):

1. **Platform Registration MR (`gitops-platform/manifests`)**:
   - Open: [http://localhost:8081/gitops-platform/manifests/-/merge_requests](http://localhost:8081/gitops-platform/manifests/-/merge_requests)
   - Click **Merge** to register `<project>-apps.yaml` and the team `AppProject` into the platform catalog.
2. **Tenant Workload MR (`<group>/<project>`)**:
   - Open: [http://localhost:8081/<group>/<project>/-/merge_requests](http://localhost:8081/<group>/<project>/-/merge_requests)
   - Click **Merge** to add starter manifests (`manifests/<app-name>/`) into the team's repository.

---

## Step 4: ArgoCD Multi-Level Synchronization

Navigate to the ArgoCD Web UI (**[http://localhost:8080](http://localhost:8080)**):

### 🌟 Milestone 5A: Project Provisioned in GitOps Platform (The Delegation Handover)

1. **Sync `root-app`**:
   - In ArgoCD UI, click **`SYNC`** on `root-app` $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: `root-app` reads `gitops-platform/manifests` and discovers your project's App-of-Apps tile: **`<project>-apps`**.

2. **Sync `<project>-apps`**:
   - Click **`SYNC`** on the **`<project>-apps`** tile $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: Creates the team AppProject and dynamically connects directly to your team's repository (`<group>/<project>.git`), discovering your child workload application tile: **`<app-name>`**.

> [!IMPORTANT]
> ### 🏆 Key Architectural Milestone: Platform Handover Complete!
> At this exact point — after syncing `<project>-apps` and **BEFORE** syncing the individual workload manifest:
> - **The project is officially provisioned in the GitOps Platform.**
> - **The platform repository (`gitops-platform/manifests`) is NEVER touched again for this project.**
> - All future microservices, configuration updates, replica scaling, and CI/CD pipelines are managed **EXCLUSIVELY within your project repository (`<group>/<project>`)**.
> - The platform engineering team has completely delegated control to the development team.

---

### 🌟 Milestone 5B: Workload Deployment & Verification

3. **Sync `<app-name>`**:
   - Click **`SYNC`** on the **`<app-name>`** tile $\rightarrow$ click **`SYNCHRONIZE`**.
   - **Result**: ArgoCD syncs manifests directly from `<group>/<project>` and deploys your microservice into GKE!

4. **Port-Forward & Access Live Microservice**:
   - The agent launches the port-forward in a dedicated pane named `<app-name>-web` in the `port-forwards` window:
     ```bash
     # In window: port-forwards
     # Pane: <app-name>-web
     kubectl port-forward -n <app-name> svc/<app-name> 8082:80
     ```
   - Direct the user to view the running workload:
     > 🌐 **Live Microservice Web Application**:
     > Navigate to **[http://localhost:8082](http://localhost:8082)** in your browser (or run `curl http://localhost:8082`) to verify the live deployed application!
   - Verify pods and services in terminal:
     ```bash
     kubectl get pods,svc -n <app-name>
     ```


5. **Multi-Service Self-Service (Add More Microservices)**:
   - To add a second microservice (e.g. `billing-service`), the team simply adds manifests to their own repository (or re-runs `/gitops-provision-project` with `-a <new-app>`).
   - Syncing `<project>-apps` discovers the new service immediately — with **zero platform PRs or admin tickets required**!

