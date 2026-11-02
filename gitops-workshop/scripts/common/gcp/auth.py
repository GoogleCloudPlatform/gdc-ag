#!/usr/bin/env python3

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Authentication provider for Google Cloud Platform (Google Cloud OAuth 2.0 / Dex / OmniAuth)."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def configure_argocd_auth(
    client_id: Optional[str],
    client_secret: Optional[str],
    server_url: str,
    dry_run: bool = False
) -> None:
    """Configure ArgoCD secret with Google OAuth 2.0 Dex connector credentials."""
    secret_key = secrets.token_urlsafe(32)
    secret_patch = {
        "stringData": {
            "server.secretkey": secret_key
        }
    }
    if client_id and client_secret:
        common.print_info("Injecting GCP OIDC Client ID & Secret into argocd-secret...")
        secret_patch["stringData"]["oidc.google.clientID"] = client_id
        secret_patch["stringData"]["oidc.google.clientSecret"] = client_secret
    else:
        common.print_info("Injecting Dex server.secretkey into argocd-secret (native admin auth mode)...")
        common.print_info("To enable Google OAuth SSO later, configure GCP_OIDC_CLIENT_ID and GCP_OIDC_CLIENT_SECRET in .env.")
        common.print_info("  - Refer to docs/user-authentication.md for instructions and redirect URIs.")

    if not dry_run:
        subprocess.run(
            ["kubectl", "create", "secret", "generic", "argocd-secret", "-n", "argocd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        patch_json = json.dumps(secret_patch)
        res = subprocess.run(
            ["kubectl", "patch", "secret", "argocd-secret", "-n", "argocd", "--type=merge", "-p", patch_json],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            common.print_success("argocd-secret configured successfully.")
        else:
            common.print_error(f"Failed to patch argocd-secret. Details:\n{res.stderr}")


def configure_gitlab_auth(
    root_pass: str,
    root_token: str,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    dry_run: bool = False
) -> None:
    """Configure GitLab secret with root credentials and optional Google OAuth 2.0 OmniAuth credentials."""
    secret_cmd = [
        "kubectl", "create", "secret", "generic", "gitlab-oauth-secret",
        "-n", "gitlab",
        f"--from-literal=root_password={root_pass}",
        f"--from-literal=root_token={root_token}",
    ]
    if client_id and client_secret:
        secret_cmd.extend([
            f"--from-literal=client_id={client_id}",
            f"--from-literal=client_secret={client_secret}",
        ])
    secret_cmd.extend(["--dry-run=client", "-o", "yaml"])

    common.print_info("Injecting root credentials into gitlab-oauth-secret...")
    code, out, _ = common.run_command(secret_cmd, check=False, capture_output=True)
    if code == 0 and out:
        if dry_run:
            common.print_info("[DRY-RUN] Would apply gitlab-oauth-secret.")
        else:
            res = subprocess.run(["kubectl", "apply", "-n", "gitlab", "-f", "-"], input=out, text=True, capture_output=True)
            if res.returncode == 0:
                common.print_success("gitlab-oauth-secret configured successfully.")
            else:
                common.print_error(f"Failed to apply gitlab-oauth-secret. Details:\n{res.stderr}")
    if not (client_id and client_secret):
        common.print_warning("GCP_OIDC_CLIENT_ID / GCP_OIDC_CLIENT_SECRET not set in .env. Using native root admin auth.")
        common.print_info("To enable Google OAuth SSO later, refer to docs/user-authentication.md:")
        common.print_info("  - GitLab Redirect URI: http://localhost:8081/users/auth/google_oauth2/callback")
