# GitLab Omnibus Architecture & Design

This document details the single-pod GitLab Omnibus deployment in GKE, persistent storage architecture, and project repository layout for `gitops-workshop`.

---

## 1. Deployment Model & Networking

GitLab Omnibus CE is deployed as a single-pod workload in the `gitlab` namespace (`manifests/gitlab/gitlab-omnibus.yaml`).

- **Image**: `gitlab/gitlab-ce:16.8.0-ce.0`
- **Internal Cluster Service**: `ClusterIP` (`gitlab-omnibus.gitlab.svc.cluster.local`)
  - Port 80 (HTTP / UI / API)
  - Port 22 (SSH Git transport)
- **Zero Public Exposure**: No external LoadBalancers or public IP addresses are provisioned.
- **Local Access**: Local developer and workshop attendee traffic is forwarded through `kubectl port-forward`:
  - UI / HTTP API: `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80`
  - Git SSH: `kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22`

---

## 2. Persistent Storage Architecture

GitLab Omnibus requires persistent storage for configuration files, PostgreSQL database files, and Git repositories.

- **PersistentVolumeClaim**: `gitlab-pvc` (30Gi, `ReadWriteOnce`) using GKE's default `standard-rwo` storage class.
- **Volume Mounts**:
  - `config`: Subpath `config` mounted to `/etc/gitlab`
  - `data`: Subpath `data` mounted to `/var/opt/gitlab`
  - `logs`: Subpath `logs` mounted to `/var/log/gitlab`

This ensures that user accounts, SSH keys, repository commits, and OAuth settings persist across pod restarts, node drains, and cluster upgrades.

---

## 3. Group & Repository Layout

The GitOps repository structure is created by automation scripts:

- **Group**: `gitops-platform`
- **Project**: `manifests` (`gitops-platform/manifests.git`)
- **Default Branch**: `main` (Protected)
- **Feature Branching**:
  - `scripts/bootstrap/gitlab/create_manifest_mr.py` pushes local manifests to `feature/initial-manifests` and opens Merge Request #1 targeting `main`.
  - Subsequent manifest updates use dynamic feature branches (`feature/update-manifests`) to maintain branch protection standards.
