# Multi-Workshop Repository Guidelines for AI Agents & Contributors

This repository (`gdc-ag`) hosts **independent, parallel hands-on workshops**, reference automation, and sample workloads for **Google Distributed Cloud - Air Gapped (GDC-AG)** and related Kubernetes platform patterns.

---

## 1. Workshop Isolation Principle

- Each workshop lives in its own **self-contained top-level directory** at the repository root (e.g., `gdc-sandbox-workshop/`, `gitops-workshop/`, future `<name>-workshop/`).
- Workshops do **not** depend on or share runtime state with one another. Each workshop maintains its own:
  - `README.md` and `docs/`
  - `.env` configuration and example templates (`.env_sample`, `.env.*.example`)
  - Automation scripts and dependencies (`requirements.txt`, shell/Python tooling)
  - Optional workshop-scoped `AGENTS.md` and `.agents/skills/`
- When working on or executing a workshop, **always scope `.env` files, script invocations, and terminal working directories to that specific workshop's directory**—never place workshop `.env` files at the repository root.

---

## 2. Available Workshops & Agent Routing

| Workshop Directory | Focus | Target Environment | Interactive Agent Skills |
| :--- | :--- | :--- | :--- |
| **[`gdc-sandbox-workshop/`](gdc-sandbox-workshop/README.md)** | Landing zone setup, IAM role bindings, Harbor registry, and sample workloads (Web Server, Translation API, Elasticsearch) | GDC Sandbox | Guided via [`README.md`](gdc-sandbox-workshop/README.md) & `LAB-1..3.md` |
| **[`gitops-workshop/`](gitops-workshop/README.md)** | Enterprise declarative GitOps platform with ArgoCD (App-of-Apps), self-hosted GitLab Omnibus, OIDC/SSH auth, and multi-tenant self-service onboarding | GDC Sandbox & GCP (GKE Autopilot) | `/gitops-workshop-guide`, `/gitops-provision-project` (shared UX in `gitops-interaction-guide`) |

### Routing Notes for AI Agents Started at Repo Root
- If a user asks about available workshops from the repository root, summarize the catalog above and help them pick the right track.
- If a user triggers `/gitops-workshop-guide` or `/gitops-provision-project` from the repository root (`gdc-ag/`), ensure all script executions, tmux panes, and `.env` operations run inside `gitops-workshop/` (see [`gitops-workshop/AGENTS.md`](gitops-workshop/AGENTS.md)).

---

## 3. Conventions for Adding Future Workshops

When incorporating a new parallel workshop into this repository:

1. **Top-Level Directory**: Place all workshop files under `<workshop-name>/` at the repository root.
2. **Self-Contained Documentation & Rules**: Include `<workshop-name>/README.md`, `<workshop-name>/.gitignore` (if workshop-specific), and optionally `<workshop-name>/AGENTS.md` for rules that apply only within that workshop.
3. **Namespaced Agent Skills**:
   - Store workshop skills in `<workshop-name>/.agents/skills/<prefix>-<skill-name>/SKILL.md` using a workshop-specific prefix to avoid collisions across workshops.
   - Register `<workshop-name>/.agents/skills` as an entry in the root [`.agents/skills.json`](.agents/skills.json) so skills work whether `agy` is started at the repo root or inside `<workshop-name>/`.
   - Ensure skills resolve their working directory to `<workshop-name>/` when invoked from the repository root.
4. **Open-Source Hygiene (`GoogleCloudPlatform`)**:
   - Include standard `Copyright <YEAR> Google LLC` Apache 2.0 license headers in source scripts (`.py`, `.sh`, etc.).
   - Sanitize all `.env` templates (`.env_sample`, `.env.*.example`) with placeholders—never commit real tokens, robot passwords, OAuth secrets, or service account keys.
5. **Catalog Registration**: Add the new workshop to both the root [`README.md`](README.md) catalog and the table in Section 2 above.
