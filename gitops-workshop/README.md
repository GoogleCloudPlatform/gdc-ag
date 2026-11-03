# GitOps Workshop

A hands-on, end-to-end GitOps workshop on Google Cloud featuring **GKE Autopilot**, a private self-hosted **GitLab Omnibus**, and **ArgoCD** operating under the declarative **App-of-Apps** pattern.

### 🎯 What You Will Learn

In this lab, you will build and operate a complete enterprise GitOps platform from scratch, gaining hands-on experience with:

- **Declarative GitOps Architecture**: How to manage Kubernetes clusters, platform components, and tenant workloads entirely through Git as the single source of truth.
- **The App-of-Apps Pattern**: How ArgoCD discovers, deploys, and recursively manages platform tools and tenant workloads using hierarchical root/child application manifests.
- **Self-Hosting Enterprise Platform Components**: Bootstrapping self-hosted GitLab Omnibus and ArgoCD directly on GKE Autopilot with persistent volumes and internal cluster networking.
- **Zero-Trust & SSO Integration**: Configuring Google Cloud OAuth 2.0 / OIDC single sign-on for human operators and SSH keypair/deploy-key authentication for automated machine-to-machine repository access.
- **GitOps Pull-Request / Merge-Request Workflow**: How platform changes and application deployments are proposed, code-reviewed, and merged in GitLab before ArgoCD synchronizes them into the cluster.
- **Multi-Tenant Self-Service Workload Onboarding**: How development teams can independently spin up isolated repositories, RBAC-scoped ArgoCD `AppProjects`, and deploy new workloads without requiring platform admin intervention or central manifest changes.

---

## 🛠️ Prerequisites

Before getting started, ensure you have the following installed and configured on your workstation:

- **Google Cloud SDK (`gcloud`)**: Authenticated with privileges to create GCP projects and GKE clusters (`gcloud auth login`).
- **`kubectl`**: Kubernetes CLI.
- **Python 3.10+**: With required dependencies (`pip install -r requirements.txt` or `rich`, `python-gitlab`, `pyyaml`).
- **`tmux` & `git`**: For split-pane command staging and repository management.
- **Antigravity CLI (`agy`)**: For interactive AI workshop orchestration.

---

## 🚀 Quick Start (Interactive Guided Workshop)

For the best experience, run the interactive AI workshop guide inside a `tmux` session. The guide automatically splits your window, validates `.env` parameters, stages commands for you to review and execute, and manages background port-forwarding.

### 1. Enter Workshop Directory & Launch `tmux` + Antigravity
```bash
cd gitops-workshop
tmux
agy
```

### 2. Run the Workshop Guide Skill (Bootstrap & Platform Setup)
Prompt the agent:
> *"Start the workshop"* or *"`/gitops-workshop-guide`"*

The guide will:
1. Conduct an interactive interview for your GCP Project ID, billing account, and owner email.
2. Stage commands phase-by-phase in an adjacent tmux pane for transparent execution.
3. Automatically launch and maintain background port-forwards for all web dashboards and SSH traffic.
4. Guide you through Merge Request reviews, manual ArgoCD syncs, and the core platform setup.

### 3. Provision New Workloads (Self-Service Onboarding)
Once the GitOps platform is running, prompt the agent:
> *"Provision a new project"* or *"`/gitops-provision-project`"*

The provisioning skill will:
- Interview you for your tenant project and GitLab group name.
- Automatically provision isolated GitLab repositories, ArgoCD `AppProject` RBAC, and deploy a sample starter microservice.
- Walk you through the Merge Request review and ArgoCD synchronization to deploy the live workload!

---

## 🌐 Local Access & Port Summary

When running the platform, services are accessible locally via Kubernetes port-forwarding:

| Service | Local URL / Port | Credentials / Purpose |
| :--- | :--- | :--- |
| **ArgoCD Web UI** | [http://localhost:8080](http://localhost:8080) | Google OAuth SSO or `admin` |
| **GitLab Web UI** | [http://localhost:8081](http://localhost:8081) | Google OAuth SSO or `root` / `oscar` |
| **GitLab Git SSH** | `localhost:2222` | ED25519 deploy key & user SSH keys |
| **Deployed Workloads** | [http://localhost:8082](http://localhost:8082) | Tenant microservice web pages |

---

## 📋 Manual Script Execution

If you prefer to execute the scripts step-by-step manually without the interactive AI guide, refer to the complete **[Bootstrap & Operations Workflow Guide](docs/bootstrap-workflow.md)** for the 8-phase execution sequence, parameter tables, and visual verification milestones.

---

## 📚 Architectural Documentation & Deep Dives

- **[Bootstrap & Operations Workflow](docs/bootstrap-workflow.md)**: Full step-by-step workflow with visual verification milestones.
- **[ArgoCD Architecture & Design](docs/argocd-design.md)**: Kustomize overlays, App-of-Apps management, and HTTP localhost routing.
- **[GitLab Architecture & Design](docs/gitlab-design.md)**: Omnibus architecture, internal networking, and repository branching model.
- **[User Authentication Architecture](docs/user-authentication.md)**: Google Cloud OAuth 2.0 / OIDC setup for ArgoCD and GitLab.
- **[Service Authentication Architecture](docs/service-authentication.md)**: Deploy keypairs, pattern-based `repo-creds`, and automated `known_hosts` reconciliation.
- **[FAQ & Local SSH Setup](docs/FAQ.md)**: Git SSH port 2222 routing, SSH config aliases, and troubleshooting.
- **[Repository Guidelines](AGENTS.md)**: Architectural rules and idempotency standards.
