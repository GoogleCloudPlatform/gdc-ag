# Application Workshop: Frequently Asked Questions & Troubleshooting

This guide answers common questions about building, pushing, and deploying multiple applications with `application-workshop`.

---

## 1. Why Does `push_manifests.py` Require an Existing GitLab Repository?

By design, **`gitops-workshop` owns platform and project onboarding**, while **`application-workshop` owns application delivery**:
- In `gitops-workshop`, running `provision_project.py -g <group> -p <project> -a <app-name>` creates a dedicated GitLab repository (`<group>/<project>.git`), configures SSH access for ArgoCD, and registers `<project>-apps` in `gitops-platform/manifests`.
- In `application-workshop`, you point `push_manifests.py` at that repository (`-r <group>/<project> -a <app-name>`). It clones the repository into a temporary directory, preserves `manifests/project.yaml`, overwrites `manifests/` with `<app-name>`'s declarative Kustomize overlays, and pushes a Merge Request without touching platform-level repositories.

---

## 2. What Happens If I Run `push_manifests.py` Again Without Changing Any Manifests?

`push_manifests.py` is strictly idempotent:
1. It clones `<group>/<project>.git` into a temporary directory and renders `manifests/<app-name>/`, `manifests/<app-name>-app.yaml`, and `manifests/kustomization.yaml`.
2. It runs `git status --porcelain` against the `main` branch.
3. If no files in `manifests/` have changed, it logs `[EXISTS/SKIP] Manifests in '<group>/<project>' are already up to date on 'main'` and exits immediately without creating a branch or Merge Request.

---

## 3. How Do I Push Directly to GitLab Using a Git Remote?

Run `push_manifests.py` with `--configure-remote`:
```bash
python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api --configure-remote
```
This configures the `gitlab` remote (`http://localhost:8081/workloads/translate-project.git`) so you can also inspect or push branches directly with `git`.

---

## 4. Required Port Forwards

| Service | Local Port | Target Service & Port | Command |
| :--- | :--- | :--- | :--- |
| **ArgoCD Web & API** | `8080` / `8088` | `argocd/argocd-server:80` | `kubectl port-forward -n argocd svc/argocd-server 8088:80` |
| **GitLab Web & HTTP Git** | `8081` | `gitlab/gitlab-omnibus:80` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80` |
| **App 1 (`translate-api`)** | `8082` | `translate-api/translate-api:80` | `kubectl port-forward -n translate-api svc/translate-api 8082:80` |
| **App 2 (`upload-api`)** | `8083` | `upload-api/upload-api:80` | `kubectl port-forward -n upload-api svc/upload-api 8083:80` |

---

## 5. Common Errors & Troubleshooting

### Q: `GitLab repository '<group>/<project>' was not found`
- **Cause**: The project repository has not been provisioned in `gitops-workshop` yet.
- **Fix**: Run `provision_project.py` in `gitops-workshop` first:
  ```bash
  cd ../gitops-workshop
  python3 scripts/project_provision/provision_project.py -g workloads -p translate-project -a starter-app
  ```

### Q: `upload-api-0` pod stays in `Pending` state
- **Cause**: `upload-api` is a `StatefulSet` that requests a `10Gi` `PersistentVolumeClaim` (`data-upload-api-0`) using `storageClassName: standard-rwo`.
- **Fix**: Verify `kubectl get pvc -n upload-api` and `kubectl get storageclass` to ensure `standard-rwo` is present on the cluster.
