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

"""Configure ArgoCD Read-Only SSH Authentication to GitLab Omnibus.

Creates a dedicated read-only service account ('argocd-readonly') in GitLab,
assigns REPORTER access to group 'gitops-platform', generates/reuses an ED25519 SSH keypair,
attaches the public SSH key to GitLab, registers the private SSH key as an ArgoCD repository secret,
and manages GitLab SSH host keys in ArgoCD known_hosts ConfigMap.

Strictly idempotent & self-healing:
- Diagnoses host key drift and recreated GitLab instances during pre-check.
- Supports --overwrite / --force to re-synchronize credentials, replace stale host keys,
  and restart ArgoCD repo-server/controller pods to flush cached commit refs.
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
from typing import Any, Dict, List, Optional, Tuple
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

from gitlab_utils import (  # noqa: E402
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
        description="Configure ArgoCD Read-Only SSH Authentication to GitLab"
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env configuration file (relative to current execution directory). Default: .env",
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="Force re-synchronize credentials, replace stale host keys in known_hosts, and restart ArgoCD components.",
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


def print_auth_completion_banner(repo_ssh_url: str):
    """Display completion banner for ArgoCD GitLab SSH authentication setup."""
    print_success("ArgoCD read-only SSH authentication to GitLab configured successfully.")
    content = (
        f"1. SSH Host Pattern: [bold cyan]{repo_ssh_url}[/bold cyan]\n"
        f"2. Service User: [bold cyan]argocd-readonly[/bold cyan] (Reporter on gitops-platform)\n"
        f"3. Proceed to Phase 5B (Enable App-of-Apps GitOps):\n"
        f"   [bold cyan]python3 scripts/bootstrap/gitops/enable_gitops.py[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(f"1. SSH Host Pattern: {repo_ssh_url}")
        print("2. python3 scripts/bootstrap/gitops/enable_gitops.py")



def run_rails_runner(ruby_code: str, description: str = "Running gitlab-rails command", retries: int = 5, delay: int = 5):
    """Execute Ruby code inside the gitlab-omnibus pod via gitlab-rails runner with retries."""
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


def get_live_gitlab_host_key():
    """Retrieve the current ED25519 host key from the active GitLab pod."""
    # Attempt 1: ssh-keyscan from repo-server pod
    keyscan_cmd = [
        "kubectl", "exec", "-n", "argocd", "deployment/argocd-repo-server",
        "--", "ssh-keyscan", "-t", "ed25519", "gitlab-omnibus.gitlab.svc.cluster.local"
    ]
    code, out, _ = run_command(keyscan_cmd, description="Scanning live GitLab ED25519 host key", check=False, capture_output=True)
    if code == 0 and out:
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "ssh-ed25519" in line:
                return line

    # Attempt 2: Read host public key directly from gitlab pod
    read_key_cmd = [
        "kubectl", "exec", "-n", "gitlab", "deployment/gitlab-omnibus",
        "--", "cat", "/etc/ssh/ssh_host_ed25519_key.pub"
    ]
    code, out, _ = run_command(read_key_cmd, description="Reading GitLab host key from pod", check=False, capture_output=True)
    if code == 0 and out and "ssh-ed25519" in out:
        pub_parts = out.strip().split()
        if len(pub_parts) >= 2:
            return f"gitlab-omnibus.gitlab.svc.cluster.local {pub_parts[0]} {pub_parts[1]}"

    return None


def get_registered_host_key():
    """Retrieve the registered host key entry for gitlab-omnibus from argocd-ssh-known-hosts-cm."""
    get_cm_cmd = ["kubectl", "get", "cm", "-n", "argocd", "argocd-ssh-known-hosts-cm", "-o", "json"]
    code, cm_json, _ = run_command(get_cm_cmd, description="Reading argocd-ssh-known-hosts-cm", check=False, capture_output=True)
    if code == 0 and cm_json:
        try:
            data = json.loads(cm_json)
            known_hosts = data.get("data", {}).get("ssh_known_hosts", "")
            for line in known_hosts.splitlines():
                line = line.strip()
                if line.startswith("gitlab-omnibus.gitlab.svc.cluster.local") and "ssh-ed25519" in line:
                    return line
        except Exception:
            return None
    return None


def get_existing_argocd_ssh_key():
    """Extract existing private key from ArgoCD Secret 'creds-gitlab-ssh' if it exists."""
    cmd = [
        "kubectl", "get", "secret", "-n", "argocd", "creds-gitlab-ssh",
        "-o", "jsonpath={.data.sshPrivateKey}"
    ]
    code, out, _ = run_command(cmd, description="Checking for existing ArgoCD SSH secret", check=False, capture_output=True)
    if code == 0 and out.strip():
        try:
            priv_key = base64.b64decode(out.strip()).decode()
            return priv_key
        except Exception:
            return None
    return None


def test_repo_server_ssh_probe():
    """Test live Git SSH connection from argocd-repo-server to GitLab manifests repository."""
    priv_key = get_existing_argocd_ssh_key()
    if priv_key:
        with tempfile.NamedTemporaryFile("w", suffix=".key", delete=False) as tf:
            tf.write(priv_key)
            temp_key_path = tf.name
        try:
            os.chmod(temp_key_path, 0o600)
            probe_cmd = (
                "cat > /tmp/id_argocd_test && chmod 600 /tmp/id_argocd_test && "
                "GIT_SSH_COMMAND='ssh -i /tmp/id_argocd_test' "
                "git ls-remote git@gitlab-omnibus.gitlab.svc.cluster.local:gitops-platform/manifests.git HEAD; "
                "rm -f /tmp/id_argocd_test"
            )
            with open(temp_key_path, "r") as f:
                res = subprocess.run(
                    ["kubectl", "exec", "-i", "-n", "argocd", "deployment/argocd-repo-server", "--", "/bin/sh", "-c", probe_cmd],
                    stdin=f,
                    capture_output=True,
                    text=True
                )
            return res.returncode == 0 and ("refs/heads/main" in res.stdout or "HEAD" in res.stdout or len(res.stdout.strip()) > 0)
        finally:
            if os.path.exists(temp_key_path):
                os.remove(temp_key_path)
    else:
        cmd = [
            "kubectl", "exec", "-n", "argocd", "deployment/argocd-repo-server",
            "--", "git", "ls-remote", "git@gitlab-omnibus.gitlab.svc.cluster.local:gitops-platform/manifests.git", "HEAD"
        ]
        code, out, _ = run_command(cmd, description="Testing live Git SSH connectivity from repo-server", check=False, capture_output=True)
        return code == 0 and ("refs/heads/main" in out or "HEAD" in out or len(out.strip()) > 0)


def check_auth_state_fast():
    """Fast inspection of ArgoCD Secret, GitLab Service Account, Host Key, and live probe."""
    state = {
        "secret_exists": False,
        "user_exists": False,
        "group_access": False,
        "key_attached": False,
        "live_host_key": None,
        "registered_host_key": None,
        "host_key_matched": False,
        "ssh_probe_success": False,
    }

    # 1. Check ArgoCD Secret
    cmd_secret = ["kubectl", "get", "secret", "-n", "argocd", "creds-gitlab-ssh"]
    code, _, _ = run_command(cmd_secret, description="Checking ArgoCD secret", check=False, capture_output=True)
    if code == 0:
        state["secret_exists"] = True

    # 2. Check service user, group membership, and SSH key via python-gitlab SDK
    try:
        gl = get_gitlab_client()
        users = gl.users.list(username="argocd-readonly")
        if users:
            u = users[0]
            state["user_exists"] = True
            state["key_attached"] = any(k.title == "ArgoCD Read-Only Key" for k in u.keys.list())
            try:
                g = gl.groups.get("gitops-platform")
                state["group_access"] = any(m.username == "argocd-readonly" for m in g.members.list(all=True))
            except Exception:
                pass
    except Exception:
        pass

    # 3. Host Key verification
    live_key = get_live_gitlab_host_key()
    registered_key = get_registered_host_key()
    state["live_host_key"] = live_key
    state["registered_host_key"] = registered_key

    if live_key and registered_key:
        live_parts = live_key.split()
        reg_parts = registered_key.split()
        if len(live_parts) >= 3 and len(reg_parts) >= 3:
            state["host_key_matched"] = (live_parts[1] == reg_parts[1] and live_parts[2] == reg_parts[2])
        elif len(live_parts) >= 2 and len(reg_parts) >= 2:
            state["host_key_matched"] = (live_parts[0] == reg_parts[0] and live_parts[1] == reg_parts[1])

    # 4. Live Connection Probe
    if state["secret_exists"] and state["user_exists"] and state["host_key_matched"]:
        state["ssh_probe_success"] = test_repo_server_ssh_probe()

    return state




def derive_public_key(priv_key_content: str):
    """Derive OpenSSH public key from private key string."""
    with tempfile.NamedTemporaryFile("w", suffix=".key", delete=False) as tf:
        tf.write(priv_key_content)
        temp_key_path = tf.name
    try:
        os.chmod(temp_key_path, 0o600)
        res = subprocess.run(["ssh-keygen", "-y", "-f", temp_key_path], capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
    finally:
        if os.path.exists(temp_key_path):
            os.remove(temp_key_path)
    return None


def update_known_hosts_configmap(live_host_key: str, root_pass: Optional[str] = None, auto_approve: bool = False, mr_approve: bool = False):
    """Replace any existing host keys for gitlab-omnibus in deployed manifest, apply to cluster, and push to GitLab."""
    if not root_pass:
        root_pass, _ = get_gitlab_credentials()

    deployed_dir = ensure_deployed_manifests_dir()

    # 1. Update known_hosts in the deployed manifests working directory
    cm_file = deployed_dir / "argocd" / "base" / "argocd-ssh-known-hosts-cm.yaml"
    if not cm_file.exists():
        cm_file = deployed_dir / "argocd" / "argocd-ssh-known-hosts-cm.yaml"

    if cm_file.exists():
        try:
            content = cm_file.read_text()
            filtered_lines = [
                line for line in content.splitlines()
                if not line.strip().startswith("gitlab-omnibus.gitlab.svc.cluster.local")
            ]
            filtered_lines.append(f"    {live_host_key.strip()}")
            cm_file.write_text("\n".join(filtered_lines) + "\n")
            print_info(f"Updated known_hosts in deployed manifest: {cm_file.name}")
        except Exception as e:
            print_warning(f"Could not update known_hosts in deployed copy: {e}")

    # 2. Apply the updated manifest directly to Kubernetes (declarative, no kubectl patch)
    if cm_file.exists():
        code, out, err = run_command(
            ["kubectl", "apply", "-n", "argocd", "-f", str(cm_file)],
            description="Applying updated argocd-ssh-known-hosts-cm manifest",
            check=False, capture_output=True
        )
        if code != 0:
            print_error(f"Failed to apply argocd-ssh-known-hosts-cm manifest: {err}")
            return False
        print_success("Applied active GitLab SSH host key to ArgoCD known_hosts ConfigMap from manifest!")

    # 3. Push updated deployed manifests to GitLab gitops-platform/manifests via feature branch and MR
    if root_pass:
        def update_manifest_files(working_dir: Path):
            shutil.copytree(deployed_dir, working_dir / "manifests", dirs_exist_ok=True)
            root_app_src = deployed_dir / "root-app.yaml"
            if root_app_src.exists():
                shutil.copy(root_app_src, working_dir / "root-app.yaml")

            # Adjust application paths based on target platform (GDC vs GCP)
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

        sync_git_repo_with_mr(
            project_path="gitops-platform/manifests",
            branch_prefix="feature/update-known-hosts",
            commit_message="Update declarative GitOps SSH known_hosts configuration",
            mr_title="Update Declarative SSH Known Hosts",
            mr_description="Updates `argocd-ssh-known-hosts-cm` with active GitLab SSH host key.",
            update_files_callback=update_manifest_files,
            root_pass=root_pass,
            target_branch="main",
            auto_approve=auto_approve,
            mr_approve=mr_approve,
        )

    return True


def restart_argocd_pods():
    """Restart ArgoCD repo-server and application-controller to reload known_hosts and flush caches."""
    print_info("Restarting ArgoCD repo-server and application-controller to flush git/commit caches...")
    run_command(
        ["kubectl", "rollout", "restart", "deployment/argocd-repo-server", "deployment/argocd-application-controller", "-n", "argocd"],
        description="Restarting ArgoCD repo-server and application-controller",
        check=False
    )
    print_info("Waiting for argocd-repo-server rollout...")
    run_command(
        ["kubectl", "rollout", "status", "deployment/argocd-repo-server", "-n", "argocd", "--timeout=120s"],
        description="Waiting for argocd-repo-server rollout",
        check=False
    )


def trigger_hard_refresh():
    """Annotate ArgoCD root application to trigger an immediate hard refresh."""
    print_info("Triggering hard refresh on ArgoCD applications...")
    run_command(
        ["kubectl", "annotate", "application", "root-app", "-n", "argocd", "argocd.argoproj.io/refresh=hard", "--overwrite"],
        description="Triggering hard refresh on root-app",
        check=False
    )


def main():
    # 1. Parse arguments first to get --env-file option
    args = parse_args()

    # 2. Resolve .env file relative to Current Working Directory (CWD)
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 3. Validate required environment variables (strictly from .env)
    env_config = validate_required_env_vars(
        ["GITLAB_HTTP_URL"],
        env_file_path=env_file_path,
    )
    gitlab_http_url = env_config["GITLAB_HTTP_URL"]

    print_header("Configure ArgoCD Read-Only SSH Authentication to GitLab")

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

    ssh_base_url = "git@gitlab-omnibus.gitlab.svc.cluster.local"

    # 5. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "GCP Project ID": project_id,
        "Secret Name": "creds-gitlab-ssh (argocd)",
        "Service User": "argocd-readonly (Reporter)",
        "SSH Host Pattern": ssh_base_url,
        "Active gcloud User": active_user,
        "Environment File": env_display,
    }
    if args.overwrite:
        params_summary["Force Overwrite"] = "[bold yellow]YES[/bold yellow]"
    if args.mr_approve:
        params_summary["MR Auto-Merge"] = "[bold yellow]YES (-m)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="ArgoCD Read-Only SSH Auth Parameters")


    # 6. Itemized Pre-Check BEFORE Confirmation Prompt
    print_header("ArgoCD GitLab Auth Pre-Check Status")
    fast_state = check_auth_state_fast()

    secret_icon = "[bold green]✓[/bold green]" if fast_state.get("secret_exists") else "[bold yellow]✗[/bold yellow]"
    secret_status = "Exists (repo-creds)" if fast_state.get("secret_exists") else "Missing"

    user_icon = "[bold green]✓[/bold green]" if fast_state.get("user_exists") else "[bold yellow]✗[/bold yellow]"
    user_status = "Exists (argocd-readonly)" if fast_state.get("user_exists") else "Not Created"

    group_icon = "[bold green]✓[/bold green]" if fast_state.get("group_access") else "[bold yellow]✗[/bold yellow]"
    group_status = "Configured (Reporter)" if fast_state.get("group_access") else "Not Configured"

    key_icon = "[bold green]✓[/bold green]" if fast_state.get("key_attached") else "[bold yellow]✗[/bold yellow]"
    key_status = "Attached" if fast_state.get("key_attached") else "Not Attached"

    host_key_matched = fast_state.get("host_key_matched")
    host_icon = "[bold green]✓[/bold green]" if host_key_matched else "[bold red]✗[/bold red]"
    if host_key_matched:
        host_status = "Matched (Up to date)"
    elif fast_state.get("registered_host_key"):
        host_status = "Mismatch / Outdated (GitLab host key changed!)"
    else:
        host_status = "Not Registered"

    probe_ok = fast_state.get("ssh_probe_success")
    probe_icon = "[bold green]✓[/bold green]" if probe_ok else "[bold yellow]✗[/bold yellow]"
    probe_status = "Connected (git ls-remote verified)" if probe_ok else "Not Verified / Failed"

    print_info(f"  {secret_icon} ArgoCD Secret 'creds-gitlab-ssh'          : {secret_status}")
    print_info(f"  {user_icon} GitLab Service User 'argocd-readonly'       : {user_status}")
    print_info(f"  {group_icon} Group Access 'gitops-platform'              : {group_status}")
    print_info(f"  {key_icon} Public SSH Key attached in GitLab           : {key_status}")
    print_info(f"  {host_icon} GitLab SSH Host Key in ArgoCD             : {host_status}")
    print_info(f"  {probe_icon} Repo-Server Live SSH Connection Probe      : {probe_status}")

    # Check if fully healthy and no force overwrite requested
    is_fully_healthy = (
        fast_state.get("secret_exists") and
        fast_state.get("user_exists") and
        fast_state.get("group_access") and
        fast_state.get("key_attached") and
        host_key_matched and
        probe_ok
    )

    if is_fully_healthy and not args.overwrite:
        print_success("Pre-Check Complete: ArgoCD read-only SSH authentication to GitLab is already configured and verified!")
        print_auth_completion_banner(ssh_base_url)
        sys.exit(0)

    # 7. Diagnose drifted state and customize prompt
    has_drift = (
        (not host_key_matched and fast_state.get("registered_host_key")) or
        (not fast_state.get("user_exists") and fast_state.get("secret_exists")) or
        args.overwrite
    )

    if has_drift:
        print_warning("GitLab host key mismatch or credential drift detected (GitLab was likely re-installed).")
        prompt_text = "Do you want to re-synchronize SSH credentials, update known_hosts, and restart ArgoCD repo-server?"
    else:
        prompt_text = "Do you want to configure ArgoCD pattern-based read-only SSH authentication to GitLab?"

    if not confirm_action(prompt_text, auto_approve=args.auto_approve):
        sys.exit(0)

    if args.dry_run:
        print_info("[DRY-RUN] Would generate/reuse ED25519 SSH key, configure service user 'argocd-readonly', update known_hosts, and apply Secret.")
        sys.exit(0)

    # 8. Check for existing SSH key or generate new ED25519 SSH Keypair
    existing_priv_key = get_existing_argocd_ssh_key()
    pub_key_content = None

    if existing_priv_key:
        pub_key_content = derive_public_key(existing_priv_key)
        if pub_key_content:
            print_info("[yellow]EXISTS/SKIP[/yellow] Reusing existing SSH private key from ArgoCD Secret 'creds-gitlab-ssh'.")
            priv_key_content = existing_priv_key

    if not pub_key_content:
        print_info("Generating fresh runtime ED25519 SSH keypair...")
        with tempfile.TemporaryDirectory() as tmpdir:
            priv_key_path = os.path.join(tmpdir, "id_ed25519")
            pub_key_path = os.path.join(tmpdir, "id_ed25519.pub")

            keygen_res = subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-C", "argocd-readonly@gitops-platform", "-f", priv_key_path, "-N", ""],
                capture_output=True, text=True
            )
            if keygen_res.returncode != 0:
                print_error(f"Failed to generate SSH keypair:\n{keygen_res.stderr}")
                sys.exit(1)

            with open(priv_key_path, "r") as f:
                priv_key_content = f.read()
            with open(pub_key_path, "r") as f:
                pub_key_content = f.read().strip()

    # 9. Configure Read-Only Service Account & SSH Public Key in GitLab via python-gitlab SDK
    print_info("Checking and configuring service user 'argocd-readonly' and SSH key in GitLab...")
    try:
        user = ensure_gitlab_user(
            email="argocd-readonly@workshop.local",
            username="argocd-readonly",
            name="ArgoCD Read-Only Service Account",
        )
        print_success("Service user 'argocd-readonly' verified in GitLab.")

        ensure_group_member("gitops-platform", user, access_level=20)
        print_success("Assigned Reporter (Read-Only) permissions on group 'gitops-platform'.")

        ensure_user_ssh_key(user, title="ArgoCD Read-Only Key", key=pub_key_content)
        print_success("SSH Public Key verified in GitLab for 'argocd-readonly'.")
    except Exception as exc:
        print_error(f"Failed to configure service user 'argocd-readonly' in GitLab:\n{exc}")
        sys.exit(1)
        print_info("[yellow]EXISTS/SKIP[/yellow] SSH Public Key in GitLab is already up to date.")

    # 10. Apply ArgoCD SSH Repository Credential Secret (repo-creds) in Kubernetes
    print_info("Applying ArgoCD repo-creds template ('argocd' namespace)...")
    indented_priv_key = "\n".join(f"    {line}" for line in priv_key_content.splitlines())

    repo_secret_manifest = f"""apiVersion: v1
