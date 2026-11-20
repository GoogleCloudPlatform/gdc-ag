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

"""GitLab repository and Merge Request helpers for application-workshop.

Operates strictly against an existing GitLab project repository provisioned
by gitops-workshop (provision_project.py). Does not provision GitLab groups,
users, or platform App-of-Apps manifests.
"""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from common import (
    RICH_AVAILABLE,
    confirm_action,
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    run_command,
)

if RICH_AVAILABLE:
    from rich import box
    from rich.panel import Panel


def get_gitlab_credentials() -> Tuple[str, str]:
    """Retrieve GitLab root password and root Personal Access Token from environment or cluster secret."""
    env_pass = os.environ.get("GITLAB_ROOT_PASSWORD", "").strip()
    env_token = os.environ.get("GITLAB_ROOT_TOKEN", "").strip()
    if env_pass and env_token:
        return env_pass, env_token

    code, out, _ = run_command(
        ["kubectl", "get", "secret", "gitlab-oauth-secret", "-n", "gitlab", "-o", "json"],
        check=False,
        capture_output=True,
    )
    secret_pass = ""
    secret_token = ""
    if code == 0 and out:
        try:
            secret_data = json.loads(out).get("data", {})
            if "root_password" in secret_data:
                secret_pass = base64.b64decode(secret_data["root_password"]).decode("utf-8").strip()
            if "root_token" in secret_data:
                secret_token = base64.b64decode(secret_data["root_token"]).decode("utf-8").strip()
        except Exception:
            pass

    if not secret_token:
        code, out, _ = run_command(
            [
                "kubectl",
                "get",
                "secret",
                "gitlab-root-pat",
                "-n",
                "gitlab",
                "-o",
                "jsonpath={.data.token}",
            ],
            check=False,
            capture_output=True,
        )
        if code == 0 and out:
            try:
                secret_token = base64.b64decode(out).decode("utf-8").strip()
            except Exception:
                pass

    final_pass = env_pass or secret_pass
    final_token = env_token or secret_token
    if not final_pass or not final_token:
        print_error(
            "Could not retrieve GitLab credentials from 'gitlab-oauth-secret' in namespace 'gitlab'. "
            "Ensure the GitOps platform from gitops-workshop is running."
        )
        sys.exit(1)
    return final_pass, final_token


def get_gitlab_client(url: Optional[str] = None, token: Optional[str] = None) -> Any:
    """Return an authenticated python-gitlab client instance."""
    import gitlab

    target_url = (url or os.environ.get("GITLAB_HTTP_URL") or "http://localhost:8081").strip().rstrip("/")
    if not token:
        _, token = get_gitlab_credentials()
    return gitlab.Gitlab(target_url, private_token=token, timeout=15)


def verify_existing_gitlab_repo(project_path: str, gitlab_http_url: Optional[str] = None) -> Any:
    """Verify that the target GitLab project repository already exists (created by gitops-workshop)."""
    gl = get_gitlab_client(gitlab_http_url)
    try:
        return gl.projects.get(project_path)
    except Exception:
        print_error(
            f"GitLab repository '{project_path}' was not found.\n"
            f"Please provision the project repository first using gitops-workshop:\n"
            f"  cd ../gitops-workshop && python3 scripts/project_provision/provision_project.py "
            f"-g {project_path.split('/')[0]} -p {project_path.split('/')[-1]} -a starter-app"
        )
        sys.exit(1)


