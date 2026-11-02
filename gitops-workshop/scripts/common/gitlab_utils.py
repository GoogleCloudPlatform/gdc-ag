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

"""Shared GitLab Python SDK (python-gitlab) & GitOps automation utilities."""

import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Ensure venv site-packages are discovered if needed
for venv_path in [
    Path.cwd() / ".venv",
    Path(__file__).resolve().parents[2] / ".venv",
    Path.cwd() / "venv",
    Path.home() / ".local",
]:
    try:
        if venv_path.exists():
            for site_pkg in venv_path.glob("lib/python*/site-packages"):
                if site_pkg.exists() and str(site_pkg) not in sys.path:
                    sys.path.insert(0, str(site_pkg))
    except Exception:
        pass

# Ensure common directory is on sys.path
common_dir = str(Path(__file__).resolve().parent)
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

try:
    import gitlab
    import gitlab.exceptions
    GITLAB_SDK_AVAILABLE = True
except ImportError:
    gitlab = None
    GITLAB_SDK_AVAILABLE = False

from common import (
    RICH_AVAILABLE,
    confirm_action,
    console,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    run_command,
)

if RICH_AVAILABLE:
    from rich.panel import Panel


def get_gitlab_credentials() -> Tuple[str, str]:
    """Retrieve GitLab root password and admin PAT token.
    
    1. Checks GITLAB_ROOT_PASSWORD_OVERRIDE / GITLAB_ROOT_TOKEN_OVERRIDE in .env
    2. Reads from Kubernetes Secret gitlab/gitlab-oauth-secret if available
    3. If neither exists, dynamically generates random credentials on the fly.
    """
    token = os.environ.get("GITLAB_ROOT_TOKEN_OVERRIDE", "").strip()
    password = os.environ.get("GITLAB_ROOT_PASSWORD_OVERRIDE", "").strip()

    # If not overridden in .env, attempt reading from live Kubernetes Secret
    if not (token and password):
        try:
            cmd = ["kubectl", "get", "secret", "-n", "gitlab", "gitlab-oauth-secret", "-o", "json"]
            code, out, _ = run_command(cmd, description="Reading gitlab-oauth-secret", check=False, capture_output=True)
            if code == 0 and out:
                data = json.loads(out).get("data", {})
                if not password and "root_password" in data:
                    password = base64.b64decode(data["root_password"]).decode("utf-8")
                if not token and "root_token" in data:
                    token = base64.b64decode(data["root_token"]).decode("utf-8")
        except Exception:
            pass

    # Dynamic generation on the fly if still missing (e.g. initial generation)
    if not password:
        password = secrets.token_urlsafe(20)
    if not token:
        token = f"glpat-{secrets.token_urlsafe(20)}"

    return password, token


def get_gitlab_client(
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: int = 10,
) -> Any:
    """Return an authenticated GitLab API client using the python-gitlab SDK."""
    if not GITLAB_SDK_AVAILABLE or gitlab is None:
        print_error("Python 'python-gitlab' package is not installed. Please install it with 'pip install python-gitlab'.")
        sys.exit(1)
    target_url = (url or os.environ.get("GITLAB_HTTP_URL", "")).strip()
    if not target_url:
        print_error("Missing required environment variable: GITLAB_HTTP_URL. Please set in .env (e.g. GITLAB_HTTP_URL=http://localhost:8081).")
        sys.exit(1)
    if not token:
        _, token = get_gitlab_credentials()
    gl = gitlab.Gitlab(url=target_url, private_token=token, timeout=timeout)
    return gl


def run_rails_runner(ruby_code: str, description: str = "Running gitlab-rails command", retries: int = 3, delay: int = 3) -> Optional[str]:
    """Execute Ruby code inside the gitlab-omnibus pod via gitlab-rails runner (Day-0 bootstrap)."""
    cmd = [
        "kubectl", "exec", "-n", "gitlab", "deployment/gitlab-omnibus",
        "--", "gitlab-rails", "runner", ruby_code
    ]
    for attempt in range(1, retries + 1):
        code, out, err = run_command(cmd, description=description, check=False, capture_output=True)
        if code == 0:
            return out.strip() if out else ""
        if attempt < retries:
            print_warning(f"gitlab-rails runner attempt {attempt}/{retries} failed, retrying in {delay}s...")
            time.sleep(delay)
        else:
            print_error(f"gitlab-rails runner failed after {retries} attempts:\n{err}")
    return None


