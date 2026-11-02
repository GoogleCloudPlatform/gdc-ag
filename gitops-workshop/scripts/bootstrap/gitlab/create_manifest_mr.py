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

"""Create and seed initial Kubernetes manifests Merge Request in GitLab for gitops-workshop.

Copies the local manifests/ directory to a feature branch 'feature/initial-manifests',
pushes it to GitLab, creates Merge Request #1 into 'main', and prompts the user to review and merge it.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

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
from platform_adapter import get_config


from gitlab_utils import (  # noqa: E402
    check_git_remote_branch,
    get_gitlab_credentials,
    get_gitlab_open_mr,
    sync_git_repo_with_mr,
)

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Manifests Feature Branch and Merge Request in GitLab"
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
        help="Simulate execution without modifying cluster state.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    parser.add_argument(
        "-m",
        "--mr-approve",
        action="store_true",
        help="Automatically approve and merge created GitLab Merge Requests via API.",
    )
    return parser.parse_args()




def print_completion_banner(mr_url: Optional[str] = None):
    """Display completion banner for GitLab repository seeding."""
    print_success("GitLab manifests feature branch and Merge Request created.")
    content_lines = []
    if mr_url:
        content_lines.append(f"1. Review & Merge MR in GitLab (Milestone 3):\n   [bold cyan]{mr_url}[/bold cyan]")
    else:
        content_lines.append("1. Review & Merge open MRs in GitLab:\n   [bold cyan]http://localhost:8081/gitops-platform/manifests/-/merge_requests[/bold cyan]")
    content_lines.append("2. Proceed to Phase 6 (Configure ArgoCD GitLab SSH Auth):\n   [bold cyan]python3 scripts/bootstrap/gitops/setup_gitlab_auth.py[/bold cyan]")

    content = "\n".join(content_lines)
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        if mr_url:
            print(f"1. Review & Merge MR: {mr_url}")
        else:
            print("1. Review & Merge open MRs in GitLab: http://localhost:8081/gitops-platform/manifests/-/merge_requests")
        print("2. python3 scripts/bootstrap/gitops/setup_gitlab_auth.py")


def main():
    args = parse_args()

    # 1. Resolve .env file relative to Current Working Directory
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)
    config = get_config(env_file_path)

    # 2. Validate required environment variables (strictly from .env)
    env_config = validate_required_env_vars(
        ["GITLAB_HTTP_URL"],
        env_file_path=env_file_path,
    )
    gitlab_http_url = env_config["GITLAB_HTTP_URL"]
    project_id = config.project_id or get_active_gcp_project(env_file_path) or "Unknown"
    active_user = config.admin_email or get_active_gcloud_user() or "None"
    root_pass, _ = get_gitlab_credentials()


    # 3. Resolve deployed manifests directory
    manifests_dir = ensure_deployed_manifests_dir()
    if not manifests_dir.exists():
        print_error(f"Manifests directory not found at: {manifests_dir}")
        sys.exit(1)

    print_header("Seed Manifests & Create Merge Request")

    # 4. Check prerequisites
    if not check_prerequisites(verbose=args.check_prereqs):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 5. Display Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "GCP Project ID": project_id,
        "Target Project": "gitops-platform/manifests",
        "Target Branch": "main",
        "Source Manifests": "manifests/",
        "Active gcloud User": active_user,
        "Environment File": env_display,
    }
    if args.mr_approve:
        params_summary["MR Auto-Merge"] = "[bold yellow]YES (-m)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Manifest MR Parameters")

    # 6. Prompt confirmation
    if not confirm_action("Do you want to check local manifests and push changes to GitLab?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 7. Define file update callback
    def copy_manifest_files(working_dir: Path):
        shutil.copytree(manifests_dir, working_dir / "manifests", dirs_exist_ok=True)
        root_app_src = manifests_dir / "root-app.yaml"
        if root_app_src.exists():
            shutil.copy(root_app_src, working_dir / "root-app.yaml")

        target_platform = os.environ.get("TARGET_PLATFORM", "gcp").lower()
        overlay_target = "gdc" if target_platform == "gdc" else "gcp"

        argocd_app = working_dir / "manifests" / "apps" / "argocd.yaml"
        if argocd_app.exists():
            content = argocd_app.read_text()
            content = content.replace(
                "path: manifests/argocd\n",
                f"path: manifests/argocd/overlays/{overlay_target}\n"
            )
            argocd_app.write_text(content)

        gitlab_app = working_dir / "manifests" / "apps" / "gitlab.yaml"
        if gitlab_app.exists():
            content = gitlab_app.read_text()
            content = content.replace(
                "path: manifests/gitlab\n",
                f"path: manifests/gitlab/overlays/{overlay_target}\n"
            )
            gitlab_app.write_text(content)

    owner_email = config.admin_email

    # 8. Sync git repo with branching and interactive MR
    has_changes, feature_branch, mr_url = sync_git_repo_with_mr(
        project_path="gitops-platform/manifests",
        branch_prefix="feature/update-manifests",
        commit_message="Update GitOps application manifests",
        mr_title="Update GitOps Application Manifests",
        mr_description="Update Kubernetes manifests for ArgoCD App-of-Apps synchronization.",
        update_files_callback=copy_manifest_files,
        assignee=owner_email,
        root_pass=root_pass,
        target_branch="main",
        auto_approve=args.auto_approve,
        mr_approve=args.mr_approve,
        dry_run=args.dry_run,
    )


    if has_changes:
        print_completion_banner(mr_url=mr_url)



if __name__ == "__main__":
    main()
