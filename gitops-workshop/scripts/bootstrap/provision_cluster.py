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

"""Provision Kubernetes cluster for gitops-workshop.

Idempotently creates/verifies the cluster and networking configuration, and configures local kubectl context.
Supports Google Cloud Platform (GCP GKE Autopilot) and Google Distributed Cloud (GDC Sandbox).
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from common import (
    RICH_AVAILABLE,
    check_prerequisites,
    confirm_action,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_parameter_summary,
    print_success,
    print_warning,
    validate_required_env_vars,
)
from platform_adapter import (
    get_target_platform,
    get_prereqs_provider,
    get_project_provider,
    get_cluster_provider,
    get_config,
)


if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Provision Kubernetes Cluster for GitOps Workshop (GCP / GDC)"
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env configuration file (relative to current execution directory). Default: .env",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Check tool dependencies and environment setup without making changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying infrastructure.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    parser.add_argument(
        "--platform",
        choices=["gcp", "gdc"],
        help="Target platform override (gcp | gdc). Defaults to TARGET_PLATFORM in .env or gcp.",
    )
    parser.add_argument(
        "--project",
        help="GCP Project name/ID. Sourced from .env or active configuration.",
    )
    parser.add_argument(
        "--network",
        help="VPC Network name (GCP). Defaults to GCP_VPC_NETWORK in .env or <cluster-name>-vpc.",
    )
    parser.add_argument(
        "--region",
        help="GCP Region for GKE cluster. Defaults to GCP_REGION in .env or us-central1.",
    )
    parser.add_argument(
        "--cluster-name",
        help="Name of cluster to create/verify. Defaults to GKE_CLUSTER_NAME / CLUSTER_NAME in .env.",
    )
    return parser.parse_args()


def print_cluster_next_steps(cluster_name: str, region: str, project_id: str, platform: str, env_file: Optional[str] = None):
    """Display completion banner for Cluster Provisioning."""
    print_success(f"Phase 2 Cluster '{cluster_name}' is ready on {platform.upper()}.")
    env_flag = ""
    if env_file:
        env_str = str(env_file)
        if env_str not in [".env", str(Path.cwd() / ".env")]:
            env_flag = f" -e {env_str}"

    if platform.lower() == "gdc":
        content = (
            f"1. Verify cluster node status:\n"
            f"   [bold cyan]kubectl get nodes[/bold cyan]\n"
            f"2. Proceed to Phase 3 (Mirror Container Images to Harbor):\n"
            f"   [bold cyan]python3 scripts/common/gdc/mirror_images.py{env_flag}[/bold cyan]"
        )
        plain_content = (
            f"1. kubectl get nodes\n"
            f"2. python3 scripts/common/gdc/mirror_images.py{env_flag}"
        )
    else:
        content = (
            f"1. Verify cluster deployments via kubectl:\n"
            f"   [bold cyan]kubectl get nodes[/bold cyan]\n"
            f"2. Proceed to Phase 3 (Install ArgoCD):\n"
            f"   [bold cyan]python3 scripts/bootstrap/argocd/install_argocd.py{env_flag}[/bold cyan]"
        )
        plain_content = (
            f"1. kubectl get nodes\n"
            f"2. python3 scripts/bootstrap/argocd/install_argocd.py{env_flag}"
        )

    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(plain_content)


def main():
    # 1. Parse arguments first to get --env-file option
    args = parse_args()

    # 2. Resolve .env file relative to Current Working Directory (CWD)
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 3. Determine target platform & load providers
    target_platform = args.platform or get_target_platform(env_file_path)
    prereqs_provider = get_prereqs_provider(target_platform)
    project_provider = get_project_provider(target_platform)
    cluster_provider = get_cluster_provider(target_platform)

    # 4. Load configuration & validate required environment variables based on platform
    config = get_config(
        env_file_path,
        cli_overrides={
            "project_id": args.project,
            "region": args.region,
            "cluster_name": args.cluster_name,
        },
    )
    validate_required_env_vars(
        config.required_vars,
        env_file_path=env_file_path,
    )
    project_id = config.project_id
    region = config.region if target_platform == "gcp" else "sandbox"
    cluster_name = config.cluster_name
    network_name = args.network or (os.environ.get("GCP_VPC_NETWORK_OVERRIDE") or f"{cluster_name}-vpc" if target_platform == "gcp" else "gdc-internal")


    print_header(f"Cluster Provisioning ({target_platform.upper()} Mode)")

    # 5. Prerequisite check
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 6. Display Execution Parameter Summary Table
    active_user = project_provider.get_active_identity() or "None"
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "Project / Context": project_id,
        "Cluster / Region": f"{cluster_name} ({region})",
        "VPC Network Name": network_name if target_platform == "gcp" else "Managed CNI",
        "Active User / Identity": active_user,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Cluster Provisioning Parameters")

    # 7. Prompt user for confirmation before proceeding
    if not confirm_action(f"Do you want to provision/verify the {target_platform.upper()} cluster '{cluster_name}'?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 8. Provision / verify cluster
    print_header(f"Phase 2: Ensuring {target_platform.upper()} Cluster Readiness")
    cluster_provider.ensure_cluster(
        cluster_name,
        region=region,
        project_id=project_id,
        network_name=network_name if target_platform == "gcp" else None,
        dry_run=args.dry_run
    )

    if args.dry_run:
        print_warning("Running in DRY-RUN mode. No cluster changes were applied.")

    # 9. Display completion instructions banner
    print_cluster_next_steps(cluster_name, region, project_id, target_platform, env_file=args.env_file)


if __name__ == "__main__":
    main()
