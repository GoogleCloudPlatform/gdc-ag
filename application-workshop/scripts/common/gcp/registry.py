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

"""Container registry & CDS image push provider for Google Cloud Platform (GCP Artifact Registry)."""

import os
from pathlib import Path
import sys
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_gar_config(env_path: Optional[Path] = None) -> Tuple[str, str, str]:
    """Return (project_id, region, gar_repository) for GCP Artifact Registry."""
    env = common.load_dotenv(env_path)
    project_id = (
        env.get("GCP_PROJECT") or os.environ.get("GCP_PROJECT") or ""
    ).strip()
    region = (
        env.get("GCP_REGION") or os.environ.get("GCP_REGION") or "us-central1"
    ).strip()
    gar_repo = (
        env.get("GAR_REPOSITORY")
        or os.environ.get("GAR_REPOSITORY")
        or "gitops-workloads"
    ).strip()
    return project_id, region, gar_repo


def resolve_app_image(
    app_name: str,
    image_tag: str = "v1.0.0",
    env_path: Optional[Path] = None,
) -> str:
    """Resolve full Artifact Registry container image reference for GCP workload."""
    project_id, region, gar_repo = get_gar_config(env_path)
    return f"{region}-docker.pkg.dev/{project_id}/{gar_repo}/{app_name}:{image_tag}"


def ensure_gar_repository_exists(
    project_id: str,
    region: str,
    gar_repo: str,
    dry_run: bool = False,
) -> None:
    """Idempotently ensure Artifact Registry Docker repository exists in the GCP project."""
    common.print_info(
        f"Verifying Artifact Registry repository '{gar_repo}' in '{region}' (project: '{project_id}')..."
    )
    if dry_run:
        common.print_info(
            f"[DRY-RUN] Would ensure Artifact Registry repository '{gar_repo}' exists in '{region}'."
        )
        return

    common.run_command(
        ["gcloud", "services", "enable", "artifactregistry.googleapis.com", f"--project={project_id}"],
        description="Enabling artifactregistry.googleapis.com API",
        check=False,
        capture_output=True,
    )

    desc_code, _, _ = common.run_command(
        [
            "gcloud",
            "artifacts",
            "repositories",
            "describe",
            gar_repo,
            f"--location={region}",
            f"--project={project_id}",
        ],
        check=False,
        capture_output=True,
    )
    if desc_code == 0:
        common.print_info(
            f"[yellow]EXISTS/SKIP[/yellow] Artifact Registry repository '{gar_repo}' already exists."
        )
        return

    code, _, err = common.run_command(
        [
            "gcloud",
            "artifacts",
            "repositories",
            "create",
            gar_repo,
            "--repository-format=docker",
            f"--location={region}",
            f"--project={project_id}",
            "--description=GitOps Application Workshop Container Registry",
        ],
        description=f"Creating Artifact Registry repository '{gar_repo}'",
        check=False,
        capture_output=True,
    )
    if code == 0:
        common.print_success(f"Created Artifact Registry repository '{gar_repo}'.")
    else:
        common.print_warning(f"Could not create Artifact Registry repository '{gar_repo}': {err}")


def build_and_push_app_image(
    app_dir: Path,
    app_name: str,
    image_tag: str = "v1.0.0",
    env_path: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Build container image from app_dir and push to GCP Artifact Registry."""
    project_id, region, gar_repo = get_gar_config(env_path)
    registry_host = f"{region}-docker.pkg.dev"
    full_image_ref = f"{registry_host}/{project_id}/{gar_repo}/{app_name}:{image_tag}"

    common.print_header("Step 1a: Configure Artifact Registry Authentication & Repository")
    common.run_command(
        ["gcloud", "auth", "configure-docker", registry_host, "--quiet"],
        description=f"Configuring Docker authentication for {registry_host}",
        dry_run=dry_run,
        capture_output=True,
    )
    ensure_gar_repository_exists(project_id, region, gar_repo, dry_run=dry_run)

    common.print_header(f"Step 1b: Build Application Container Image ({app_name}:{image_tag})")
    common.print_info(f"Building multi-stage container image from: [bold cyan]{app_dir}[/bold cyan]")
    code, _, _ = common.run_command(
        ["docker", "build", "-t", full_image_ref, str(app_dir)],
        description=f"Building container image {full_image_ref}",
        dry_run=dry_run,
        capture_output=False,
    )
    if not dry_run and code != 0:
        common.print_error(f"Docker build failed for '{full_image_ref}'.")
        sys.exit(1)
    common.print_success(f"Container image built: [bold cyan]{full_image_ref}[/bold cyan]")

    common.print_header("Step 1c: Push Container Image to Artifact Registry")
    common.print_info(f"Pushing image to Artifact Registry: [bold cyan]{full_image_ref}[/bold cyan]")
    code, _, _ = common.run_command(
        ["docker", "push", full_image_ref],
        description=f"Pushing {full_image_ref} to Artifact Registry",
        dry_run=dry_run,
        capture_output=False,
    )
    if not dry_run and code != 0:
        common.print_error(f"Docker push failed for '{full_image_ref}'.")
        sys.exit(1)
    common.print_success(f"Image push complete: [bold green]{full_image_ref}[/bold green]")
    return full_image_ref


def ensure_image_pull_secret(
    namespace: str,
    service_account: Optional[str] = "default",
    env_path: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    """Ensure target namespace exists on GKE (Artifact Registry uses node/workload identity)."""
    common.ensure_k8s_namespace(namespace, dry_run=dry_run)
