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

"""Install GitLab Omnibus server for gitops-workshop.

Idempotently deploys GitLab Omnibus CE single-pod deployment and waits for service readiness.
Supports Google Cloud Platform and Google Distributed Cloud Sandbox via decoupled platform providers.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from common import (
    RICH_AVAILABLE,
    check_prerequisites,
    confirm_action,
    ensure_deployed_manifests_dir,
    ensure_k8s_namespace,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_parameter_summary,
    print_success,
    print_warning,
    run_command,
)
from gitlab_utils import (
    get_gitlab_credentials,
)
from platform_adapter import (
    get_target_platform,
    get_prereqs_provider,
    get_project_provider,
    get_registry_provider,
    get_auth_provider,
)

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install GitLab Omnibus CE Server (GCP / GDC)"
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
        "--platform",
        choices=["gcp", "gdc"],
        help="Target platform override (gcp | gdc). Defaults to TARGET_PLATFORM in .env or gcp.",
    )
    return parser.parse_args()


def print_gitlab_next_steps(endpoint_url: str, root_pass: str, env_file: Optional[str] = None):
    """Display completion banner for GitLab installation."""
    print_success("Phase 5 GitLab Omnibus installed and initialized successfully.")
    env_flag = f" -e {env_file}" if env_file and env_file != ".env" else ""
    content = (
        f"1. Port-forward GitLab server (if not already running):\n"
        f"   [bold cyan]kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80[/bold cyan]\n"
        f"2. Open GitLab UI: [bold cyan]{endpoint_url}[/bold cyan]\n"
        f"   - Username: [bold cyan]root[/bold cyan]\n"
        f"   - Password: [bold cyan]{root_pass}[/bold cyan]\n"
        f"3. Proceed to Phase 6 (Initialize Repository & User):\n"
        f"   [bold cyan]python3 scripts/bootstrap/gitlab/setup_gitlab_repo.py{env_flag}[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print("1. kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80")
        print(f"2. Open UI: {endpoint_url} (root / {root_pass})")
        print(f"3. python3 scripts/bootstrap/gitlab/setup_gitlab_repo.py{env_flag}")


def seed_root_pat(root_token: str, dry_run: bool = False):
    """Seed the admin Personal Access Token (PAT) for root user via gitlab-rails."""
    if dry_run:
        print_info(f"[DRY-RUN] Would seed root Personal Access Token '{root_token}'.")
        return

    print_info("Seeding GitLab root Personal Access Token for API automation...")
    ruby_script = f"""
user = User.find_by_username('root')
token = user.personal_access_tokens.find_by(name: 'admin-bootstrap-token')
unless token
  token = user.personal_access_tokens.create!(
    name: 'admin-bootstrap-token',
    scopes: ['api', 'read_user', 'read_repository', 'write_repository', 'sudo', 'admin_mode'],
    expires_at: 1.year.from_now
  )
  token.set_token('{root_token}')
  token.save!
