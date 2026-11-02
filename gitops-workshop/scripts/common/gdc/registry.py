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

"""Container registry and image provider for Google Distributed Cloud (GDC) Sandbox."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common

if common.RICH_AVAILABLE:
    from rich.table import Table


# List of required workshop images and their target tags in Harbor
REQUIRED_IMAGES: List[Dict[str, Any]] = [
    {
        "name": "argocd",
        "upstream": "quay.io/argoproj/argocd:v3.5.1",
        "target_image": "argocd",
        "target_tag": "v3.5.1",
    },
    {
        "name": "dex",
        "upstream": "ghcr.io/dexidp/dex:v2.45.0",
        "target_image": "dex",
        "target_tag": "v2.45.0",
    },
    {
        "name": "redis",
        "upstream": "public.ecr.aws/docker/library/redis:8.2.3-alpine",
        "target_image": "redis",
        "target_tag": "8.2.3-alpine",
    },
    {
        "name": "python",
        "upstream": "python:3.11-alpine",
        "target_image": "python",
        "target_tag": "3.11-alpine",
    },
    {
        "name": "gitlab-ce",
        "upstream": "gitlab/gitlab-ce:latest",
        "target_image": "gitlab-ce",
        "target_tag": "latest",
    },
    {
        "name": "nginx",
        "upstream": "nginx:1.27-alpine",
        "target_image": "nginx",
        "target_tag": "1.27-alpine",
    },
]


def resolve_image(component: str, default_upstream: str) -> str:
    """Rewrite public container images to internal Harbor registry."""
    harbor_url = os.environ.get("HARBOR_URL", "").strip()
    harbor_project = os.environ.get("HARBOR_PROJECT", "project-lowhigh").strip()
    prefix = os.environ.get("CONTAINER_REGISTRY_PREFIX", "").strip() or (f"{harbor_url}/{harbor_project}" if harbor_url else "")
    prefix = prefix.rstrip("/")
    if not prefix:
        return default_upstream

    # Check if component is in known REQUIRED_IMAGES
    match = next((item for item in REQUIRED_IMAGES if item["name"] == component), None)
    if match:
        return f"{prefix}/{match['target_image']}:{match['target_tag']}"

    # Default fallback: strip existing host and use component name / image tag
    parts = default_upstream.split("/")
    image_and_tag = parts[-1]
    return f"{prefix}/{image_and_tag}"


def ensure_image_pull_secret(
    namespace: str,
    service_account: Optional[str] = None,
    dry_run: bool = False
) -> None:
    """Ensure Harbor image pull secret is created and linked to ServiceAccount(s) in target namespace."""
    secret_name = os.environ.get("IMAGE_PULL_SECRET_NAME", "harbor-secret")
    harbor_url = os.environ.get("HARBOR_URL", "").strip()
    harbor_user = os.environ.get("HARBOR_USERNAME", "").strip()
    harbor_password = os.environ.get("HARBOR_PASSWORD", "").strip()

    if not harbor_url or not harbor_user or not harbor_password:
        common.print_warning(
            f"Harbor credentials incomplete (HARBOR_URL={bool(harbor_url)}, HARBOR_USERNAME={bool(harbor_user)}). "
            f"Skipping pull secret creation for namespace '{namespace}'."
        )
        return

    common.print_info(f"Ensuring imagePullSecret '{secret_name}' in namespace '{namespace}'...")

    # 1. Ensure namespace exists
    common.ensure_k8s_namespace(namespace, dry_run=dry_run)

    # 2. Check if secret already exists
    code, _, _ = common.run_command(
        ["kubectl", "get", "secret", secret_name, "-n", namespace],
        check=False,
        capture_output=True,
    )
    if code == 0:
        common.print_success(f"Secret '{secret_name}' already exists in namespace '{namespace}'.")
    else:
        # Create docker-registry secret idempotently
        cmd = [
            "kubectl", "create", "secret", "docker-registry", secret_name,
            f"--namespace={namespace}",
            f"--docker-server={harbor_url}",
            f"--docker-username={harbor_user}",
            f"--docker-password={harbor_password}",
            "--dry-run=client", "-o", "yaml",
        ]
        code, out, err = common.run_command(cmd, check=False, capture_output=True)
        if code != 0 or not out:
            common.print_error(f"Failed to generate secret YAML for '{secret_name}': {err}")
            return

        if dry_run:
            common.print_info(f"[DRY-RUN] Would apply secret '{secret_name}' in namespace '{namespace}'.")
        else:
            apply_res = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=out,
                text=True,
                capture_output=True,
            )
            if apply_res.returncode == 0:
                common.print_success(f"Created secret '{secret_name}' in namespace '{namespace}'.")
            else:
                common.print_error(f"Failed to apply secret '{secret_name}': {apply_res.stderr}")
                return

    # 3. Patch ServiceAccount(s)
    sa_list: List[str] = []
    if service_account:
        sa_list = [service_account]
    else:
        # Get all ServiceAccounts in the namespace
        sa_code, sa_out, _ = common.run_command(
            ["kubectl", "get", "serviceaccounts", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"],
            check=False,
            capture_output=True,
        )
        if sa_code == 0 and sa_out.strip():
            sa_list = sa_out.strip().split()
        else:
            sa_list = ["default"]

    patched_any = False
    patch_json = json.dumps({"imagePullSecrets": [{"name": secret_name}]})
    for sa in sa_list:
        if dry_run:
            common.print_info(f"[DRY-RUN] Would patch ServiceAccount '{sa}' in '{namespace}' with imagePullSecret '{secret_name}'.")
        else:
            p_code, _, p_err = common.run_command(
                ["kubectl", "patch", "serviceaccount", sa, "-n", namespace, "-p", patch_json],
                check=False,
                capture_output=True,
            )
            if p_code == 0:
                patched_any = True
                common.print_success(f"Linked '{secret_name}' to ServiceAccount '{sa}' in namespace '{namespace}'.")
            else:
                common.print_warning(f"Could not patch ServiceAccount '{sa}' in namespace '{namespace}': {p_err}")

    if patched_any and not dry_run:
        code, out, _ = common.run_command(
            ["kubectl", "get", "pods", "-n", namespace, "--field-selector=status.phase!=Running", "-o", "jsonpath={.items[*].metadata.name}"],
            check=False, capture_output=True
        )
        if code == 0 and out.strip():
            stale_pods = out.strip().split()
            common.print_info(f"Recycling {len(stale_pods)} pod(s) in '{namespace}' to inherit newly linked imagePullSecrets...")
            common.run_command(["kubectl", "delete", "pods", "-n", namespace] + stale_pods, check=False, capture_output=True)


def get_harbor_target_tag(image_entry: Dict[str, Any]) -> str:
    """Return the full target image reference in Harbor."""
    harbor_url = os.environ.get("HARBOR_URL", "user-haas-instance-user-project.org-1.zone1.google.gdch.test").strip()
    harbor_project = os.environ.get("HARBOR_PROJECT", "project-lowhigh").strip()
    return f"{harbor_url}/{harbor_project}/{image_entry['target_image']}:{image_entry['target_tag']}"


def check_docker_image_exists(image_ref: str) -> bool:
    """Check if an image exists in the local Docker daemon."""
    code, _, _ = common.run_command(["docker", "image", "inspect", image_ref], check=False, capture_output=True)
    return code == 0


def login_to_harbor(dry_run: bool = False) -> bool:
    """Authenticate Docker client with Harbor registry using environment credentials."""
    harbor_url = os.environ.get("HARBOR_URL", "").strip()
    harbor_user = os.environ.get("HARBOR_USERNAME", "").strip()
    harbor_password = os.environ.get("HARBOR_PASSWORD", "").strip()

    if not harbor_url or not harbor_user or not harbor_password:
        common.print_error("Missing Harbor credentials in environment (HARBOR_URL, HARBOR_USERNAME, HARBOR_PASSWORD).")
        return False

    if dry_run:
        common.print_info(f"[DRY-RUN] Would execute: docker login {harbor_url} -u '{harbor_user}' --password-stdin")
        return True

    res = subprocess.run(
        ["docker", "login", harbor_url, "-u", harbor_user, "--password-stdin"],
        input=harbor_password,
        text=True,
        capture_output=True,
    )
    if res.returncode == 0:
        common.print_success(f"Docker login to Harbor '{harbor_url}' succeeded.")
        return True
    else:
        common.print_error(f"Docker login failed: {res.stderr.strip()}")
        return False


def mirror_required_images(
    check_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """Check and/or mirror required workshop container images to Harbor."""
    harbor_url = os.environ.get("HARBOR_URL", "").strip()
    harbor_project = os.environ.get("HARBOR_PROJECT", "project-lowhigh").strip()

    if not harbor_url:
        common.print_error("HARBOR_URL is not set. Please ensure .env contains Harbor configuration.")
        return False

    common.print_info(f"Target Harbor Registry: [bold cyan]{harbor_url}/{harbor_project}[/bold cyan]")

    status_rows = []
    all_ready = True

    for item in REQUIRED_IMAGES:
        target_ref = get_harbor_target_tag(item)
        has_target = check_docker_image_exists(target_ref)
        has_upstream = check_docker_image_exists(item["upstream"])

        if has_target:
            status = "[bold green]READY[/bold green]"
        elif has_upstream:
            status = "[yellow]LOCAL UPSTREAM[/yellow]"
        else:
            status = "[bold red]MISSING[/bold red]"

        if not has_target and not has_upstream:
            all_ready = False

        status_rows.append((item["name"], item["upstream"], target_ref, status, has_target, has_upstream))

    # Display Rich Table
    if common.RICH_AVAILABLE:
        table = Table(title="Harbor Container Image Mirror Status", show_header=True)
        table.add_column("Component", style="cyan", width=15)
        table.add_column("Upstream Reference", style="dim", width=40)
        table.add_column("Target Harbor Reference", style="blue", width=55)
        table.add_column("Status", width=18)

        for name, upstream, target_ref, status, _, _ in status_rows:
            table.add_row(name, upstream, target_ref, status)

        common.console.print(table)

    if check_only:
        if all_ready:
            common.print_success("All required container images are present and tagged for Harbor.")
        else:
            common.print_warning("Some images are not yet tagged or pushed to Harbor.")
        return all_ready

    # Login to Harbor
    if not login_to_harbor(dry_run=dry_run):
        return False

    # Process each image
    for item in REQUIRED_IMAGES:
        target_ref = get_harbor_target_tag(item)
        upstream_ref = item["upstream"]
        has_target = check_docker_image_exists(target_ref)
        has_upstream = check_docker_image_exists(upstream_ref)

        if has_target and not force:
            common.print_info(f"Image '{target_ref}' is present locally. Pushing to Harbor...")
        elif has_upstream:
            common.print_info(f"Tagging '{upstream_ref}' -> '{target_ref}'...")
            if not dry_run:
                common.run_command(["docker", "tag", upstream_ref, target_ref], check=True)
        else:
            common.print_info(f"Pulling upstream image '{upstream_ref}'...")
            if not dry_run:
                code, _, err = common.run_command(["docker", "pull", upstream_ref], check=False)
                if code != 0:
                    common.print_error(f"Failed to pull '{upstream_ref}': {err}")
                    return False
                common.run_command(["docker", "tag", upstream_ref, target_ref], check=True)

        # Push to Harbor
        common.print_info(f"Pushing '{target_ref}' to Harbor...")
        if not dry_run:
            p_code, _, p_err = common.run_command(["docker", "push", target_ref], check=False)
            if p_code == 0:
                common.print_success(f"Successfully pushed '{target_ref}' to Harbor.")
            else:
                common.print_error(f"Failed to push '{target_ref}' to Harbor: {p_err}")
                return False
        else:
            common.print_info(f"[DRY-RUN] Would execute: docker push {target_ref}")

    common.print_success("All workshop images mirrored to Harbor successfully.")
    return True


def prepare_argocd_kustomization(manifest_dir: Path) -> Path:
    """Return ArgoCD Kustomization directory for GDC."""
    gdc_overlay = manifest_dir / "overlays" / "gdc"
    if gdc_overlay.exists():
        return gdc_overlay
    return manifest_dir


def prepare_gitlab_kustomization(manifest_dir: Path) -> Path:
    """Return GitLab Kustomization directory for GDC."""
    gdc_overlay = manifest_dir / "overlays" / "gdc"
    if gdc_overlay.exists():
        return gdc_overlay
    return manifest_dir
