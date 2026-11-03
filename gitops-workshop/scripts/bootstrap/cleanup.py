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

"""Teardown script for gitops-workshop.

Safely and idempotently deletes the cluster, networking, and workshop resources.
Supports Google Cloud Platform and Google Distributed Cloud Sandbox via decoupled platform providers.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from common import (
    RICH_AVAILABLE,
    check_tool_installed,
    confirm_action,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_parameter_summary,
    print_success,
    print_warning,
    run_command,
    validate_required_env_vars,
)
from platform_adapter import (
    get_target_platform,
    get_prereqs_provider,
    get_project_provider,
    get_cleanup_provider,
)

if RICH_AVAILABLE:
    from rich.panel import Panel
    from rich.console import Console
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Teardown GitOps workshop environment (GCP / GDC)"
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
        help="Verify required prerequisites and exit",
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
        help="Automatically approve teardown prompts without interactive confirmation.",
    )
    parser.add_argument(
        "--platform",
        choices=["gcp", "gdc"],
        help="Target platform override (gcp | gdc). Defaults to TARGET_PLATFORM in .env or gcp.",
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID. Sourced from .env (GCP_PROJECT) or active configuration.",
    )
    parser.add_argument(
        "--region",
        help="GCP Region for GKE cluster. Sourced from .env (GCP_REGION) or us-central1.",
    )
    parser.add_argument(
        "--cluster-name",
        help="Name of cluster to delete. Sourced from .env or gitops-demo-cluster.",
    )
    parser.add_argument(
        "--network",
        help="VPC Network name (GCP). Defaults to GCP_VPC_NETWORK_OVERRIDE or <cluster-name>-vpc.",
    )
    parser.add_argument(
        "--delete-project",
        action="store_true",
        help="Also delete the entire GCP project after destroying cluster and networking resources.",
    )
    return parser.parse_args()


def print_completion_banner(project_id: str, cluster_name: str, network_name: str, project_deleted: bool = False, platform: str = "gcp"):
    """Display completion banner for teardown."""
    if platform == "gdc":
        print_success(f"Workshop namespaces purged from GDC cluster '{cluster_name}'.")
        content = (
            f"GDC standard cluster [bold cyan]{cluster_name}[/bold cyan] is reset to a clean baseline.\n"
            f"Cluster infrastructure and node pools remain online.\n\n"
            f"To re-provision from scratch, run:\n"
            f"  [bold cyan]python3 scripts/bootstrap/argocd/install_argocd.py -e .env.gdc.example[/bold cyan]"
        )
    elif project_deleted:
        print_success(f"GCP Project '{project_id}' deleted successfully.")
        content = "All workshop cloud infrastructure has been fully decommissioned."
    else:
        print_success(f"Cluster '{cluster_name}' and network '{network_name}' removed.")
        content = (
            f"Project/Environment context [bold cyan]{project_id}[/bold cyan] remains active.\n"
            f"To re-provision, run: [bold cyan]python3 scripts/bootstrap/bootstrap.py[/bold cyan]"
        )

    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold red]Teardown Complete[/bold red]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Teardown Complete ---")
        if platform == "gdc":
            print(f"Workshop namespaces purged from GDC cluster '{cluster_name}'.")
        elif project_deleted:
            print(f"GCP Project '{project_id}' deleted successfully.")
        else:
            print(f"Cluster '{cluster_name}' and network '{network_name}' removed from '{project_id}'.")


def main():
    args = parse_args()

    # 1. Resolve .env file relative to Current Working Directory (CWD)
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 2. Determine target platform & load providers
    target_platform = args.platform or get_target_platform(env_file_path)
    prereqs_provider = get_prereqs_provider(target_platform)
    project_provider = get_project_provider(target_platform)
    cleanup_provider = get_cleanup_provider(target_platform)

    # 3. Validate required environment variables based on platform
    if target_platform == "gcp":
        env_config = validate_required_env_vars(
            ["GCP_PROJECT", "GCP_REGION", "GKE_CLUSTER_NAME"],
            env_file_path=env_file_path,
            cli_overrides={
                "GCP_PROJECT": args.project,
                "GCP_REGION": args.region,
                "GKE_CLUSTER_NAME": args.cluster_name,
            },
        )
        project = env_config["GCP_PROJECT"]
        region = env_config["GCP_REGION"]
        cluster_name = env_config["GKE_CLUSTER_NAME"]
        network_name = (args.network or os.environ.get("GCP_VPC_NETWORK_OVERRIDE") or f"{cluster_name}-vpc").strip().lower()
    else:
        env_config = validate_required_env_vars(
            ["CLUSTER_NAME"],
            env_file_path=env_file_path,
            cli_overrides={"CLUSTER_NAME": args.cluster_name},
        )
        project = "gdc"
        region = "sandbox"
        cluster_name = env_config["CLUSTER_NAME"]
        network_name = "gdc-internal"

    active_user = project_provider.get_active_identity() or "None"

    print_header(f"GitOps Workshop Cleanup & Teardown ({target_platform.upper()} Mode)")

    # 4. Prerequisite check
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 5. Display execution parameters table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "Project ID / Context": project,
        "Cluster / Region": f"{cluster_name} ({region})",
        "VPC Network": network_name if target_platform == "gcp" else "Managed CNI",
        "Active User / Identity": active_user,
        "Environment File": env_display,
    }
    if args.delete_project and target_platform == "gcp":
        params_summary["Delete GCP Project"] = "[bold red]YES (Permanent)[/bold red]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Teardown Configuration Parameters")

    # 6. Execute platform teardown
    project_deleted = cleanup_provider.teardown_platform(
        project=project,
        cluster_name=cluster_name,
        region=region,
        network_name=network_name,
        delete_project=args.delete_project,
        auto_approve=args.auto_approve,
        dry_run=args.dry_run
    )

    if not args.dry_run:
        repo_root = Path(__file__).resolve().parents[2]
        deployed_dir = repo_root / ".deployed-manifests"
        if deployed_dir.exists():
            shutil.rmtree(deployed_dir)
            print_info(f"Purged deployed manifests working directory: {deployed_dir.name}/")

        print_completion_banner(project, cluster_name, network_name, project_deleted=project_deleted, platform=target_platform)


if __name__ == "__main__":
    main()