def ensure_gitlab_user(
    email: str,
    username: Optional[str] = None,
    name: Optional[str] = None,
    password: Optional[str] = None,
    is_admin: bool = False,
    client: Optional[Any] = None,
) -> Any:
    """Idempotently find or create a GitLab user via the python-gitlab SDK."""
    gl = client or get_gitlab_client()
    clean_email = email.strip().lower()
    clean_uname = (username or clean_email.split("@")[0]).strip().lower()
    clean_name = name or clean_uname.capitalize()

    # Search by username or email
    users = gl.users.list(username=clean_uname)
    if not users:
        users = gl.users.list(search=clean_email)
    if users:
        user = users[0]
        if is_admin and not getattr(user, "admin", False):
            try:
                user.admin = True
                user.save()
            except Exception:
                pass
        return user

    user_password = password or f"{secrets.token_urlsafe(24)}Aa1!"
    user = gl.users.create({
        "email": clean_email,
        "username": clean_uname,
        "name": clean_name,
        "password": user_password,
        "admin": is_admin,
        "skip_confirmation": True,
    })
    return user


def ensure_user_ssh_key(
    user_id_or_username: Union[int, str, Any],
    title: str,
    key: str,
    client: Optional[Any] = None,
) -> Any:
    """Idempotently add an SSH public key to a user via the python-gitlab SDK."""
    gl = client or get_gitlab_client()
    if isinstance(user_id_or_username, str) and not user_id_or_username.isdigit():
        users = gl.users.list(username=user_id_or_username)
        if not users:
            raise ValueError(f"User '{user_id_or_username}' not found.")
        user = users[0]
    elif isinstance(user_id_or_username, (int, str)):
        user = gl.users.get(int(user_id_or_username))
    else:
        user = user_id_or_username

    clean_key = key.strip()
    existing_keys = user.keys.list()
    for k in existing_keys:
        if k.key.strip() == clean_key or k.title == title:
            if k.key.strip() != clean_key:
                k.delete()
                break
            return k

    return user.keys.create({"title": title, "key": clean_key})


def ensure_gitlab_group(
    group_name: str,
    visibility: str = "internal",
    client: Optional[Any] = None,
) -> Any:
    """Idempotently find or create a GitLab group via the python-gitlab SDK."""
    gl = client or get_gitlab_client()
    clean_name = group_name.strip().lower()
    try:
        group = gl.groups.get(clean_name)
        return group
    except gitlab.exceptions.GitlabGetError:
        group = gl.groups.create({
            "name": clean_name,
            "path": clean_name,
            "visibility": visibility,
        })
        return group


def ensure_group_member(
    group_id_or_name: Union[int, str, Any],
    user_id_or_username: Union[int, str, Any],
    access_level: Union[int, str] = 50,
    client: Optional[Any] = None,
) -> Any:
    """Idempotently grant or update a user's access level in a group via python-gitlab SDK."""
    gl = client or get_gitlab_client()
    if isinstance(group_id_or_name, (int, str)):
        group = gl.groups.get(group_id_or_name)
    else:
        group = group_id_or_name

    if isinstance(user_id_or_username, str) and not user_id_or_username.isdigit():
        users = gl.users.list(username=user_id_or_username)
        if not users:
            raise ValueError(f"User '{user_id_or_username}' not found.")
        user = users[0]
    elif isinstance(user_id_or_username, (int, str)):
        user = gl.users.get(int(user_id_or_username))
    else:
        user = user_id_or_username

    if isinstance(access_level, str):
        level_map = {"guest": 10, "reporter": 20, "developer": 30, "maintainer": 40, "owner": 50}
        numeric_level = level_map.get(access_level.strip().lower(), 50)
    else:
        numeric_level = int(access_level)

    try:
        member = group.members.get(user.id)
        if member.access_level != numeric_level:
            member.access_level = numeric_level
            member.save()
        return member
    except gitlab.exceptions.GitlabGetError:
        member = group.members.create({
            "user_id": user.id,
            "access_level": numeric_level,
        })
        return member



