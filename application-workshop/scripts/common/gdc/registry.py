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

"""Container registry & CDS image push provider for Google Distributed Cloud (GDC)."""

import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from typing import Optional, Tuple
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_harbor_config(env_path: Optional[Path] = None) -> Tuple[str, str, str, str]:
    """Retrieve Harbor registry endpoint, project, username, and password from .env or gdcloud."""
    env = common.load_dotenv(env_path)
    harbor_url = (
        env.get("HARBOR_URL")
        or os.environ.get("HARBOR_URL")
        or ""
    ).strip().rstrip("/")
    if harbor_url.startswith("https://"):
        harbor_url = harbor_url[len("https://"):]
    elif harbor_url.startswith("http://"):
        harbor_url = harbor_url[len("http://"):]

    harbor_project = (
        env.get("HARBOR_PROJECT")
        or os.environ.get("HARBOR_PROJECT")
        or "gitops-platform"
    ).strip()

    harbor_user = (
        env.get("HARBOR_USERNAME")
        or os.environ.get("HARBOR_USERNAME")
        or "admin"
    ).strip()

    harbor_pass = (
        env.get("HARBOR_PASSWORD")
        or os.environ.get("HARBOR_PASSWORD")
        or "admin"
    ).strip()

    if not harbor_url and common.check_tool_installed("gdcloud"):
        instance_name = (
            env.get("HARBOR_INSTANCE_NAME")
            or os.environ.get("HARBOR_INSTANCE_NAME")
            or "gitops-registry"
        ).strip()
        code, out, _ = common.run_command(
            ["gdcloud", "harbor", "harbor-instances", "list", f"--project={harbor_project}", "--format=json"],
            check=False,
            capture_output=True,
        )
        if code == 0 and out.strip():
            try:
                items = json.loads(out)
                if isinstance(items, list):
                    for item in items:
                        name = item.get("metadata", {}).get("name") or item.get("name", "")
                        if name == instance_name or len(items) == 1:
                            url = item.get("status", {}).get("url") or item.get("url", "")
                            if url:
                                harbor_url = url.replace("https://", "").replace("http://", "").rstrip("/")
                                break
            except Exception:
                pass

    if not harbor_url:
        harbor_url = "10.200.0.1"

    return harbor_url, harbor_project, harbor_user, harbor_pass


def resolve_app_image(
    app_name: str,
    image_tag: str = "v1.0.0",
    env_path: Optional[Path] = None,
) -> str:
    """Resolve full Harbor container image reference for GDC workload."""
    harbor_url, harbor_project, _, _ = get_harbor_config(env_path)
    return f"{harbor_url}/{harbor_project}/{app_name}:{image_tag}"


