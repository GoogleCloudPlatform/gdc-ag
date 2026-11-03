# Repository Guidelines for AI Agents & Developers

This document defines the architectural standards, operational rules, and design documentation structure for `gitops-workshop`.

## Core Architectural Principles

1. **Idempotency Mandatory**:
   - All Python automation scripts (`scripts/bootstrap/bootstrap.py`, `scripts/bootstrap/provision_cluster.py`, `scripts/bootstrap/argocd/install_argocd.py`, `scripts/project_provision/provision_project.py`, etc.) **must be strictly idempotent**.
   - Scripts must check for resource existence first, report current state in parameter tables, and proceed without errors when re-run against active environments.
   - Deletion scripts (`scripts/bootstrap/cleanup.py`) must handle missing resources as warnings and exit with code 0.

2. **GCP Project Auto-Creation, Billing Account & Read-Only `.env` Sourcing**:
   - GCP Project ID can be provided via `--project`, environment variable `GCP_PROJECT`, or sourced from `.env` via `-e` / `--env-file`.
   - `.env` files are **strictly read-only**: Python scripts MUST NEVER modify, overwrite, or mutate `.env` files.
   - `.env` path defaults to `.env` in the current working execution directory (`Path.cwd() / ".env"`).
   - If specified GCP project does not exist, `scripts/bootstrap/bootstrap.py` creates it and links the selected open billing account.
   - Project Owner IAM binding (`roles/owner`) is seeded from `GCP_PROJECT_OWNER` in `.env` or `--project-owner`.

3. **Python + Rich CLI UX Standard**:
   - All automation MUST be written in Python 3 using the `rich` library for formatted panels, status badges (`[SUCCESS]`, `[EXISTS/SKIP]`, `[ERROR]`), and progress spinners.
   - All scripts must display a parameter summary table (`print_parameter_summary()`) and prompt for confirmation (`confirm_action()`) before execution, supporting `-y` / `--auto-approve`.
   - Detailed UX guidelines are maintained in `docs/cli-ux-guidelines.md`.

4. **Manual Sync Principle**:
   - All ArgoCD applications (`root-app`, `argocd`, `gitlab`) must use **manual sync** (no `syncPolicy.automated`). This ensures workshop participants actively review diffs and execute sync operations.

5. **Security & Secrets**:
   - Never commit GCP service account keys, client secrets, or OAuth secrets to Git.
   - Generate runtime secrets dynamically in Python and inject them directly as Kubernetes secrets (`kubectl patch secret ...` or `kubectl create secret ...`).

6. **Transparent Agent Narration ("Explain First, Execute Second")**:
   - Whenever an AI agent begins an interactive skill (`/gitops-workshop-guide`, `/gitops-provision-project`), the agent **MUST ALWAYS output a visible markdown greeting and educational overview explaining what it is doing BEFORE calling any execution tools**.
   - Never execute background commands (such as checking tmux, port-forwards, or cluster resources) silently without prior explanation to the user.

---

## Architectural & Design Documentation

Detailed component and workflow designs are maintained in the [`docs/`](docs/) directory:

- **[Bootstrap & Operations Workflow](docs/bootstrap-workflow.md)**: End-to-end execution sequence, script responsibilities, parameter tables, and visual verification milestones.
- **[ArgoCD Architecture & Design](docs/argocd-design.md)**: Kustomize overlay structure, HTTP mode on localhost, App-of-Apps management, diff ignoring, and orphan reset flow.
- **[GitLab Architecture & Design](docs/gitlab-design.md)**: Single-pod Omnibus deployment, 30Gi PVC persistent storage (`standard-rwo`), internal `ClusterIP` networking, and repository branching model.
- **[User Authentication Architecture](docs/user-authentication.md)**: Google Cloud OAuth 2.0 / OIDC setup, consent screen, redirect URI callbacks, ArgoCD Dex connector, and GitLab OmniAuth auto-linking.
- **[Service Authentication Architecture](docs/service-authentication.md)**: Machine-to-machine trust between ArgoCD and GitLab, `argocd-readonly` service user, ED25519 deploy keypair, pattern-based `repo-creds`, and automated `known_hosts` reconciliation.
- **[CLI UX & Formatting Guidelines](docs/cli-ux-guidelines.md)**: Output styling, color palette, badges, parameter tables, and confirmation prompt standards.
- **[FAQ & Local Setup / Troubleshooting](docs/FAQ.md)**: Local Git SSH port 2222 routing, SSH config alias, branch protection, and common participant questions.
