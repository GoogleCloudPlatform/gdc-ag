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

"""Install ArgoCD and configure authentication for gitops-workshop.

Idempotently applies ArgoCD K8s manifests, ConfigMaps, and authentication secrets.
Supports Google Cloud Platform (Google Cloud OAuth 2.0 / Dex) and Google Distributed Cloud (GDC / Native Admin).
"""

import argparse
import os
import sys
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
    validate_required_env_vars,
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
        description="Install ArgoCD & Configure Authentication"
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
    parser.add_argument(
        "--client-id",
        help="OAuth 2.0 / OIDC Client ID. Sourced from GCP_OIDC_CLIENT_ID / GDC_OIDC_CLIENT_ID in .env.",
    )
    parser.add_argument(
        "--client-secret",
        help="OAuth 2.0 / OIDC Client Secret. Sourced from GCP_OIDC_CLIENT_SECRET / GDC_OIDC_CLIENT_SECRET in .env.",
    )
    return parser.parse_args()


def print_argocd_next_steps(server_url: str, platform: str, client_id_configured: bool, env_file: Optional[str] = None):
    """Display completion banner for ArgoCD installation and auth setup."""
    phase_label = "Phase 4" if platform.lower() == "gdc" else "Phase 3"
    next_phase_label = "Phase 5" if platform.lower() == "gdc" else "Phase 4"
    print_success(f"{phase_label} ArgoCD installed and configured successfully on {platform.upper()}.")

    if platform.lower() == "gdc":
        login_hint = "Log in via '[bold cyan]GDC Fake OIDC Provider[/bold cyan]' (or admin)"
        pf_cmd = "kubectl port-forward -n argocd svc/argocd-server 8088:80"
    elif client_id_configured:
        login_hint = "Click '[bold cyan]Log in via Google[/bold cyan]'"
        pf_cmd = "kubectl port-forward -n argocd svc/argocd-server 8080:80"
    else:
        login_hint = "Log in as [bold cyan]admin[/bold cyan]"
        pf_cmd = "kubectl port-forward -n argocd svc/argocd-server 8080:80"

    env_flag = ""
    if env_file:
        env_str = str(env_file)
        if env_str not in [".env", str(Path.cwd() / ".env")]:
            env_flag = f" -e {env_str}"

    content = (
        f"1. Port-forward ArgoCD server (if not already running):\n"
        f"   [bold cyan]{pf_cmd}[/bold cyan]\n"
        f"2. Open ArgoCD UI: [bold cyan]{server_url}[/bold cyan]\n"
        f"3. {login_hint}.\n"
        f"4. Proceed to {next_phase_label} (Install GitLab Omnibus):\n"
        f"   [bold cyan]python3 scripts/bootstrap/gitlab/install_gitlab.py{env_flag}[/bold cyan]"
    )
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(f"1. {pf_cmd}")
        print(f"2. Open UI: {server_url}")
        print(f"3. python3 scripts/bootstrap/gitlab/install_gitlab.py{env_flag}")