def ensure_harbor_project_exists(
    harbor_url: str,
    harbor_project: str,
    harbor_user: str,
    harbor_pass: str,
    dry_run: bool = False,
) -> None:
    """Ensure the target Harbor project exists via Harbor REST API v2.0."""
    if dry_run:
        common.print_info(f"[DRY-RUN] Would verify Harbor project '{harbor_project}' on '{harbor_url}'.")
        return

    import base64
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    auth_str = base64.b64encode(f"{harbor_user}:{harbor_pass}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json",
    }

    check_url = f"https://{harbor_url}/api/v2.0/projects?name={harbor_project}"
    try:
        req = urllib.request.Request(check_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            if resp.status == 200:
                projects = json.loads(resp.read().decode("utf-8")) or []
                if any(p.get("name") == harbor_project for p in projects):
                    common.print_info(
                        f"[yellow]EXISTS/SKIP[/yellow] Harbor project '{harbor_project}' already exists on '{harbor_url}'."
                    )
                    return
    except Exception:
        pass

    create_url = f"https://{harbor_url}/api/v2.0/projects"
    payload = json.dumps({"project_name": harbor_project, "public": True}).encode("utf-8")
    try:
        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            if resp.status in (200, 201):
                common.print_success(f"Created Harbor project '{harbor_project}' on '{harbor_url}'.")
                return
    except urllib.error.HTTPError as http_err:
        if http_err.code == 409:
            common.print_info(
                f"[yellow]EXISTS/SKIP[/yellow] Harbor project '{harbor_project}' already exists."
            )
            return
        common.print_warning(f"Harbor API returned HTTP {http_err.code} when checking project '{harbor_project}'.")
    except Exception as exc:
        common.print_warning(f"Could not verify Harbor project via REST API: {exc}")


def build_and_push_app_image(
    app_dir: Path,
    app_name: str,
    image_tag: str = "v1.0.0",
    env_path: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Build container image from app_dir and push to GDC Harbor registry."""
    harbor_url, harbor_project, harbor_user, harbor_pass = get_harbor_config(env_path)
    full_image_ref = f"{harbor_url}/{harbor_project}/{app_name}:{image_tag}"

    common.print_header("Step 1a: Authenticate & Verify Harbor Registry (CDS High-Side Target)")
    if dry_run:
        common.print_info(f"[DRY-RUN] Would authenticate to Harbor registry '{harbor_url}' as '{harbor_user}'.")
    else:
        login_res = subprocess.run(
            ["docker", "login", harbor_url, "-u", harbor_user, "--password-stdin"],
            input=harbor_pass,
            text=True,
            capture_output=True,
        )
        if login_res.returncode != 0:
            common.print_error(f"Failed to authenticate to Harbor registry '{harbor_url}':\n{login_res.stderr}")
            sys.exit(1)
        common.print_success(f"Authenticated to Harbor registry '{harbor_url}'.")

    ensure_harbor_project_exists(harbor_url, harbor_project, harbor_user, harbor_pass, dry_run=dry_run)

    common.print_header(f"Step 1b: Build Application Container Image ({app_name}:{image_tag})")
    common.print_info(f"Building multi-stage container image from: [bold cyan]{app_dir}[/bold cyan]")
    code, _, err = common.run_command(
        ["docker", "build", "-t", full_image_ref, str(app_dir)],
        description=f"Building container image {full_image_ref}",
        dry_run=dry_run,
        capture_output=False,
    )
    if not dry_run and code != 0:
        common.print_error(f"Docker build failed for '{full_image_ref}'.")
        sys.exit(1)
    common.print_success(f"Container image built: [bold cyan]{full_image_ref}[/bold cyan]")

    common.print_header("Step 1c: Push Container Image across CDS Boundary to Harbor")
    common.print_info(f"Pushing image to high-side Harbor registry: [bold cyan]{full_image_ref}[/bold cyan]")
    code, _, err = common.run_command(
        ["docker", "push", full_image_ref],
        description=f"Pushing {full_image_ref} to Harbor",
        dry_run=dry_run,
        capture_output=False,
    )
    if not dry_run and code != 0:
        common.print_error(f"Docker push failed for '{full_image_ref}'.")
        sys.exit(1)
    common.print_success(f"CDS image transfer complete: [bold green]{full_image_ref}[/bold green]")
    return full_image_ref


def ensure_image_pull_secret(
    namespace: str,
    service_account: Optional[str] = "default",
    env_path: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    """Idempotently create 'harbor-pull-secret' in target namespace and bind to ServiceAccount."""
    harbor_url, _, harbor_user, harbor_pass = get_harbor_config(env_path)
    common.ensure_k8s_namespace(namespace, dry_run=dry_run)

    secret_name = "harbor-pull-secret"
    common.print_info(f"Ensuring image pull secret '{secret_name}' in namespace '{namespace}'...")

    if dry_run:
        common.print_info(f"[DRY-RUN] Would create/update secret '{secret_name}' in namespace '{namespace}'.")
        return

    create_cmd = [
        "kubectl",
        "create",
        "secret",
        "docker-registry",
        secret_name,
        f"--docker-server={harbor_url}",
        f"--docker-username={harbor_user}",
        f"--docker-password={harbor_pass}",
        "-n",
        namespace,
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    code, out, err = common.run_command(create_cmd, check=False, capture_output=True)
    if code == 0 and out:
        apply_res = subprocess.run(
            ["kubectl", "apply", "-n", namespace, "-f", "-"],
            input=out,
            text=True,
            capture_output=True,
        )
        if apply_res.returncode == 0:
            common.print_success(f"Secret '{secret_name}' configured in namespace '{namespace}'.")
        else:
            common.print_warning(f"Could not apply '{secret_name}': {apply_res.stderr}")

    if service_account:
        patch_payload = json.dumps({"imagePullSecrets": [{"name": secret_name}]})
        subprocess.run(
            ["kubectl", "patch", "serviceaccount", service_account, "-n", namespace, "-p", patch_payload],
            capture_output=True,
            text=True,
        )