def ensure_gitlab_project(
    group_id_or_name: Union[int, str, Any],
    project_name: str,
    initialize_with_readme: bool = True,
    default_branch: str = "main",
    visibility: str = "internal",
    client: Optional[Any] = None,
) -> Any:
    """Idempotently find or create a GitLab project with initialized main branch."""
    gl = client or get_gitlab_client()
    if isinstance(group_id_or_name, (int, str)):
        group = gl.groups.get(group_id_or_name)
    else:
        group = group_id_or_name

    clean_proj = project_name.strip().lower()
    full_path = f"{group.path}/{clean_proj}"

    try:
        project = gl.projects.get(full_path)
        return project
    except gitlab.exceptions.GitlabGetError:
        project = gl.projects.create({
            "name": clean_proj,
            "path": clean_proj,
            "namespace_id": group.id,
            "initialize_with_readme": initialize_with_readme,
            "default_branch": default_branch,
            "visibility": visibility,
        })
        return project


def check_gitlab_group_state(
    group_name: str,
    owner_email: str,
    client: Optional[Any] = None,
) -> Tuple[bool, bool, bool]:
    """Check group existence, owner access (50), and argocd-readonly access (20) in ~5ms."""
    gl = client or get_gitlab_client()
    clean_group = group_name.strip().lower()
    try:
        group = gl.groups.get(clean_group)
    except Exception:
        return False, False, False

    owner_access = False
    argocd_access = False
    owner_uname = owner_email.split("@")[0].lower() if owner_email else ""

    try:
        members = group.members.list(all=True)
        for m in members:
            uname = getattr(m, "username", "").lower()
            email = getattr(m, "email", "").lower()
            access = getattr(m, "access_level", 0)
            if (uname == owner_uname or email == owner_email.lower()) and access >= 50:
                owner_access = True
            if uname == "argocd-readonly" and access >= 20:
                argocd_access = True
    except Exception:
        pass

    return True, owner_access, argocd_access


def check_gitlab_group_exists(
    group_name: str,
    client: Optional[Any] = None,
) -> bool:
    """Check group existence via python-gitlab SDK in ~5ms."""
    gl = client or get_gitlab_client()
    try:
        gl.groups.get(group_name.strip().lower())
        return True
    except Exception:
        return False


def check_gitlab_file_exists(
    project_path: str,
    file_path: str,
    ref: str = "main",
    client: Optional[Any] = None,
) -> bool:
    """Check if a file exists in a GitLab repository branch via python-gitlab SDK."""
    gl = client or get_gitlab_client()
    try:
        project = gl.projects.get(project_path)
        project.files.get(file_path=file_path, ref=ref)
        return True
    except Exception:
        return False


def check_git_remote_branch(repo_url: str, branch: str = "main") -> Tuple[bool, bool]:
    """Check repository existence and branch status via git ls-remote in milliseconds."""
    code, out, _ = run_command(["git", "ls-remote", repo_url], check=False, capture_output=True)
    if code != 0:
        return False, False
    repo_exists = True
    branch_exists = f"refs/heads/{branch}" in (out or "") or "HEAD" in (out or "")
    return repo_exists, branch_exists


def get_gitlab_open_mr(
    project_path: str,
    source_branch: Optional[str] = None,
    client: Optional[Any] = None,
) -> Optional[Dict]:
    """Fetch open MR for a given project via python-gitlab SDK."""
    gl = client or get_gitlab_client()
    try:
        project = gl.projects.get(project_path)
        params = {"state": "opened"}
        if source_branch:
            params["source_branch"] = source_branch
        mrs = project.mergerequests.list(**params)
        if mrs:
            mr = mrs[0]
            return {"iid": mr.iid, "web_url": mr.web_url, "title": mr.title}
    except Exception:
        pass
    return None


