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

"""Initialize GitLab user, group, repository, and default main branch for gitops-workshop.

Provisions the GCP Project Owner user (Oscar), attaches their SSH key, creates group 'gitops-platform',
grants Owner access on the group, creates project 'gitops-platform/manifests', and initializes the 'main' branch.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
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
)

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Initialize GitLab User, Group, Project, and Default 'main' Branch"
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
    return parser.parse_args()


def check_repo_state_fast(root_pass: str):
    """Fast check inspecting group, project, and main branch status via python-gitlab SDK."""
    group_exists = False
    project_exists = False
    main_branch_exists = False
    try:
        gl = get_gitlab_client()
        try:
            gl.groups.get("gitops-platform")
            group_exists = True
        except Exception:
            pass

        try:
            project = gl.projects.get("gitops-platform/manifests")
            project_exists = True
            try:
                project.branches.get("main")
                main_branch_exists = True
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass

    return {
        "group_exists": group_exists,
        "project_exists": project_exists,
        "main_branch_exists": main_branch_exists,
    }


def main():
    # 1. Parse CLI arguments
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
    project_id = config.project_id or get_active_gcp_project(env_file_path) or "Unknown"
    active_user = config.admin_email or get_active_gcloud_user() or "None"


    print_header("Initialize GitLab User, Group & Repository")

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
        "Project Owner": owner_email,
        "GitLab Group / Project": "gitops-platform / manifests",
        "Default Branch": "main",
        "Active gcloud User": active_user,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="GitLab Setup Parameters")

    # 6. Check existing state
    print_header("GitLab Repository Pre-Check Status")
    pf_proc = None
    try:
        pf_cmd = ["kubectl", "port-forward", "-n", "gitlab", "svc/gitlab-omnibus", "8081:80"]
        pf_proc = subprocess.Popen(pf_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

        fast_state = check_repo_state_fast(root_pass)
        if fast_state:
            group_icon = "[bold green]✓[/bold green]" if fast_state.get("group_exists") else "[bold yellow]✗[/bold yellow]"
            project_icon = "[bold green]✓[/bold green]" if fast_state.get("project_exists") else "[bold yellow]✗[/bold yellow]"
            main_icon = "[bold green]✓[/bold green]" if fast_state.get("main_branch_exists") else "[bold yellow]✗[/bold yellow]"

            print_info(f"  {group_icon} Group 'gitops-platform'           : {'Exists' if fast_state.get('group_exists') else 'Not Found'}")
            print_info(f"  {project_icon} Project 'gitops-platform/manifests': {'Exists' if fast_state.get('project_exists') else 'Not Found'}")
            print_info(f"  {main_icon} Branch 'main'                      : {'Exists' if fast_state.get('main_branch_exists') else 'Not Found'}")

            if fast_state.get("group_exists") and fast_state.get("project_exists") and fast_state.get("main_branch_exists"):
                print_success("Pre-Check Complete: Group, project, and 'main' branch already exist!")
                sys.exit(0)
    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait()

    # 7. Prompt confirmation
    if not confirm_action("Do you want to initialize the GitLab user, group, and repository?", auto_approve=args.auto_approve):
        sys.exit(0)

    if args.dry_run:
        print_info("[DRY-RUN] Would create 'gitops-platform/manifests' project, assign owner, and initialize main branch.")
        sys.exit(0)

    # 8. Create user, group, project & set Owner permissions in GitLab via python-gitlab SDK
    ssh_pub_key = ""
    oscar_pub_path = Path.home() / ".ssh" / "oscar-id_ed25519.pub"
    if oscar_pub_path.exists():
        ssh_pub_key = oscar_pub_path.read_text().strip()

    target_platform = os.environ.get("TARGET_PLATFORM", "gcp").lower()
    if target_platform == "gdc":
        username = owner_email.split("@")[0]
        name = username.replace("-", " ").title()
    else:
        username = "oscar"
        name = "Oscar Admin"

    try:
        user = ensure_gitlab_user(email=owner_email, username=username, name=name, is_admin=True)
        if ssh_pub_key:
            ensure_user_ssh_key(user, title=f"{username}-workstation-key", key=ssh_pub_key)
        ensure_gitlab_group("gitops-platform")
        ensure_group_member("gitops-platform", user.id, access_level="Owner")
        ensure_gitlab_project("gitops-platform", "manifests", initialize_with_readme=False)
        print_success("GitLab user, group, and project verified.")
    except Exception as e:
        print_error(f"Failed to configure GitLab user/group/project: {e}")
        sys.exit(1)


    # 9. Initialize main branch if not exists
    pf_proc = None
    try:
        pf_cmd = ["kubectl", "port-forward", "-n", "gitlab", "svc/gitlab-omnibus", "8081:80"]
        pf_proc = subprocess.Popen(pf_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

        auth_repo_url = f"http://root:{root_pass}@localhost:8081/gitops-platform/manifests.git"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            git_env = os.environ.copy()
            git_env["GIT_TERMINAL_PROMPT"] = "0"
            ls_remote = subprocess.run(["git", "ls-remote", auth_repo_url], capture_output=True, text=True, env=git_env)
            if "refs/heads/main" not in ls_remote.stdout:
                subprocess.run(["git", "init"], cwd=temp_path, check=True, stdout=subprocess.DEVNULL, env=git_env)
                subprocess.run(["git", "checkout", "-b", "main"], cwd=temp_path, check=True, stdout=subprocess.DEVNULL, env=git_env)
                subprocess.run(["git", "config", "user.name", "GitOps Administrator"], cwd=temp_path, check=True, stdout=subprocess.DEVNULL, env=git_env)
                subprocess.run(["git", "config", "user.email", "admin@workshop.local"], cwd=temp_path, check=True, stdout=subprocess.DEVNULL, env=git_env)
                (temp_path / ".gitkeep").touch()
                subprocess.run(["git", "add", "."], cwd=temp_path, check=True, stdout=subprocess.DEVNULL, env=git_env)
                subprocess.run(["git", "commit", "-m", "Initial repository setup"], cwd=temp_path, capture_output=True, env=git_env)
                subprocess.run(["git", "push", auth_repo_url, "main"], cwd=temp_path, capture_output=True, text=True, env=git_env)
                print_success("Initialized empty default branch 'main'.")
    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait()

    # 10. Summary Banner
    print_success("GitLab user, group, and repository initialized successfully.")
    content = (
        f"1. Target Project: [bold cyan]gitops-platform/manifests[/bold cyan] (Default branch: [bold cyan]main[/bold cyan])\n"
        f"2. Proceed to Phase 4D (Create Manifests Merge Request):\n"
        f"   [bold cyan]python3 scripts/bootstrap/gitlab/create_manifest_mr.py[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print("1. Target Project: gitops-platform/manifests")
        print("2. python3 scripts/bootstrap/gitlab/create_manifest_mr.py")



if __name__ == "__main__":
    main()
