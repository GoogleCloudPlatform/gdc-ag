# GitOps Workshop: Frequently Asked Questions & Local Setup

This guide answers common questions and provides step-by-step instructions for interacting with the GitOps workshop environment locally (GitLab, ArgoCD, and Git CLI).

---

## Table of Contents

1. [How to Clone and Push to GitLab Locally as a User](#1-how-to-clone-and-push-to-gitlab-locally-as-a-user)
2. [Why Does `git clone git@localhost:...` Connect to the Wrong Port / Fail?](#2-why-does-git-clone-gitlocalhost-connect-to-the-wrong-port--fail)
3. [Local SSH Config Setup (Recommended)](#3-local-ssh-config-setup-recommended)
4. [One-Shot Clone Alternative (`GIT_SSH_COMMAND`)](#4-one-shot-clone-alternative-git_ssh_command)
5. [Required Port Forwards](#5-required-port-forwards)
6. [Branch Protection & Merge Request Workflow](#6-branch-protection--merge-request-workflow)
7. [Common Errors & Troubleshooting](#7-common-errors--troubleshooting)

---

## 1. How to Clone and Push to GitLab Locally as a User

When developing microservices or updating workloads in GitLab as a workshop participant (e.g. user `oscar`), follow these steps:

### Step 1: Generate an SSH Keypair (if not already created)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/oscar-id_ed25519 -C "oscar@example.com" -N ""
```

### Step 2: Add Public Key to GitLab
1. Open GitLab in your browser: [http://localhost:8081](http://localhost:8081)
2. Log in with Google Cloud OAuth / OIDC or your assigned credentials.
3. Navigate to **User Settings** → **SSH Keys** ([http://localhost:8081/-/user_settings/ssh_keys](http://localhost:8081/-/user_settings/ssh_keys)).
4. Paste the contents of `~/.ssh/oscar-id_ed25519.pub` and click **Add key**.

### Step 3: Configure `~/.ssh/config` (see Section 3)
Add the `gitlab-local` host block to route to port `2222`.

### Step 4: Clone the Project Repository
```bash
git clone gitlab-local:<group-name>/<project-name>.git

# Example:
git clone gitlab-local:drdc/research-a.git
```

### Step 5: Configure Local Git Author Details
Inside the cloned repository:
```bash
cd research-a
git config user.name "Oscar"
git config user.email "oscar@example.com"
```

---

## 2. Why Does `git clone git@localhost:...` Connect to the Wrong Port / Fail?

### The Problem:
Running `git clone git@localhost:<group>/<project>.git` defaults to standard SSH port **22**. On local workstations, port 22 connects to the host system's SSH daemon rather than the container's forwarded port, triggering an authentication failure:

```text
git@localhost: Permission denied (publickey).
```

### The Solution:
GitLab Omnibus SSH is forwarded to local port **`2222`**. You must either:
- Use the `gitlab-local` host alias in `~/.ssh/config` (Port 2222), or
- Use the full URL format: `ssh://git@localhost:2222/<group>/<project>.git`

---

## 3. Local SSH Config Setup (Recommended)

Add this entry to `~/.ssh/config` on your local machine:

```ssh-config
Host gitlab-local
    HostName localhost
    Port 2222
    User git
    IdentityFile ~/.ssh/oscar-id_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

### Explanation of Directives:
- **`Host gitlab-local`**: Creates a convenient shorthand alias.
- **`HostName localhost`**: Connects to the local workstation loopback.
- **`Port 2222`**: Targets GitLab's forwarded SSH port (avoiding port 22 host SSH).
- **`IdentityFile ~/.ssh/oscar-id_ed25519`**: Explicitly selects the user's SSH private key.
- **`IdentitiesOnly yes`**: Prevents SSH agent from offering other workstation keys first.
- **`UserKnownHostsFile /dev/null`**: Prevents host identification collision with port 22 entries.

### Verify Connection:
```bash
ssh -T gitlab-local
```
**Expected output**:
```text
Welcome to GitLab, @oscar!
```

---

## 4. One-Shot Clone Alternative (`GIT_SSH_COMMAND`)

If you prefer not to modify `~/.ssh/config`, use `GIT_SSH_COMMAND`:

```bash
GIT_SSH_COMMAND="ssh -p 2222 -i ~/.ssh/oscar-id_ed25519 -o StrictHostKeyChecking=accept-new"   git clone ssh://git@localhost:2222/drdc/research-a.git
```

To configure that repository to always use this SSH key for subsequent `git pull` and `git push`:
```bash
cd research-a
git config core.sshCommand "ssh -p 2222 -i ~/.ssh/oscar-id_ed25519 -o StrictHostKeyChecking=accept-new"
```

---

## 5. Required Port Forwards

The workshop environment requires three active port-forwards to access web interfaces and SSH locally:

| Service | Local Port | Target Service & Port | Command |
| :--- | :--- | :--- | :--- |
| **GitLab Web & HTTP Git** | `8081` | `gitlab/gitlab-omnibus:80` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80` |
| **GitLab SSH Git** | `2222` | `gitlab/gitlab-omnibus:22` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22` |
| **ArgoCD Web & API** | `8080` | `argocd/argocd-server:80` | `kubectl port-forward -n argocd svc/argocd-server 8080:80` |

---

## 6. Branch Protection & Merge Request Workflow

By default, GitLab protects the `main` branch against direct pushes:

```text
remote: GitLab: You are not allowed to push code to protected branches on this project.
```

### Standard Workflow:
1. **Branch**: Create a new feature branch from `main`:
   ```bash
   git checkout -b feature/update-nginx-config
   ```
2. **Commit & Push**:
   ```bash
   git commit -am "feat: update nginx deployment replicas"
   git push -u origin feature/update-nginx-config
   ```
3. **Merge Request**: GitLab will print the MR creation URL in the terminal, or navigate to [http://localhost:8081](http://localhost:8081) to open and merge the MR.
4. **ArgoCD Sync**: Once merged to `main`, ArgoCD will detect the changes on the next refresh cycle (or click **Sync** in the ArgoCD UI).

---

## 7. Common Errors & Troubleshooting

### Q: `git@localhost: Permission denied (publickey)`
- **Cause**: Connecting to port 22 instead of port 2222.
- **Fix**: Use `git clone gitlab-local:<group>/<project>.git` or `ssh://git@localhost:2222/...`.

### Q: `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!`
- **Cause**: The host key for `localhost:2222` differs from the existing `localhost:22` entry in `~/.ssh/known_hosts`.
- **Fix**: Add `UserKnownHostsFile /dev/null` and `StrictHostKeyChecking no` to your `gitlab-local` block in `~/.ssh/config`.

### Q: `ssh: connect to host localhost port 2222: Connection refused`
- **Cause**: The GitLab SSH port-forward process is not running.
- **Fix**: Start the port forward in a terminal:
  ```bash
  kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22
  ```

### Q: `ArgoCD shows ComparisonError: repository not found`
- **Cause**: ArgoCD repo-server cached a previous SSH key or host key.
- **Fix**: Run `scripts/bootstrap/gitops/setup_gitlab_auth.py --overwrite -y` to re-sync deploy keys and restart the repo-server pod.
