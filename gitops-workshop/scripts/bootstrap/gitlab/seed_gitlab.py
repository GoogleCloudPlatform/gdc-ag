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

"""Seed gitops-platform/manifests repository in GitLab Omnibus for gitops-workshop.

Creates group 'gitops-platform' and project 'gitops-platform/manifests' in GitLab,
grants Owner access to the GCP Project Owner, initializes 'main' branch,
pushes manifests to a feature branch, creates a Merge Request, and prompts the user to review and merge it.

Includes sub-second fast REST API pre-checks to inspect GitLab state without booting Rails.
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
import urllib.parse
import urllib.request
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from common import (
    RICH_AVAILABLE,
    check_prerequisites,
    confirm_action,
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
    ensure_gitlab_group,
    ensure_gitlab_project,
    ensure_gitlab_user,
    ensure_group_member,
    ensure_user_ssh_key,
    get_gitlab_client,
    get_gitlab_credentials,
    sync_git_repo_with_mr,
)

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed gitops-platform/manifests Repository in GitLab via Merge Request Workflow"
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


def print_seeding_completion_banner(repo_url: str):
    """Display completion banner for GitLab repository seeding."""
    print_success("GitLab 'gitops-platform/manifests' repository seeded and merged successfully.")
    content = (
        f"1. Internal Git URL: [bold cyan]{repo_url}[/bold cyan]\n"
        f"2. External Git URL: [bold cyan]http://localhost:8081/gitops-platform/manifests.git[/bold cyan]\n"
        f"3. Proceed to Phase 5A (Configure ArgoCD GitLab Auth & Deploy Keys):\n"
        f"   [bold cyan]python3 scripts/bootstrap/gitops/setup_gitlab_auth.py[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(f"1. Internal Git URL: {repo_url}")
        print(f"2. External Git URL: http://localhost:8081/gitops-platform/manifests.git")
        print("3. python3 scripts/bootstrap/gitops/setup_gitlab_auth.py")



def run_rails_runner(ruby_code: str, description: str = "Running gitlab-rails command"):
    """Execute Ruby code inside the gitlab-omnibus pod via gitlab-rails runner."""
    cmd = [
        "kubectl", "exec", "-n", "gitlab", "deployment/gitlab-omnibus",
        "--", "gitlab-rails", "runner", ruby_code
    ]
    code, out, err = run_command(cmd, description=description, check=False, capture_output=True)
    if code != 0:
        print_error(f"gitlab-rails runner failed:\n{err}")
        return None
    return out.strip() if out else ""


def check_gitlab_state_fast(root_pass: str):
    """Fast sub-second REST API pre-check inspecting itemized GitLab state without booting Rails."""
    _, root_token = get_gitlab_credentials()
    headers = {"PRIVATE-TOKEN": root_token}

    def api_get(path):
        url = f"http://localhost:8081/api/v4/{path}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except Exception:
            return None
        return None

    # Check Group
    group_data = api_get("groups/gitops-platform")
    group_exists = group_data is not None

    # Check Project
    project_data = api_get("projects/gitops-platform%2Fmanifests")
    project_exists = project_data is not None

    # Check Branch main
    main_branch = api_get("projects/gitops-platform%2Fmanifests/repository/branches/main") if project_exists else None
    main_exists = main_branch is not None

    # Check for Open Merge Requests on manifests project
    open_mrs = api_get("projects/gitops-platform%2Fmanifests/merge_requests?state=opened&target_branch=main") if project_exists else None
    mr_info = None
    if open_mrs and isinstance(open_mrs, list) and len(open_mrs) > 0:
        mr_info = open_mrs[0]
    else:
        # Fallback to latest MR if none open
        all_mrs = api_get("projects/gitops-platform%2Fmanifests/merge_requests?target_branch=main") if project_exists else None
        if all_mrs and isinstance(all_mrs, list) and len(all_mrs) > 0:
            mr_info = all_mrs[0]

    feature_exists = False
    if mr_info and "source_branch" in mr_info:
        src_b = urllib.parse.quote(mr_info["source_branch"], safe="")
        b_data = api_get(f"projects/gitops-platform%2Fmanifests/repository/branches/{src_b}")
        feature_exists = b_data is not None

    return {
        "group_exists": group_exists,
        "project_exists": project_exists,
        "main_branch_exists": main_exists,
        "feature_branch_name": mr_info.get("source_branch") if mr_info else None,
        "feature_branch_exists": feature_exists,
        "mr_iid": mr_info.get("iid") if mr_info else None,
        "mr_state": mr_info.get("state") if mr_info else None,
        "mr_web_url": f"http://localhost:8081/gitops-platform/manifests/-/merge_requests/{mr_info.get('iid')}" if mr_info else None,
    }


def main():
    # 1. Parse arguments first to get --env-file option
    args = parse_args()

    # 2. Resolve configuration via platform_adapter
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)
    config = get_config(env_file_path)

    # 3. Validate required environment variables (strictly from .env)
    validate_required_env_vars(
        config.gitlab_required_vars,
        env_file_path=env_file_path,
    )
    owner_email = config.admin_email
    gitlab_http_url = config.gitlab_http_url
    root_pass, _ = get_gitlab_credentials()


    print_header("Seed GitLab Manifests Repository (Merge Request Workflow)")

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

    # 5. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "GCP Project ID": project_id,
        "Project Owner": owner_email,
        "Target Project": "gitops-platform/manifests",
        "Manifest Source": "manifests/",
        "Active gcloud User": active_user,
        "Environment File": env_display,
    }
    if args.mr_approve:
        params_summary["MR Auto-Merge"] = "[bold yellow]YES (-m)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="GitLab Repository Seeding Parameters")


    repo_root = Path(__file__).resolve().parents[3]
    manifests_dir = repo_root / "manifests"

    if not manifests_dir.exists():
        print_error(f"Manifests directory not found at {manifests_dir}")
        sys.exit(1)

    # 6. Itemized Sub-Second Pre-Check BEFORE Execution Prompt
    print_header("GitLab Repository Pre-Check Status")
    pf_proc = None
    fast_state = None
    try:
        pf_cmd = ["kubectl", "port-forward", "-n", "gitlab", "svc/gitlab-omnibus", "8081:80"]
        pf_proc = subprocess.Popen(pf_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)  # Allow port forward to establish

        fast_state = check_gitlab_state_fast(root_pass)
        if fast_state:
            mr_state = fast_state.get("mr_state")
            feature_exists = fast_state.get("feature_branch_exists")

            group_icon = "[bold green]✓[/bold green]" if fast_state.get("group_exists") else "[bold yellow]✗[/bold yellow]"
            project_icon = "[bold green]✓[/bold green]" if fast_state.get("project_exists") else "[bold yellow]✗[/bold yellow]"
            main_icon = "[bold green]✓[/bold green]" if fast_state.get("main_branch_exists") else "[bold yellow]✗[/bold yellow]"

            print_info(f"  {group_icon} Group 'gitops-platform'           : {'Exists' if fast_state.get('group_exists') else 'Not Found'}")
            print_info(f"  {project_icon} Project 'gitops-platform/manifests': {'Exists' if fast_state.get('project_exists') else 'Not Found'}")
            print_info(f"  {main_icon} Branch 'main'                      : {'Exists' if fast_state.get('main_branch_exists') else 'Not Found'}")
            if fast_state.get("feature_branch_name"):
                feat_name = fast_state.get("feature_branch_name")
                feat_icon = "[bold green]✓[/bold green]" if fast_state.get("feature_branch_exists") else "[bold yellow]✗[/bold yellow]"
                print_info(f"  {feat_icon} Branch '{feat_name}' : {'Exists' if fast_state.get('feature_branch_exists') else 'Cleaned Up'}")

            mr_state = fast_state.get("mr_state")
            if mr_state:
                mr_icon = "[bold green]✓[/bold green]" if mr_state == "merged" else "[bold cyan]i[/bold cyan]"
                print_info(f"  {mr_icon} Merge Request #{fast_state.get('mr_iid')}                  : {mr_state.upper()}")
            else:
                print_info("  [bold yellow]✗[/bold yellow] Merge Request                    : Not Created")
    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait()

    # 7. Prompt user for confirmation before proceeding with full seeding
    if not confirm_action("Do you want to seed the 'gitops-platform/manifests' repository in GitLab?", auto_approve=args.auto_approve):
        sys.exit(0)

    if args.dry_run:
        print_info("[DRY-RUN] Would create 'gitops-platform/manifests' project, assign owner, and push MR.")
        sys.exit(0)

    # 8. Ensure Group & Project exist & set Owner/Maintainer permissions via python-gitlab SDK
    # Read public SSH key if available
    ssh_pub_key = ""
    oscar_pub_path = Path.home() / ".ssh" / "oscar-id_ed25519.pub"
    if oscar_pub_path.exists():
        ssh_pub_key = oscar_pub_path.read_text().strip()

    try:
        group = ensure_gitlab_group("gitops-platform")
        project = ensure_gitlab_project(group, "manifests", initialize_with_readme=True, default_branch="main")
        owner_user = ensure_gitlab_user(email=owner_email, username="oscar", name="Oscar Developer")
        ensure_group_member(group, owner_user, access_level=50)
        if ssh_pub_key:
            ensure_user_ssh_key(owner_user, title="oscar-workstation-key", key=ssh_pub_key)
    except Exception as exc:
        print_error(f"Failed to set up GitLab group/project and permissions:\n{exc}")
        sys.exit(1)

    print_info("[bold yellow][EXISTS/SKIP][/bold yellow] GitLab group 'gitops-platform' & project 'manifests' verified with Owner permissions.")

    # 9. Sync Git Repository & Create Merge Request branched from main
    def copy_manifest_files(working_dir: Path):
        shutil.copytree(manifests_dir, working_dir / "manifests", dirs_exist_ok=True)
        root_app_src = manifests_dir / "root-app.yaml"
        if root_app_src.exists():
            shutil.copy(root_app_src, working_dir / "root-app.yaml")

    pf_proc = None
    has_changes = False
    mr_url = None
    try:
        # Start transient port-forward to port 8081
        pf_cmd = ["kubectl", "port-forward", "-n", "gitlab", "svc/gitlab-omnibus", "8081:80"]
        pf_proc = subprocess.Popen(pf_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)  # Allow port forward to establish

        has_changes, _, mr_url = sync_git_repo_with_mr(
            project_path="gitops-platform/manifests",
            branch_prefix="feature/initial-manifests",
            commit_message="Add initial GitOps application manifests",
            mr_title="Initial GitOps Application Manifests",
            mr_description="Add initial Kubernetes manifests for ArgoCD App-of-Apps synchronization.",
            update_files_callback=copy_manifest_files,
            assignee=owner_email,
            root_pass=root_pass,
            target_branch="main",
            auto_approve=args.auto_approve,
            mr_approve=args.mr_approve,
            dry_run=args.dry_run,
        )
    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait()

    # 10. Display Completion Banner
    internal_url = "http://gitlab-omnibus.gitlab.svc.cluster.local/gitops-platform/manifests.git"
    print_seeding_completion_banner(internal_url)


if __name__ == "__main__":
    main()