def create_gitlab_mr(
    project_path: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str,
    assignee: Optional[str] = None,
    client: Optional[Any] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Create or return an open Merge Request in GitLab via python-gitlab SDK."""
    gl = client or get_gitlab_client()
    try:
        project = gl.projects.get(project_path)
        existing = project.mergerequests.list(
            state="opened", source_branch=source_branch, target_branch=target_branch
        )
        if existing:
            return existing[0].iid, existing[0].web_url

        mr_payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "remove_source_branch": False,
        }
        if assignee:
            uname = assignee.split("@")[0]
            users = gl.users.list(username=uname)
            if users:
                mr_payload["assignee_id"] = users[0].id

        mr = project.mergerequests.create(mr_payload)
        return mr.iid, mr.web_url
    except Exception as exc:
        print_warning(f"Failed to create Merge Request via GitLab API: {exc}")
        return None, None


def merge_gitlab_mr(
    project_path: str,
    mr_iid: int,
    client: Optional[Any] = None,
    timeout: int = 30,
) -> bool:
    """Merge a GitLab Merge Request via python-gitlab SDK, retrying while GitLab computes mergeability."""
    gl = client or get_gitlab_client()
    try:
        project = gl.projects.get(project_path)
        start = time.time()
        last_exc = None
        while time.time() - start < timeout:
            mr = project.mergerequests.get(mr_iid)
            if mr.state == "merged":
                return True
            try:
                mr.merge(should_remove_source_branch=False)
            except Exception as merge_exc:
                last_exc = merge_exc
                time.sleep(2)
                continue
            time.sleep(1)
            mr = project.mergerequests.get(mr_iid)
            if mr.state == "merged":
                return True
        if last_exc:
            print_warning(f"GitLab MR merge encountered: {last_exc}")
    except Exception as exc:
        print_warning(f"GitLab MR merge encountered: {exc}")
    return False


def sync_git_repo_with_mr(
    project_path: str,
    branch_prefix: str,
    commit_message: str,
    mr_title: str,
    mr_description: str,
    update_files_callback: Callable[[Path], None],
    assignee: Optional[str] = None,
    root_pass: Optional[str] = None,
    target_branch: str = "main",
    auto_approve: bool = False,
    mr_approve: bool = False,
    dry_run: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    """Clone an existing GitLab repository in a temp directory, apply manifest updates, push a branch, and open an MR."""
    if not root_pass:
        root_pass, _ = get_gitlab_credentials()

    gitlab_http = os.environ.get("GITLAB_HTTP_URL", "http://localhost:8081").strip().rstrip("/")
    parsed = urlparse(gitlab_http)
    host_netloc = parsed.netloc or "localhost:8081"
    scheme = parsed.scheme or "http"
    auth_repo_url = f"{scheme}://root:{root_pass}@{host_netloc}/{project_path}.git"
    branch_name = f"{branch_prefix}-{int(time.time())}"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        git_env = os.environ.copy()
        git_env["GIT_TERMINAL_PROMPT"] = "0"

        clone_res = subprocess.run(
            ["git", "clone", "--branch", target_branch, auth_repo_url, str(temp_path)],
            capture_output=True,
            text=True,
            env=git_env,
        )
        if clone_res.returncode != 0:
            print_error(
                f"Failed to clone '{project_path}' (branch '{target_branch}'). "
                f"Ensure the GitLab port-forward (8081:80) is active and the project was provisioned in gitops-workshop.\n"
                f"Details: {clone_res.stderr.strip()}"
            )
            sys.exit(1)

        subprocess.run(["git", "checkout", "-b", branch_name], cwd=temp_path, check=True, capture_output=True, env=git_env)
        subprocess.run(["git", "config", "user.name", "Application Operator"], cwd=temp_path, check=True, env=git_env)
        subprocess.run(["git", "config", "user.email", assignee or "operator@example.com"], cwd=temp_path, check=True, env=git_env)

        # Apply manifest integration / overwrites inside the cloned repository
        update_files_callback(temp_path)

        subprocess.run(["git", "add", "-A"], cwd=temp_path, check=True, env=git_env)
        status_res = subprocess.run(["git", "status", "--porcelain"], cwd=temp_path, capture_output=True, text=True, env=git_env)
        if not status_res.stdout.strip():
            print_info(f"[yellow]EXISTS/SKIP[/yellow] Manifests in '{project_path}' are already up to date on '{target_branch}'.")
            return False, branch_name, None

        if dry_run:
            print_info(f"[DRY-RUN] Changes staged in temporary clone of '{project_path}':")
            print(status_res.stdout.strip())
            print_info(f"[DRY-RUN] Would push branch '{branch_name}' and open Merge Request to '{target_branch}'.")
            return True, branch_name, f"{gitlab_http}/{project_path}/-/merge_requests/dry-run"

        subprocess.run(["git", "commit", "-m", commit_message], cwd=temp_path, check=True, capture_output=True, env=git_env)
        push_res = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=temp_path,
            capture_output=True,
            text=True,
            env=git_env,
        )
        if push_res.returncode != 0:
            print_error(f"Failed to push branch '{branch_name}' to '{project_path}': {push_res.stderr}")
            sys.exit(1)
        print_success(f"Pushed branch '[bold cyan]{branch_name}[/bold cyan]' to '{project_path}'.")

    if RICH_AVAILABLE and console:
        mr_summary = (
            f"[bold]GitLab Merge Request: [cyan]{project_path}[/cyan][/bold]\n"
            f"  - [bold]Source Branch[/bold] : [yellow]{branch_name}[/yellow]\n"
            f"  - [bold]Target Branch[/bold] : [green]{target_branch}[/green]\n"
            f"  - [bold]Summary[/bold]       : {mr_title}"
        )
        console.print()
        console.print(Panel(mr_summary, title="[bold magenta]Merge Request Action[/bold magenta]", box=box.ROUNDED, expand=False))

    if not confirm_action(f"Create Merge Request in '{project_path}'?", auto_approve=auto_approve):
        return True, branch_name, None

    mr_iid, mr_url = create_gitlab_mr(
        project_path=project_path,
        source_branch=branch_name,
        target_branch=target_branch,
        title=mr_title,
        description=mr_description,
        assignee=assignee,
    )
    if mr_url:
        print_success(f"Merge Request !{mr_iid} created in '{project_path}': [bold cyan]{mr_url}[/bold cyan]")
        if mr_approve and mr_iid is not None:
            print_info(f"Auto-merging Merge Request !{mr_iid} in '{project_path}' (-m / --mr-approve)...")
            if merge_gitlab_mr(project_path=project_path, mr_iid=mr_iid):
                print_success(f"Merge Request !{mr_iid} merged into '{target_branch}'.")
            else:
                print_warning(f"Merge Request !{mr_iid} could not be auto-merged; please merge manually at {mr_url}.")
    return True, branch_name, mr_url
