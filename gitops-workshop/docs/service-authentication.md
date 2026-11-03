# Service Authentication Architecture (ArgoCD to GitLab)

This document describes how ArgoCD authenticates internally to the self-hosted GitLab repository over SSH to fetch application manifests.

---

## 1. Machine-to-Machine Trust Model

ArgoCD synchronizes manifests from GitLab using internal Kubernetes cluster networking over SSH:
- **Internal Git URL**: `git@gitlab-omnibus.gitlab.svc.cluster.local:gitops-platform/manifests.git`
- **Transport**: SSH over TCP port 22

---

## 2. Authentication Components

### 1. GitLab Service User (`argocd-readonly`)
- Dedicated machine account created automatically by `scripts/bootstrap/gitops/setup_gitlab_auth.py`.
- Granted **Reporter** (20 - Read-Only) membership on the `gitops-platform` group.
- Cannot push code or modify repository settings.

### 2. Runtime ED25519 SSH Keypair
- Generated dynamically in memory during `scripts/bootstrap/gitops/setup_gitlab_auth.py`.
- **Public Key**: Uploaded to GitLab as the public SSH key for user `argocd-readonly`.
- **Private Key**: Injected into Kubernetes Secret `creds-gitlab-ssh` in the `argocd` namespace.

### 3. Pattern-Based Repository Credentials
ArgoCD matches repositories using pattern-based credentials (`type: repo-creds`):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: creds-gitlab-ssh
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
stringData:
  type: git
  url: git@gitlab-omnibus.gitlab.svc.cluster.local
  sshPrivateKey: |
    -----BEGIN OPENSSH PRIVATE KEY-----
    ...
    -----END OPENSSH PRIVATE KEY-----
```
Any ArgoCD application referencing a repository under `git@gitlab-omnibus.gitlab.svc.cluster.local:*` automatically inherits these credentials.

---

## 3. SSH Host Key Verification & Drift Prevention

ArgoCD validates the SSH server host key against the `argocd-ssh-known-hosts-cm` ConfigMap.

- **Host Key Reconciliation**: `scripts/bootstrap/gitops/setup_gitlab_auth.py` reads the active GitLab ED25519 host key directly from `/etc/gitlab/ssh_host_ed25519_key.pub` and updates the ConfigMap.
- **Drift Detection**: If GitLab is reinstalled and generates a new host key, the script detects the mismatch, updates `known_hosts`, restarts `argocd-repo-server`, and verifies connectivity with a live SSH probe (`git ls-remote`).
