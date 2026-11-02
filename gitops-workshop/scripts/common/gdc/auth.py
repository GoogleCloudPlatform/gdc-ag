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

"""Authentication provider for Google Distributed Cloud (GDC) Sandbox."""

import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def ensure_oidc_proxy_tls_secret(dry_run: bool = False) -> None:
    """Ensure TLS certificate secret exists for oidc-token-proxy."""
    secret_name = "oidc-token-proxy-tls"
    code, _, _ = common.run_command(
        ["kubectl", "get", "secret", secret_name, "-n", "argocd"],
        check=False,
        capture_output=True,
    )
    if code == 0:
        common.print_success(f"TLS secret '{secret_name}' already exists in namespace 'argocd'.")
        return

    common.print_info(f"Generating self-signed TLS certificate for '{secret_name}'...")
    if dry_run:
        common.print_info(f"[DRY-RUN] Would generate self-signed cert and create secret '{secret_name}'.")
        return

    host = "fake-oidc-provider.org-1.zone1.google.gdch.test"
    cmd = (
        f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 "
        f"-keyout /tmp/oidc-proxy.key -out /tmp/oidc-proxy.crt "
        f"-subj '/CN={host}' 2>/dev/null && "
        f"kubectl create secret tls {secret_name} -n argocd --cert=/tmp/oidc-proxy.crt --key=/tmp/oidc-proxy.key && "
        f"rm -f /tmp/oidc-proxy.key /tmp/oidc-proxy.crt"
    )
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        common.print_success(f"Created TLS secret '{secret_name}' for host '{host}'.")
    else:
        common.print_warning(f"Could not create TLS secret '{secret_name}': {res.stderr}")


def sync_proxy_ip_manifests(proxy_ip: str, target_dir: Optional[Path] = None):
    """Update declarative manifest patch files in deployed copy with the live oidc-token-proxy ClusterIP."""
    if target_dir is None:
        target_dir = common.get_deployed_manifests_dir()
    upstream_host = "fake-oidc-provider.org-1.zone1.google.gdch.test"

    for rel_path in [
        Path("argocd/overlays/gdc/argocd-dex-server-patch.yaml"),
        Path("gitlab/overlays/gdc/deployment-patch.yaml"),
    ]:
        file_path = target_dir / rel_path
        if file_path.exists():
            try:
                import re
                content = file_path.read_text()
                pattern = r'(- ip:\s*["\']?)(?:[\d\.]+|TEMPLATE_[A-Z0-9_]+|NOT_CONFIGURED_[A-Z0-9_]+|[^"\'\s\n]+)(["\']?\s*\n\s*hostnames:\s*\n\s*-\s*["\']?' + re.escape(upstream_host) + r'["\']?)'
                new_content = re.sub(pattern, r'\g<1>' + proxy_ip + r'\g<2>', content)
                if new_content != content:
                    file_path.write_text(new_content)
                    common.print_info(f"Updated deployed copy {rel_path} with live proxy ClusterIP: {proxy_ip}")
            except Exception as e:
                common.print_warning(f"Could not update {rel_path}: {e}")


