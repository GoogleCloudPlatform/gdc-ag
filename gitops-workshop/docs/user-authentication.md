# User Authentication Architecture (Google OAuth / OIDC)

This document describes how human users authenticate to both ArgoCD and GitLab using Google Cloud OAuth 2.0 / OpenID Connect (OIDC).

---

## 1. GCP OAuth Setup

Both ArgoCD and GitLab share a single Google Cloud OAuth 2.0 Web Application client.

### Step 1: OAuth Consent Screen
1. Open the [GCP OAuth Consent Screen Console](https://console.cloud.google.com/apis/credentials/consent).
2. Set User Type to **Internal** (or External for personal accounts).
3. Specify application name (e.g. `GitOps Workshop`) and contact email addresses.

### Step 2: Data Access (Scopes)
1. On the **Data Access** / **Scopes** page, click **Add or Remove Scopes**.
2. Select the standard non-sensitive scopes:
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
   - `openid`
3. Save and continue.

### Step 3: OAuth 2.0 Web Application Client
1. Open the [GCP Credentials Console](https://console.cloud.google.com/apis/credentials).
2. Create credentials $\rightarrow$ **OAuth Client ID** $\rightarrow$ **Web application**.
3. Add Authorized Redirect URIs:
   - `http://localhost:8080/api/dex/callback` (ArgoCD UI Dex callback)
   - `http://localhost:8081/users/auth/google_oauth2/callback` (GitLab Omnibus UI callback)
4. Record the **Client ID** and **Client Secret** in `.env`:
   ```ini
   GCP_OIDC_CLIENT_ID=123456789012-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com
   GCP_OIDC_CLIENT_SECRET=GOCSPX-your_client_secret_here
   ```

---

## 2. ArgoCD User Authentication Flow

```
[User Browser] (http://localhost:8080)
       │
       ▼ (1. Click 'Log in via Google')
[ArgoCD Server]
       │
       ▼ (2. Redirect to Dex)
[ArgoCD Dex]
       │
       ▼ (3. Redirect to Google OAuth)
[Google Accounts] (User authenticates)
       │
       ▼ (4. Return ID Token & Scopes)
[ArgoCD Dex]
       │
       ▼ (5. Issue ArgoCD JWT Session)
[ArgoCD Server] ───► RBAC Match in argocd-rbac-cm (role:admin)
```

- **RBAC Mapping**: `manifests/argocd/policy.csv` (templated from `policy.csv.example`) assigns administrative privileges (`role:admin`) to the configured project owner via Kustomize `configMapGenerator`.

---

## 3. GitLab User Authentication Flow

- **OmniAuth Integration**: Configured in `gitlab.rb` within `manifests/gitlab/gitlab-omnibus.yaml`.
- **Auto-Linking (`omniauth_auto_link_user`)**: Enabled for `google_oauth2` so logging in with a Google account automatically links to the existing user profile.
- **Root Credentials Backup**: The local admin user `root` is available with credentials dynamically generated during bootstrap (or overridden via `GITLAB_ROOT_PASSWORD_OVERRIDE` in `.env`).