kind: Secret
metadata:
  name: creds-gitlab-ssh
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
type: Opaque
stringData:
  type: git
  url: {ssh_base_url}
  sshPrivateKey: |
{indented_priv_key}
  insecure: "true"
  insecureIgnoreHostKey: "true"
---
apiVersion: v1
kind: Secret
metadata:
  name: repo-gitlab-manifests
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repository
type: Opaque
stringData:
  type: git
  url: {ssh_base_url}:gitops-platform/manifests.git
  sshPrivateKey: |
{indented_priv_key}
  insecure: "true"
  insecureIgnoreHostKey: "true"
"""

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(repo_secret_manifest)
        temp_secret_path = tf.name

    try:
        code, out, _ = run_command(
            ["kubectl", "apply", "-f", temp_secret_path],
            description="Applying ArgoCD SSH repository secret",
            check=True, capture_output=True
        )
        if "unchanged" in out:
            print_info("[yellow]EXISTS/SKIP[/yellow] ArgoCD Secret 'creds-gitlab-ssh' is unchanged.")
        else:
            print_success("ArgoCD SSH Repository Credential Secret applied successfully!")
    finally:
        if os.path.exists(temp_secret_path):
            os.remove(temp_secret_path)

    # 11. Register / Replace GitLab SSH Host Key in ArgoCD Known Hosts ConfigMap
    print_info("Registering active GitLab SSH host key in ArgoCD known_hosts ConfigMap...")
    root_pass, _ = get_gitlab_credentials()
    live_host_key = fast_state.get("live_host_key") or get_live_gitlab_host_key()
    if live_host_key:
        if update_known_hosts_configmap(live_host_key, root_pass=root_pass, auto_approve=args.auto_approve, mr_approve=args.mr_approve):
            print_success("Active GitLab SSH host key registered in ArgoCD known_hosts ConfigMap!")
        else:
            print_error("Failed to update ArgoCD known_hosts ConfigMap.")
    else:
        print_warning("Could not retrieve live GitLab SSH host key. Skipping known_hosts update.")

    # 12. Restart ArgoCD Repo-Server & Controller Pods to load updated host keys & flush cache
    restart_argocd_pods()

    # 13. Trigger Hard Refresh on Applications
    trigger_hard_refresh()

    # 14. Verification Probe
    print_info("Verifying live Git SSH connectivity from ArgoCD repo-server...")
    if test_repo_server_ssh_probe():
        print_success("Live Git SSH connection probe succeeded!")
    else:
        print_warning("Live connection probe did not return expected branch refs yet. ArgoCD will sync on next poll.")

    # 15. Display Completion Banner
    print_auth_completion_banner(ssh_base_url)


if __name__ == "__main__":
    main()