end
puts 'TOKEN_READY'
"""
    cmd = [
        "kubectl", "exec", "-n", "gitlab", "deployment/gitlab-omnibus",
        "--", "gitlab-rails", "runner", ruby_script
    ]
    code, out, err = run_command(cmd, description="Seeding GitLab root Personal Access Token", check=False, capture_output=True)
    if code == 0 and "TOKEN_READY" in (out or ""):
        print_success("GitLab root Personal Access Token seeded successfully.")
    else:
        print_error(f"Failed to seed root Personal Access Token. Details:\n{err or out}")

    # Store in Kubernetes secret as in-cluster backup
    secret_cmd = [
        "kubectl", "create", "secret", "generic", "gitlab-root-pat",
        "-n", "gitlab",
        f"--from-literal=token={root_token}",
        "--dry-run=client", "-o", "yaml"
    ]
    code, out, _ = run_command(secret_cmd, check=False, capture_output=True)
    if code == 0 and out:
        subprocess.run(["kubectl", "apply", "-n", "gitlab", "-f", "-"], input=out, text=True, capture_output=True)


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
    registry_provider = get_registry_provider(target_platform)
    auth_provider = get_auth_provider(target_platform)

    # 4. Resolve dynamic GitLab root credentials (or .env override)
    root_pass, root_token = get_gitlab_credentials()
    gitlab_image = registry_provider.resolve_image("gitlab-ce", "gitlab/gitlab-ce:16.8.0-ce.0")

    print_header(f"GitLab Omnibus Server Installation ({target_platform.upper()} Mode)")

    # 5. Prerequisite check
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 6. Determine Project & Active User
    active_identity = project_provider.get_active_identity() or "None"

    # 7. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "Namespace": "gitlab",
        "GitLab Image": gitlab_image,
        "Active User / Identity": active_identity,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="GitLab Installation Parameters")

    # 8. Prompt user for confirmation before proceeding
    if not confirm_action(f"Do you want to install GitLab Omnibus server on {target_platform.upper()}?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 9. Ensure namespace & Apply GitLab Manifests
    print_header(f"Phase 5: Deploying GitLab Omnibus Specs ({target_platform.upper()})")
    repo_root = Path(__file__).resolve().parents[3]
    deployed_dir = ensure_deployed_manifests_dir()
    manifest_dir = deployed_dir / "gitlab"
    kustomize_dir = registry_provider.prepare_gitlab_kustomization(manifest_dir)

    if not kustomize_dir.exists():
        print_error(f"Kustomize directory not found at {kustomize_dir}")
        sys.exit(1)

    ensure_k8s_namespace("gitlab", dry_run=args.dry_run)
    registry_provider.ensure_image_pull_secret("gitlab", dry_run=args.dry_run)

    # For GDC mode: ensure live oidc-token-proxy ClusterIP is populated in deployment-patch.yaml before applying
    if target_platform == "gdc":
        code, out, _ = run_command(
            ["kubectl", "get", "svc", "oidc-token-proxy", "-n", "argocd", "-o", "jsonpath={.spec.clusterIP}"],
            check=False,
            capture_output=True
        )
        if code == 0 and out.strip():
            proxy_ip = out.strip()
            auth_provider.sync_proxy_ip_manifests(proxy_ip, target_dir=deployed_dir)

    # Inject GitLab root credentials and auth
    client_id = os.environ.get("GCP_OIDC_CLIENT_ID") or os.environ.get("GDC_OIDC_CLIENT_ID")
    client_secret = os.environ.get("GCP_OIDC_CLIENT_SECRET") or os.environ.get("GDC_OIDC_CLIENT_SECRET")

    auth_provider.configure_gitlab_auth(
        root_pass=root_pass,
        root_token=root_token,
        client_id=client_id,
        client_secret=client_secret,
        dry_run=args.dry_run,
    )

    print_info(f"Applying GitLab Omnibus deployment specification ({kustomize_dir.relative_to(repo_root)})...")
    run_command(
        ["kubectl", "apply", "-k", str(kustomize_dir)],
        description=f"Applying {kustomize_dir.relative_to(repo_root)}",
        dry_run=args.dry_run
    )
    # Ensure image pull secrets are linked to all newly created ServiceAccounts (e.g. gitlab-omnibus)
    registry_provider.ensure_image_pull_secret("gitlab", dry_run=args.dry_run)

    # 10. Wait for GitLab deployment rollout
    if not args.dry_run:
        print_info("Waiting for GitLab Omnibus server deployment rollout (this may take a few minutes)...")
        run_command(
            ["kubectl", "rollout", "status", "deployment", "gitlab-omnibus", "-n", "gitlab", "--timeout=600s"],
            description="Waiting for gitlab-omnibus rollout",
            check=False
        )
        print_info("Waiting for GitLab internal services (puma, nginx) to initialize...")
        for i in range(1, 31):
            cmd = ["kubectl", "exec", "-n", "gitlab", "deployment/gitlab-omnibus", "-c", "gitlab-ce", "--", "gitlab-ctl", "status"]
            code, out, _ = run_command(cmd, description="Checking gitlab-ctl status", check=False, capture_output=True)
            if code == 0 and out and "run: puma" in out and "run: nginx" in out:
                print_success("GitLab services are online and ready!")
                break
            time.sleep(5)

    # 11. Seed Admin Personal Access Token (PAT) for python-gitlab SDK automation
    seed_root_pat(root_token, dry_run=args.dry_run)

    # 12. Display completion instructions banner
    gitlab_http_url = os.environ.get("GITLAB_HTTP_URL", "http://localhost:8081")
    print_gitlab_next_steps(gitlab_http_url, root_pass, env_file=args.env_file)


if __name__ == "__main__":
    main()