def configure_argocd_auth(
    client_id: Optional[str],
    client_secret: Optional[str],
    server_url: str,
    dry_run: bool = False
) -> None:
    """Configure ArgoCD authentication for GDC (OIDC via token proxy or native admin)."""
    auth_mode = os.environ.get("AUTH_MODE", "oidc").lower()
    common.print_info(f"GDC-Sandbox mode: Configuring ArgoCD auth using mode '{auth_mode}'...")

    # 1. Ensure argocd-secret exists and has server.secretkey
    secret_key = secrets.token_urlsafe(32)
    string_data = {
        "server.secretkey": secret_key
    }
    if client_secret:
        string_data["dex.fake-oidc.clientSecret"] = client_secret
        string_data["oidc.fake-oidc.clientSecret"] = client_secret

    if not dry_run:
        subprocess.run(
            ["kubectl", "create", "secret", "generic", "argocd-secret", "-n", "argocd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        patch_json = json.dumps({"stringData": string_data})
        common.run_command(
            ["kubectl", "patch", "secret", "argocd-secret", "-n", "argocd", "--type=merge", "-p", patch_json],
            description="Patching argocd-secret with secretkey and OIDC credentials",
            check=False,
            dry_run=dry_run
        )
    else:
        common.print_info(f"[DRY-RUN] Would patch 'argocd-secret' in 'argocd'.")

    # 2. Configure OIDC Token Proxy if in OIDC mode
    if auth_mode == "oidc":
        ensure_oidc_proxy_tls_secret(dry_run=dry_run)

        # Retrieve ClusterIP of oidc-token-proxy service
        code, out, _ = common.run_command(
            ["kubectl", "get", "svc", "oidc-token-proxy", "-n", "argocd", "-o", "jsonpath={.spec.clusterIP}"],
            check=False,
            capture_output=True,
        )
        if code == 0 and out.strip():
            proxy_ip = out.strip()
            sync_proxy_ip_manifests(proxy_ip)

    common.print_success("ArgoCD authentication configured successfully for GDC.")


def ensure_gitlab_ssh_keys_secret(dry_run: bool = False) -> None:
    """Ensure SSH host keys secret exists in gitlab namespace to bypass FIPS PRNG issue."""
    secret_name = "gitlab-ssh-keys-secret"
    code, _, _ = common.run_command(
        ["kubectl", "get", "secret", secret_name, "-n", "gitlab"],
        check=False,
        capture_output=True,
    )
    if code == 0:
        common.print_success(f"SSH host keys secret '{secret_name}' already exists in namespace 'gitlab'.")
        return

    common.print_info(f"Generating SSH host keys for '{secret_name}' to bypass FIPS PRNG limitation...")
    if dry_run:
        common.print_info(f"[DRY-RUN] Would generate SSH host keys (RSA, ECDSA, ED25519) and create secret '{secret_name}'.")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        key_types = [
            ("rsa", ["-b", "2048"]),
            ("ecdsa", []),
            ("ed25519", []),
        ]
        from_file_args = []
        for ktype, extra_args in key_types:
            key_file = tmp_path / f"ssh_host_{ktype}_key"
            keygen_cmd = ["ssh-keygen", "-q", "-N", "", "-t", ktype] + extra_args + ["-f", str(key_file)]
            res = subprocess.run(keygen_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                common.print_error(f"Failed to generate {ktype} host key: {res.stderr}")
                return
            from_file_args.append(f"--from-file=ssh_host_{ktype}_key={key_file}")
            from_file_args.append(f"--from-file=ssh_host_{ktype}_key.pub={key_file}.pub")

        create_cmd = [
            "kubectl", "create", "secret", "generic", secret_name,
            "-n", "gitlab",
            *from_file_args,
            "--dry-run=client", "-o", "yaml"
        ]
        code, out, err = common.run_command(create_cmd, check=False, capture_output=True)
        if code == 0 and out:
            res = subprocess.run(["kubectl", "apply", "-n", "gitlab", "-f", "-"], input=out, text=True, capture_output=True)
            if res.returncode == 0:
                common.print_success(f"Created SSH host keys secret '{secret_name}' in namespace 'gitlab'.")
            else:
                common.print_error(f"Failed to apply secret '{secret_name}': {res.stderr}")
        else:
            common.print_error(f"Failed to generate secret manifest for '{secret_name}': {err}")


def ensure_gitlab_oidc_proxy_cert(dry_run: bool = False) -> None:
    """Sync OIDC proxy TLS certificate to gitlab namespace for trusted-certs mount."""
    secret_name = "oidc-proxy-tls-cert"
    code, _, _ = common.run_command(
        ["kubectl", "get", "secret", secret_name, "-n", "gitlab"],
        check=False,
        capture_output=True,
    )
    if code == 0:
        common.print_success(f"TLS secret '{secret_name}' already exists in namespace 'gitlab'.")
        return

    code, out, _ = common.run_command(
        ["kubectl", "get", "secret", "oidc-token-proxy-tls", "-n", "argocd", "-o", "jsonpath={.data.tls\\.crt}"],
        check=False,
        capture_output=True,
    )
    if code != 0 or not out.strip():
        common.print_warning("Could not retrieve oidc-token-proxy-tls cert from argocd namespace.")
        return

    cert_b64 = out.strip()
    secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: gitlab
data:
  oidc-proxy.crt: {cert_b64}
"""
    if dry_run:
        common.print_info(f"[DRY-RUN] Would create secret '{secret_name}' in namespace 'gitlab'.")
        return

    res = subprocess.run(["kubectl", "apply", "-n", "gitlab", "-f", "-"], input=secret_yaml, text=True, capture_output=True)
    if res.returncode == 0:
        common.print_success(f"Synced '{secret_name}' into namespace 'gitlab'.")
    else:
        common.print_warning(f"Could not apply secret '{secret_name}': {res.stderr}")


def configure_gitlab_auth(
    root_pass: str,
    root_token: str,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    dry_run: bool = False
) -> None:
    """Configure GitLab authentication for GDC (native root credentials, FIPS host keys, and OIDC)."""
    ensure_gitlab_ssh_keys_secret(dry_run=dry_run)
    ensure_gitlab_oidc_proxy_cert(dry_run=dry_run)

    auth_mode = os.environ.get("AUTH_MODE", "oidc").lower()
    oidc_client_id = client_id or os.environ.get("GDC_OIDC_CLIENT_ID", "gpc")
    oidc_client_secret = client_secret or os.environ.get("GDC_OIDC_CLIENT_SECRET", "very-private-oidc-client-secret")
    oidc_issuer = os.environ.get("GDC_OIDC_ISSUER", "https://fake-oidc-provider.org-1.zone1.google.gdch.test")
    gitlab_http_url = os.environ.get("GITLAB_HTTP_URL", "http://localhost:8081")

    secret_cmd = [
        "kubectl", "create", "secret", "generic", "gitlab-oauth-secret",
        "-n", "gitlab",
        f"--from-literal=root_password={root_pass}",
        f"--from-literal=root_token={root_token}",
        f"--from-literal=auth_mode={auth_mode}",
        f"--from-literal=gdc_client_id={oidc_client_id}",
        f"--from-literal=gdc_client_secret={oidc_client_secret}",
        f"--from-literal=gdc_issuer={oidc_issuer}",
        f"--from-literal=gitlab_http_url={gitlab_http_url}",
        "--dry-run=client", "-o", "yaml"
    ]
    common.print_info("GDC-Sandbox mode: Injecting credentials and OIDC configuration into gitlab-oauth-secret...")
    code, out, _ = common.run_command(secret_cmd, check=False, capture_output=True)
    if code == 0 and out and not dry_run:
        subprocess.run(["kubectl", "apply", "-n", "gitlab", "-f", "-"], input=out, text=True, capture_output=True)

    # Sync proxy IP into deployed manifest if in OIDC mode
    if auth_mode == "oidc":
        code, out, _ = common.run_command(
            ["kubectl", "get", "svc", "oidc-token-proxy", "-n", "argocd", "-o", "jsonpath={.spec.clusterIP}"],
            check=False,
            capture_output=True,
        )
        if code == 0 and out.strip():
            proxy_ip = out.strip()
            sync_proxy_ip_manifests(proxy_ip)