def ensure_argocd_rbac_policy(
    base_dir: Path,
    repo_root: Path,
    admin_user: str,
    dry_run: bool = False,
) -> Path:
    """Ensure ArgoCD RBAC policy.csv exists with project owner mapped to role:admin.

    Generates policy.csv from policy.csv.example template if not present,
    and displays a rich explanatory panel detailing the RBAC role binding.
    """
    deployed_policy_csv = base_dir / "policy.csv"
    src_base_dir = repo_root / "manifests" / "argocd" / "base"
    src_policy_csv = src_base_dir / "policy.csv"
    src_example_csv = src_base_dir / "policy.csv.example"

    # If policy.csv already exists in deployed_dir or src_base_dir
    if deployed_policy_csv.exists() or src_policy_csv.exists():
        existing_file = deployed_policy_csv if deployed_policy_csv.exists() else src_policy_csv
        if not deployed_policy_csv.exists() and src_policy_csv.exists() and not dry_run:
            deployed_policy_csv.write_text(src_policy_csv.read_text())
        print_info(f"Using existing ArgoCD RBAC policy file: [bold cyan]{existing_file.relative_to(repo_root)}[/bold cyan]")
        return deployed_policy_csv

    # Content generation from example template or default definition
    header_content = (
        "# ArgoCD RBAC Policy Definitions\n"
        "# Format:\n"
        "# p, <role/user/group>, <resource>, <action>, <object>, <allow/deny>\n"
        "# g, <user/email/group>, <role>\n"
    )
    if src_example_csv.exists():
        lines = [line for line in src_example_csv.read_text().splitlines() if line.startswith("#")]
        if lines:
            header_content = "\n".join(lines) + "\n"

    policy_content = f"{header_content}\n# Admin Role Binding for Project Owner / Platform Admin\ng, {admin_user}, role:admin\n"

    if not dry_run:
        if src_base_dir.exists():
            src_policy_csv.write_text(policy_content)
        if base_dir.exists():
            deployed_policy_csv.write_text(policy_content)

    summary_text = (
        f"ArgoCD requires an RBAC policy definition file ([bold cyan]policy.csv[/bold cyan])\n"
        f"to assign permissions to users logging in via Google Cloud OAuth / OIDC.\n\n"
        f"  • [bold green]Action[/bold green]: Auto-created [bold]policy.csv[/bold] from template\n"
        f"  • [bold green]Admin Identity[/bold green]: [bold cyan]{admin_user}[/bold cyan]\n"
        f"  • [bold green]Role Mapping[/bold green]: [bold yellow]g, {admin_user}, role:admin[/bold yellow]\n"
        f"  • [bold green]Source Manifest[/bold green]: [bold]{src_policy_csv.relative_to(repo_root)}[/bold]\n"
        f"  • [bold green]Deployed Manifest[/bold green]: [bold]{deployed_policy_csv.relative_to(repo_root)}[/bold]\n\n"
        f"This policy grants full ArgoCD administrator privileges ([bold]role:admin[/bold]) to\n"
        f"[bold cyan]{admin_user}[/bold cyan] upon authenticating via SSO."
    )

    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(summary_text, title="[bold green]ArgoCD RBAC Setup[/bold green]", box=box.ROUNDED, expand=False))
        console.print()
    else:
        print_success(f"Generated policy.csv: bound '{admin_user}' to role:admin")

    return deployed_policy_csv


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

    # 4. Validate required environment variables
    env_config = validate_required_env_vars(
        ["GCP_PROJECT_OWNER", "ARGOCD_SERVER_URL"] if target_platform == "gcp" else ["ARGOCD_SERVER_URL"],
        env_file_path=env_file_path,
    )
    server_url = env_config.get("ARGOCD_SERVER_URL", "http://localhost:8080")

    # 5. Sourced OIDC secrets & validate pair consistency
    client_id = (args.client_id or os.environ.get("GCP_OIDC_CLIENT_ID") or os.environ.get("GDC_OIDC_CLIENT_ID") or "").strip()
    client_secret = (args.client_secret or os.environ.get("GCP_OIDC_CLIENT_SECRET") or os.environ.get("GDC_OIDC_CLIENT_SECRET") or "").strip()

    if bool(client_id) != bool(client_secret):
        print_error("Both Client ID and Client Secret must be set to enable OIDC, or both omitted for native auth.")
        sys.exit(1)

    print_header(f"ArgoCD Installation ({target_platform.upper()} Mode)")

    # 6. Prerequisite check
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 7. Determine Project & Active User
    active_identity = project_provider.get_active_identity() or "None"

    # 8. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "Namespace": "argocd",
        "Server URL": server_url,
        "Authentication Mode": "OIDC Configured" if client_id else "Native Admin Auth",
        "Active User / Identity": active_identity,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="ArgoCD Installation Parameters")

    # 9. Prompt user for confirmation before proceeding
    if not confirm_action(f"Do you want to install ArgoCD on {target_platform.upper()}?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 10. Apply ArgoCD Manifests
    phase_label = "Phase 4" if target_platform == "gdc" else "Phase 3"
    print_header(f"{phase_label}: Deploying ArgoCD Specifications ({target_platform.upper()})")
    repo_root = Path(__file__).resolve().parents[3]
    deployed_dir = ensure_deployed_manifests_dir()
    manifest_dir = deployed_dir / "argocd"
    base_dir = manifest_dir / "base" if (manifest_dir / "base").exists() else manifest_dir

    crd_manifest = base_dir / "crds.yaml"
    install_manifest = base_dir / "install.yaml"
    cm_manifest = base_dir / "argocd-cm.yaml"

    admin_user = (
        os.environ.get("GCP_PROJECT_OWNER")
        or os.environ.get("PLATFORM_ADMIN")
        or (active_identity if active_identity != "None" else "")
        or "user@example.com"
    ).strip()

    # Ensure policy.csv exists in base_dir and source manifests
    ensure_argocd_rbac_policy(base_dir, repo_root, admin_user, dry_run=args.dry_run)

    if not install_manifest.exists():
        print_error(f"Manifest not found at {install_manifest}")
        sys.exit(1)

    # Ensure argocd namespace exists
    ensure_k8s_namespace("argocd", dry_run=args.dry_run)

    # Ensure image pull secrets if required by platform
    registry_provider.ensure_image_pull_secret("argocd", dry_run=args.dry_run)

    # Apply Kustomize overlay or manifests
    kustomize_dir = registry_provider.prepare_argocd_kustomization(manifest_dir)
    kustomize_file = kustomize_dir / "kustomization.yaml"

    # For GDC mode: deploy oidc-token-proxy first, retrieve its ClusterIP, and update the deployed patch
    if target_platform == "gdc":
        proxy_manifest = kustomize_dir / "oidc-token-proxy.yaml"
        if proxy_manifest.exists():
            auth_provider.ensure_oidc_proxy_tls_secret(dry_run=args.dry_run)
            if not args.dry_run:
                run_command(
                    ["kubectl", "apply", "-f", str(proxy_manifest)],
                    description="Applying oidc-token-proxy specification",
                    check=False
                )
                code, out, _ = run_command(
                    ["kubectl", "get", "svc", "oidc-token-proxy", "-n", "argocd", "-o", "jsonpath={.spec.clusterIP}"],
                    check=False,
                    capture_output=True
                )
                if code == 0 and out.strip():
                    proxy_ip = out.strip()
                    auth_provider.sync_proxy_ip_manifests(proxy_ip, target_dir=deployed_dir)

    # Configure Authentication
    auth_provider.configure_argocd_auth(
        client_id=client_id,
        client_secret=client_secret,
        server_url=server_url,
        dry_run=args.dry_run
    )

    if kustomize_file.exists():
        print_info(f"Applying ArgoCD deployment specifications & Kustomize overlays ({kustomize_dir.relative_to(repo_root)})...")
        apply_cmd = ["kubectl", "apply", "-k", str(kustomize_dir)]
        if target_platform == "gdc":
            apply_cmd.extend(["--server-side", "--force-conflicts"])
        run_command(
            apply_cmd,
            description=f"Applying {kustomize_dir.relative_to(repo_root)} via Kustomize",
            dry_run=args.dry_run
        )
        # Ensure image pull secrets are linked to all newly created ServiceAccounts
        registry_provider.ensure_image_pull_secret("argocd", dry_run=args.dry_run)
    else:
        if crd_manifest.exists():
            print_info("Applying ArgoCD Custom Resource Definitions (CRDs)...")
            run_command(
                ["kubectl", "apply", "-f", str(crd_manifest)],
                description="Applying manifests/argocd/crds.yaml",
                dry_run=args.dry_run
            )

        print_info("Applying ArgoCD deployment specifications...")
        run_command(
            ["kubectl", "apply", "-n", "argocd", "-f", str(install_manifest)],
            description="Applying manifests/argocd/install.yaml",
            dry_run=args.dry_run
        )

        print_info("Applying ArgoCD ConfigMaps...")
        cmd_params_manifest = base_dir / "argocd-cmd-params-cm.yaml"

        run_command(
            ["kubectl", "apply", "-n", "argocd", "-f", str(cm_manifest)],
            description="Applying manifests/argocd/argocd-cm.yaml",
            dry_run=args.dry_run
        )
        if cmd_params_manifest.exists():
            run_command(
                ["kubectl", "apply", "-n", "argocd", "-f", str(cmd_params_manifest)],
                description="Applying manifests/argocd/argocd-cmd-params-cm.yaml",
                dry_run=args.dry_run
            )

    # 12. Restart ArgoCD components to pick up configuration
    if not args.dry_run:
        print_info("Restarting ArgoCD server and Dex server to apply configuration changes...")
        run_command(
            ["kubectl", "rollout", "restart", "deployment", "argocd-server", "-n", "argocd"],
            description="Restarting argocd-server",
            check=False
        )
        run_command(
            ["kubectl", "rollout", "restart", "deployment", "argocd-dex-server", "-n", "argocd"],
            description="Restarting argocd-dex-server",
            check=False
        )

    # 13. Display Next Steps
    print_argocd_next_steps(server_url, target_platform, bool(client_id), env_file=args.env_file)


if __name__ == "__main__":
    main()
