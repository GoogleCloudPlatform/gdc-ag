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

"""Enable Root App-of-Apps GitOps Synchronization in ArgoCD for gitops-workshop.

Idempotently registers internal GitLab credentials in ArgoCD and deploys manifests/root-app.yaml.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from common import (
    RICH_AVAILABLE,
    check_prerequisites,
    confirm_action,
    ensure_deployed_manifests_dir,
    get_active_gcloud_user,
    get_active_gcp_project,
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

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Enable Root App-of-Apps GitOps Synchronization in ArgoCD"
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
        "--recreate-apps",
        action="store_true",
        help="Orphan delete existing ArgoCD Application CRs to reset sync history and cached states before applying.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying cluster state.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    return parser.parse_args()


def print_gitops_completion_banner(root_app_name: str, argocd_url: str = "http://localhost:8080"):
    """Display final completion banner for GitOps Workshop setup."""
    print_success("Root App-of-Apps GitOps control loop enabled successfully.")
    content = (
        f"1. Open ArgoCD UI: [bold cyan]{argocd_url}[/bold cyan] (Log in with Google OAuth)\n"
        f"2. Sync [bold cyan]{root_app_name}[/bold cyan] -> then sync child apps [bold cyan]argocd[/bold cyan] and [bold cyan]gitlab[/bold cyan] (Milestone 4).\n"
        f"3. Proceed to Phase 8 (Self-Service Tenant Workload Provisioning):\n"
        f"   [bold cyan]python3 scripts/project_provision/provision_project.py -g workloads -p demo-project -a frontend[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(f"1. Open ArgoCD UI: {argocd_url}")
        print(f"2. Sync {root_app_name}, then sync argocd and gitlab child apps.")
        print("3. python3 scripts/project_provision/provision_project.py -g workloads -p demo-project -a frontend")




def get_existing_applications(namespace: str = "argocd") -> list:
    """Fetch existing ArgoCD applications in the target namespace."""
    res = subprocess.run(
        ["kubectl", "get", "applications", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        try:
            data = json.loads(res.stdout)
            return data.get("items", [])
        except Exception:
            return []
    return []


def wait_for_gitops_sync(timeout: int = 60, poll_interval: int = 4):
    """Poll ArgoCD applications to verify Git connectivity and manual sync readiness."""
    print_header("Verifying App-of-Apps GitOps Connectivity")
    print_info("Triggering hard refresh on 'root-app'...")
    subprocess.run(
        ["kubectl", "annotate", "app", "root-app", "-n", "argocd", "argocd.argoproj.io/refresh=hard", "--overwrite"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print_info("Verifying ArgoCD Git repository connectivity and Application manifests...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        res = subprocess.run(
            ["kubectl", "get", "applications", "-n", "argocd", "-o", "json"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout)
                apps = data.get("items", [])
                root_apps = [a for a in apps if a.get("metadata", {}).get("name") == "root-app"]
                if root_apps:
                    root_app = root_apps[0]
                    sync_st = root_app.get("status", {}).get("sync", {}).get("status", "Unknown")
                    health_st = root_app.get("status", {}).get("health", {}).get("status", "Unknown")
                    conditions = root_app.get("status", {}).get("conditions", [])

                    # Root app is ready if it successfully resolved revision and has no comparison errors
                    if sync_st in ("OutOfSync", "Synced") and not conditions:
                        if RICH_AVAILABLE:
                            from rich.table import Table
                            table = Table(title="ArgoCD GitOps Applications Status", show_header=True, header_style="bold magenta")
                            table.add_column("Application", style="bold cyan")
                            table.add_column("Sync Status", style="yellow")
                            table.add_column("Health Status", style="green")
                            for a in apps:
                                a_name = a.get("metadata", {}).get("name", "unknown")
                                a_sync = a.get("status", {}).get("sync", {}).get("status", "Unknown")
                                a_health = a.get("status", {}).get("health", {}).get("status", "Unknown")
                                sync_color = "green" if a_sync == "Synced" else "yellow"
                                table.add_row(a_name, f"[{sync_color}]{a_sync}[/{sync_color}]", f"[green]{a_health}[/green]")
                            console.print()
                            console.print(table)
                        print_success("Root App-of-Apps is connected to GitLab and ready for manual sync.")
                        return True

            except Exception:
                pass
        time.sleep(poll_interval)

    print_warning("Could not confirm Git repository sync readiness within timeout. Current state:")
    subprocess.run(["kubectl", "get", "applications", "-n", "argocd"])
    return False


def main():
    # 1. Parse arguments first to get --env-file option
    args = parse_args()

    # 2. Resolve .env file relative to Current Working Directory (CWD)
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 3. Validate required environment variables (strictly from .env)
    env_config = validate_required_env_vars(
        ["ARGOCD_SERVER_URL"],
        env_file_path=env_file_path,
    )
    argocd_url = env_config["ARGOCD_SERVER_URL"]

    print_header("Enable App-of-Apps GitOps Synchronization")

    # 3. Prerequisite check
    if not check_prerequisites(verbose=args.check_prereqs):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 4. Determine GCP Project & Active User
    project_id = get_active_gcp_project(env_file_path) or "Unknown"
    active_user = get_active_gcloud_user() or "None"

    # 5. Check for existing ArgoCD applications
    existing_apps = get_existing_applications("argocd")
    existing_app_names = [a.get("metadata", {}).get("name", "unknown") for a in existing_apps]

    # 6. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "GCP Project ID": project_id,
        "Namespace": "argocd",
        "Root App Manifest": "manifests/root-app.yaml",
        "Source Repo": "gitops-platform/manifests (internal SSH)",
        "Active gcloud User": active_user,
        "Environment File": env_display,
    }
    if existing_app_names:
        params_summary["Existing Applications"] = f"{len(existing_app_names)} apps detected"
    if args.recreate_apps:
        params_summary["Recreate Apps"] = "[bold yellow]YES (--recreate-apps)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="GitOps Handover Parameters")


    # 7. Prompt user for confirmation before proceeding
    if not confirm_action("Do you want to enable the App-of-Apps GitOps control loop in ArgoCD?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 8. Check if existing apps should be recreated to reset history
    recreate_apps = args.recreate_apps
    if existing_apps and not args.recreate_apps and not args.dry_run and not args.auto_approve:
        print_header("Existing Application Resources Detected")
        print_info(f"Found {len(existing_apps)} existing Application CR(s): {', '.join(existing_app_names)}")
        if confirm_action(
            "Would you like to recreate Application resources (cascade orphan) to reset sync history and cached state?",
            auto_approve=False
        ):
            recreate_apps = True

    # 9. Apply AppProject & root-app.yaml manifests
    print_header("Phase 6: Deploying AppProject & Root App-of-Apps Manifests")
    repo_root = Path(__file__).resolve().parents[3]
    deployed_dir = ensure_deployed_manifests_dir()
    project_manifest = deployed_dir / "project.yaml"
    root_app_manifest = deployed_dir / "root-app.yaml"

    if recreate_apps and existing_apps:
        print_info("Removing existing Application CRs with --cascade=orphan (workloads will remain running)...")
        run_command(
            ["kubectl", "delete", "applications", "-n", "argocd", "--all", "--cascade=orphan"],
            description="Orphan deleting existing Application CRs",
            dry_run=args.dry_run
        )
        print_success("Existing Application CRs removed. Fresh state will be initialized.")

    if project_manifest.exists():
        print_info("Applying AppProject 'gitops-platform' specification...")
        run_command(
            ["kubectl", "apply", "-n", "argocd", "-f", str(project_manifest)],
            description="Applying manifests/project.yaml",
            dry_run=args.dry_run
        )

    if not root_app_manifest.exists():
        print_error(f"Root app manifest not found at {root_app_manifest}")
        sys.exit(1)

    print_info("Applying Root App specification to ArgoCD...")
    run_command(
        ["kubectl", "apply", "-n", "argocd", "-f", str(root_app_manifest)],
        description="Applying manifests/root-app.yaml",
        dry_run=args.dry_run
    )

    print_success("Phase 6 Root App-of-Apps specification applied successfully.")

    # 10. Wait & verify GitOps synchronization if not dry-run
    if not args.dry_run:
        wait_for_gitops_sync()

    # 11. Display Completion Instructions Banner
    print_gitops_completion_banner("root-app", argocd_url=argocd_url)


if __name__ == "__main__":
    main()