def create_gitlab_mr(
    project_path: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str,
    assignee: Optional[Union[str, int, Any]] = None,
    client: Optional[Any] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Create Merge Request in GitLab via python-gitlab SDK assigned to the owner user."""
    gl = client or get_gitlab_client()

    # Resolve assignee user ID
    assignee_id = None
    if not assignee:
        try:
            import platform_adapter
            cfg = platform_adapter.get_config()
            target_assignee = cfg.admin_email or "oscar"
        except Exception:
            target_assignee = os.environ.get("PLATFORM_ADMIN") or os.environ.get("GCP_PROJECT_OWNER") or "oscar"
    else:
        target_assignee = assignee

    if isinstance(target_assignee, int):
        assignee_id = target_assignee
    elif hasattr(target_assignee, "id"):
        assignee_id = target_assignee.id
    elif isinstance(target_assignee, str) and target_assignee.strip():
        clean_target = target_assignee.strip().lower()
        uname = clean_target.split("@")[0]
        users = gl.users.list(username=uname)
        if not users and "@" in clean_target:
            users = gl.users.list(search=clean_target)
        if not users and clean_target != "oscar":
            users = gl.users.list(username="oscar")
        if users:
            assignee_id = users[0].id

    try:
        project = gl.projects.get(project_path)
        # Check if MR already exists
        existing_mrs = project.mergerequests.list(source_branch=source_branch, target_branch=target_branch, state="opened")
        if existing_mrs:
            mr = existing_mrs[0]
            if assignee_id and not getattr(mr, "assignee", None):
                try:
                    mr.assignee_id = assignee_id
                    mr.assignee_ids = [assignee_id]
                    mr.save()
                except Exception:
                    pass
            return mr.iid, mr.web_url

        mr_payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "remove_source_branch": False,
        }
        if assignee_id:
            mr_payload["assignee_id"] = assignee_id
            mr_payload["assignee_ids"] = [assignee_id]

        mr = project.mergerequests.create(mr_payload)
        return mr.iid, mr.web_url
    except Exception as exc:
        print_warning(f"python-gitlab SDK MR creation encountered: {exc}")

    # Fallback to Rails Runner (if SDK call fails)
    escaped_title = title.replace("'", "\\'")
    escaped_desc = description.replace("'", "\\'")
    assignee_code = ""
    if assignee_id:
        assignee_code = f"assignee_id: {assignee_id}, "
    elif target_assignee:
        clean_uname = str(target_assignee).split("@")[0]
        assignee_code = f"assignee_id: (User.find_by_username('{clean_uname}')&.id || User.find_by_username('oscar')&.id), "

    ruby_code = (
        f"user = User.find_by_username('root'); "
        f"project = Project.find_by_full_path('{project_path}'); "
        f"if project; "
        f"  existing_mr = project.merge_requests.find_by(source_branch: '{source_branch}', target_branch: '{target_branch}', state: 'opened'); "
        f"  mr = existing_mr || MergeRequests::CreateService.new(project: project, current_user: user, params: {{ "
        f"    title: '{escaped_title}', "
        f"    source_branch: '{source_branch}', "
        f"    target_branch: '{target_branch}', "
        f"    {assignee_code}"
        f"    description: '{escaped_desc}' "
        f"  }}).execute; "
        f"  puts \"MR_IID:#{{mr.iid}}\" if mr.persisted?; "
        f"end"
    )
    mr_res = run_rails_runner(ruby_code, description=f"Creating MR in GitLab for '{project_path}'")
    if mr_res and "MR_IID:" in mr_res:
        try:
            mr_iid = int(mr_res.split("MR_IID:")[1].strip().split()[0])
            return mr_iid, f"http://localhost:8081/{project_path}/-/merge_requests/{mr_iid}"
        except Exception:
            pass
    return None, None


def merge_gitlab_mr(
    project_path: str,
    mr_iid: int,
    client: Optional[Any] = None,
    timeout: int = 30,
) -> bool:
    """Idempotently merge a GitLab Merge Request via python-gitlab SDK (with Rails runner fallback) and wait for merged state."""
    gl = client or get_gitlab_client()
    try:
        project = gl.projects.get(project_path)
        mr = project.mergerequests.get(mr_iid)
        if mr.state == "merged":
            return True
        mr.merge(should_remove_source_branch=False)
        start = time.time()
        while time.time() - start < timeout:
            mr = project.mergerequests.get(mr_iid)
            if mr.state == "merged":
                return True
            time.sleep(1)
        return mr.state == "merged"
    except Exception as exc:
        print_warning(f"python-gitlab SDK MR merge encountered: {exc}")

    # Fallback to Rails Runner
    ruby_code = (
        f"user = User.find_by_username('root'); "
        f"project = Project.find_by_full_path('{project_path}'); "
        f"if project; "
        f"  mr = project.merge_requests.find_by(iid: {mr_iid}); "
        f"  if mr && mr.open?; "
        f"    MergeRequests::MergeService.new(project: project, current_user: user).execute(mr); "
        f"    puts \"MERGED_STATE:#{{mr.reload.state}}\"; "
        f"  elsif mr; "
        f"    puts \"MERGED_STATE:#{{mr.state}}\"; "
        f"  end; "
        f"end"
    )
    merge_res = run_rails_runner(ruby_code, description=f"Merging MR !{mr_iid} in '{project_path}'")
    if merge_res and "MERGED_STATE:merged" in merge_res:
        return True
    return False


def sync_git_repo_with_mr(
    project_path: str,
    branch_prefix: str,
    commit_message: str,
    mr_title: str,
    mr_description: str,
    update_files_callback: Callable[[Path], None],
    assignee: Optional[Union[str, int, Any]] = None,
    root_pass: Optional[str] = None,
    target_branch: str = "main",
    auto_approve: bool = False,
    mr_approve: bool = False,
    dry_run: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:

    """
    Standardized GitOps manifest workflow:
    1. Clone repository from target_branch (or init if fresh).
    2. Invoke callback to render / copy / modify files in the working tree.
    3. Check for diffs via 'git status --porcelain' (skip if no changes).
    4. Checkout fresh feature branch and push to GitLab.
    5. Prompt user to auto-create MR (or provide manual link).
    6. If mr_approve (-m) is enabled, auto-merge via GitLab API; otherwise prompt user to merge in GitLab.

    Returns:
        Tuple of (has_changes, feature_branch_name, mr_url)
    """
    active_root_pass = root_pass
    if not active_root_pass:
        active_root_pass, _ = get_gitlab_credentials()

    gitlab_http_url = os.environ.get("GITLAB_HTTP_URL", "").strip().rstrip("/")
    if not gitlab_http_url:
        print_error("Missing required environment variable: GITLAB_HTTP_URL. Please set in .env (e.g. GITLAB_HTTP_URL=http://localhost:8081).")
        sys.exit(1)

    if gitlab_http_url.startswith("http://"):
        host_port = gitlab_http_url[len("http://"):]
        git_remote_url = f"http://root:{active_root_pass}@{host_port}/{project_path}.git"
    elif gitlab_http_url.startswith("https://"):
        host_port = gitlab_http_url[len("https://"):]
        git_remote_url = f"https://root:{active_root_pass}@{host_port}/{project_path}.git"
    else:
        git_remote_url = f"http://root:{active_root_pass}@{gitlab_http_url}/{project_path}.git"
    feature_branch = f"{branch_prefix}-{int(time.time())}"
    repo_exists, branch_exists = check_git_remote_branch(git_remote_url, target_branch)

    with tempfile.TemporaryDirectory() as tmp_dir:
        working_dir = Path(tmp_dir)

        if branch_exists:
            clone_code, _, clone_err = run_command(
                ["git", "clone", "-b", target_branch, git_remote_url, str(working_dir)],
                description=f"Cloning '{project_path}' ({target_branch})",
                check=False,
                capture_output=True,
            )
            if clone_code != 0:
                print_error(f"Failed to clone '{project_path}':\n{clone_err}")
                sys.exit(1)
        else:
            working_dir.mkdir(parents=True, exist_ok=True)
            run_command(["git", "init"], cwd=working_dir, description=f"Initializing git repository with default branch '{target_branch}'")
            run_command(["git", "checkout", "-b", target_branch], cwd=working_dir, description=f"Switching to default branch '{target_branch}'")
            run_command(["git", "remote", "add", "origin", git_remote_url], cwd=working_dir, description="Adding origin remote")
            run_command(["git", "config", "user.name", "GitOps Administrator"], cwd=working_dir, description="Setting git user name")
            run_command(["git", "config", "user.email", "admin@workshop.local"], cwd=working_dir, description="Setting git user email")

            # Create initial baseline on target_branch and push to GitLab to establish default branch
            readme_file = working_dir / "README.md"
            if not readme_file.exists():
                readme_file.write_text(f"# {project_path.split('/')[-1].capitalize()}\n\nInitial repository baseline.\n")
            run_command(["git", "add", "README.md"], cwd=working_dir, description=f"Staging baseline for '{target_branch}'")
            run_command(["git", "commit", "-m", "Initial commit"], cwd=working_dir, description=f"Creating baseline commit on '{target_branch}'")
            run_command(
                ["git", "push", "-u", "origin", target_branch, "--force"],
                cwd=working_dir,
                description=f"Establishing default branch '{target_branch}' in GitLab",
                check=False,
                capture_output=True,
            )

        # Execute callback to update/render files
        update_files_callback(working_dir)

        run_command(["git", "config", "user.name", "GitOps Administrator"], cwd=working_dir, description="Setting git user name")
        run_command(["git", "config", "user.email", "admin@workshop.local"], cwd=working_dir, description="Setting git user email")
        run_command(["git", "add", "-A"], cwd=working_dir, description="Staging manifest changes")

        # Check for diffs
        _, status_out, _ = run_command(["git", "status", "--porcelain"], cwd=working_dir, check=False, capture_output=True)
        if not status_out.strip():
            print_info(f"[yellow]EXISTS/SKIP[/yellow] Applied manifests for '{project_path}' resulted in no changes (already up to date on '{target_branch}').")
            return False, None, None

        if dry_run:
            print_info(f"[DRY-RUN] Detected manifest diffs to commit in '{project_path}':\n{status_out.strip()}")
            print_info(f"[DRY-RUN] Would push branch '{feature_branch}' and open Merge Request to '{target_branch}'.")
            return True, feature_branch, None

        # Checkout fresh feature branch, commit, and push
        run_command(["git", "checkout", "-B", feature_branch], cwd=working_dir, description=f"Creating branch '{feature_branch}'")
        run_command(["git", "commit", "-m", commit_message], cwd=working_dir, description="Committing manifests")

        push_code, _, push_err = run_command(
            ["git", "push", "-u", "origin", feature_branch, "--force"],
            cwd=working_dir,
            description=f"Pushing branch '{feature_branch}' to GitLab",
            check=False,
            capture_output=True,
        )
        if push_code != 0:
            print_error(f"Failed to push branch '{feature_branch}' to '{project_path}':\n{push_err}")
            sys.exit(1)
        print_success(f"Pushed branch '{feature_branch}' to '{project_path}'.")

    # Display Merge Request Action Box
    mr_box = (
        f"[bold yellow]GitLab Merge Request Required: [/bold yellow][bold cyan]{project_path}[/bold cyan]\n"
        f"  - Source Branch : [bold cyan]{feature_branch}[/bold cyan]\n"
        f"  - Target Branch : [bold cyan]{target_branch}[/bold cyan]\n"
        f"  - Summary       : {mr_title}"
    )
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(mr_box, title="[bold cyan]Merge Request Action[/bold cyan]", expand=False))
    else:
        print(f"\n=== Merge Request Action: {project_path} ===")
        print(f"  Source Branch: {feature_branch}")
        print(f"  Target Branch: {target_branch}")
        print(f"  Summary      : {mr_title}\n")

    # Automatically create Merge Request via GitLab API
    mr_iid, mr_url = create_gitlab_mr(
        project_path=project_path,
        source_branch=feature_branch,
        target_branch=target_branch,
        title=mr_title,
        description=mr_description,
        assignee=assignee,
    )

    if mr_iid and mr_url:
        print_success(f"Merge Request !{mr_iid} created successfully in '{project_path}'!")
        print_info(f"MR Link: [bold cyan]{mr_url}[/bold cyan]")
    else:
        mr_url = f"http://localhost:8081/{project_path}/-/merge_requests/new?merge_request%5Bsource_branch%5D={feature_branch}&merge_request%5Btarget_branch%5D={target_branch}"
        print_warning(f"Could not auto-create MR via API. Please create the Merge Request manually at:\n   [bold cyan]{mr_url}[/bold cyan]")

    # Auto-merge if mr_approve (-m) is requested, otherwise prompt
    if mr_approve and mr_iid:
        print_info(f"Auto-merging Merge Request !{mr_iid} in '{project_path}' via GitLab API (-m / --mr-approve)...")
        if merge_gitlab_mr(project_path, mr_iid):
            print_success(f"Merge Request !{mr_iid} successfully merged into '{target_branch}'.")
        else:
            print_warning(f"Merge Request !{mr_iid} could not be automatically merged via API. Please merge it manually.")
    else:
        if not confirm_action(
            f"Have you merged the Merge Request for '{feature_branch}' into '{target_branch}' in GitLab?",
            auto_approve=False,
        ):
            print_warning(f"Please merge the Merge Request for '{project_path}' in GitLab before synchronizing in ArgoCD.")

    return True, feature_branch, mr_url
