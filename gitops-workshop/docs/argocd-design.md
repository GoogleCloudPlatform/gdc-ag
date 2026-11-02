# ArgoCD Architecture & Design

This document details the ArgoCD deployment model, Kustomize overlay structure, network access settings, and App-of-Apps GitOps management in `gitops-workshop`.

---

## 1. Deployment & Kustomize Overlay

ArgoCD is deployed to the `argocd` namespace using Kustomize (`manifests/argocd/kustomization.yaml`).

### Base Resources & Patches
- **Base Upstream**: `crds.yaml` and `install.yaml` provide the standard ArgoCD core controllers and services.
- **ConfigMaps**:
  - `argocd-cm.yaml`: Declares the base server URL (`http://localhost:8080`) and Google OIDC Dex connector configuration.
  - `policy.csv.example`: Template for RBAC policies (`manifests/argocd/base/policy.csv`), loaded into `argocd-rbac-cm` via Kustomize `configMapGenerator`.
- **Strategic Merge Patch**:
  - `argocd-cmd-params-cm.yaml`: Patches `server.insecure: "true"`, allowing `argocd-server` to serve plain HTTP to port-forwarded localhost connections without TLS redirect loops.
- **Runtime Secret Injection**:
  - OAuth client credentials and Dex secret keys are injected dynamically at runtime via `kubectl patch secret argocd-secret` by `scripts/bootstrap/argocd/install_argocd.py`.

---

## 2. App-of-Apps Pattern & Manifest Organization

ArgoCD manages cluster workloads using the declarative **App-of-Apps** pattern:

```
manifests/
├── root-app.yaml               # Root Application tracking manifests/apps in GitLab
├── project.yaml                # AppProject 'gitops-platform' defining allowed sources/destinations
├── apps/                       # Child Application manifests
│   ├── argocd.yaml             # Manages ArgoCD manifests (manifests/argocd)
│   └── gitlab.yaml             # Manages GitLab manifests (manifests/gitlab)
└── argocd/                     # ArgoCD Kustomize overlay
```

### Flow:
1. `manifests/root-app.yaml` is applied to ArgoCD during Phase 6 (`scripts/bootstrap/gitops/enable_gitops.py`).
2. `root-app` monitors the `manifests/apps` directory in the internal GitLab repository.
3. As child Application custom resources (`argocd.yaml`, `gitlab.yaml`) are discovered in `manifests/apps`, ArgoCD creates corresponding applications to manage the respective components.

---

## 3. Manual Sync Principle

All Application manifests in this workshop omit `syncPolicy.automated` (`prune: true`, `selfHeal: true`).

- **Participant-Driven Operations**: Workshop attendees explicitly review out-of-sync diffs in the ArgoCD UI and trigger manual syncs.
- **Diff Respect**: `argocd.yaml` includes `RespectIgnoreDifferences=true` and ignores live changes to `argocd-secret`, `argocd-cm`, and `argocd-rbac-cm` so Git sync does not overwrite runtime-injected credentials.

---

## 4. Reset & History Management

When GitLab is re-initialized or host keys drift, live `Application` custom resources can retain references to old commit SHAs in `.status.history`. 

`scripts/bootstrap/gitops/enable_gitops.py` includes a pre-check detection and `--recreate-apps` option:
```bash
# Deletes Application CRs without terminating underlying pods
kubectl delete applications -n argocd --all --cascade=orphan
```
Re-applying `root-app.yaml` initializes fresh tracking against the active repository HEAD.

---

## 5. Application Labeling & Metadata Taxonomy

All ArgoCD `Application` custom resources adhere to standard Kubernetes and GitOps domain metadata labels for UI filtering, group isolation, and tier hierarchy:

```
[root-app]                     ──► tier: root (Global Entrypoint)
    │                               group: gitops-platform, project: manifests
    │
    ├──► [argocd, gitlab]      ──► tier: platform (Core Infrastructure)
    │                               group: gitops-platform, project: manifests
    │
    └──► [<project>-apps]      ──► tier: tenant-root (Tenant App-of-Apps Entrypoint)
            │                       group: <group>, project: <project>
            │
            └──► [<app-name>]  ──► tier: workload (Developer Microservice Workload)
                                    group: <group>, project: <project>
```

### Standard Labels Applied:

| Label Key | Purpose & Scope | Example Values |
| :--- | :--- | :--- |
| **`app.kubernetes.io/part-of`** | Top-level organization / group identity | `gitops-platform`, `drdc` |
| **`gitops.platform/group`** | GitLab Group / Organization name | `gitops-platform`, `drdc` |
| **`gitops.platform/project`** | GitLab Project / Repository name | `manifests`, `team-a` |
| **`gitops.platform/tier`** | 4-Tier Architectural Level | `root`, `platform`, `tenant-root`, `workload` |
