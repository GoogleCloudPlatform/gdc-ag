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

"""
Provision a new workload project in GitLab and onboard it to the ArgoCD GitOps platform.

Features:
- Takes Group Name, Project Name, and Group Owner as required inputs.
- Idempotently creates the GitLab group and project if they do not exist.
- Grants the specified Group Owner 'Owner' (50) access on the group.
- Grants the 'argocd-readonly' service account 'Reporter' (20) access.
- Seeds the project repo with a multi-app template (App-of-Apps) and initial nginx service.
- Adds the project root Application manifest to 'gitops-platform/manifests' via branch and Merge Request.
- Follows Rich CLI UX guidelines with parameter summary, pre-checks, and completion banner.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Ensure shared scripts/common directory is in python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

from common import (  # noqa: E402
    RICH_AVAILABLE,
    check_prerequisites,
    confirm_action,
    console,
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
from platform_adapter import (
    get_target_platform,
    get_prereqs_provider,
    get_project_provider,
    get_registry_provider,
    get_config,
)


from gitlab_utils import (  # noqa: E402
    check_git_remote_branch,
    check_gitlab_file_exists,
    check_gitlab_group_state,
    create_gitlab_mr,
    ensure_gitlab_group,
    ensure_gitlab_project,
    ensure_gitlab_user,
    ensure_group_member,
    get_gitlab_credentials,
    get_gitlab_open_mr,
    sync_git_repo_with_mr,
)

if RICH_AVAILABLE:
    from rich.panel import Panel


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Provision a new workload project in GitLab and onboard to ArgoCD GitOps."
    )
    parser.add_argument(
        "--group-name",
        "-g",
        type=str,
        required=True,
        help="GitLab group name for the project (required, e.g. workloads, drdc)",
    )
    parser.add_argument(
        "--project-name",
        "-p",
        type=str,
        required=True,
        help="Name of the project / repository in GitLab (required, e.g. research-a)",
    )
    parser.add_argument(
        "--app-name",
        "-a",
        dest="app_name",
        type=str,
        required=True,
        help="Name of the application / microservice to create within the project (required, e.g. frontend, payments)",
    )
    parser.add_argument(
        "--group-owner",
        "-o",
        type=str,
        default=None,
        help="Email of the group owner to be granted Owner permissions (required unless set in .env as GCP_PROJECT_OWNER)",
    )
    parser.add_argument(
        "--manifest-update",
        action="store_true",
        help="Only update/seed project manifests and platform integration without modifying GitLab user/group permissions",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve prompts without interactive confirmation",
    )
    parser.add_argument(
        "-m",
        "--mr-approve",
        action="store_true",
        help="Automatically approve and merge created GitLab Merge Requests via API",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying GitLab or Git repositories",
    )
    parser.add_argument(
        "-e",
        "--env-file",
        type=str,
        default=".env",
        help="Path to environment file (default: .env in current execution directory)",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Verify required prerequisites and exit",
    )
    return parser.parse_args()


def check_project_state_fast(group_name: str, project_name: str, app_name: str, owner_email: str, root_pass: Optional[str] = None):
    """Fast check inspecting group, members, project repo, branch, app manifests, and platform integration."""
    if not root_pass:
        root_pass, _ = get_gitlab_credentials()
    group_exists, owner_access, argocd_access = check_gitlab_group_state(group_name, owner_email)
    project_url = f"http://root:{root_pass}@localhost:8081/{group_name}/{project_name}.git"
    project_exists, main_branch_exists = check_git_remote_branch(project_url, "main")

    app_manifest_exists = check_gitlab_file_exists(f"{group_name}/{project_name}", f"manifests/{app_name}-app.yaml", ref="main")
    platform_app_exists = check_gitlab_file_exists("gitops-platform/manifests", f"manifests/apps/{project_name}.yaml", ref="main")
    open_mr = get_gitlab_open_mr("gitops-platform/manifests")

    return {
        "group_exists": group_exists,
        "project_exists": project_exists,
        "main_branch_exists": main_branch_exists,
        "owner_has_access": owner_access,
        "argocd_has_access": argocd_access,
        "app_manifest_exists": app_manifest_exists,
        "platform_app_exists": platform_app_exists,
        "open_mr": open_mr,
    }


def render_template_file(template_path: Path, output_path: Path, context: dict):
    """Render template file replacing placeholders."""
    content = template_path.read_text()
    for key, value in context.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)


def print_completion_banner(project_name: str, group_name: str, app_name: str, group_owner: str, p2_mr_url: Optional[str] = None, p3_mr_url: Optional[str] = None):
    """Display completion banner with instructions for workshop participant."""
    print_success(f"Project '{project_name}' (app: '{app_name}') provisioned successfully.")
    content_lines = []
    if p2_mr_url:
        content_lines.append(f"1. Workload MR: [bold cyan]{p2_mr_url}[/bold cyan]")
    if p3_mr_url:
        content_lines.append(f"2. Platform MR: [bold cyan]{p3_mr_url}[/bold cyan]")
    
    if p2_mr_url or p3_mr_url:
        content_lines.append("3. Review & merge open MRs in GitLab (http://localhost:8081).")
        content_lines.append(f"4. Sync in ArgoCD (http://localhost:8080):\n   [bold cyan]root-app[/bold cyan] -> [bold cyan]{project_name}-apps[/bold cyan] -> [bold cyan]{app_name}[/bold cyan]")
        content_lines.append(f"5. Access deployed microservice (Port-Forward):\n   [bold cyan]kubectl port-forward -n {app_name} svc/{app_name} 8082:80[/bold cyan]\n   Open: [bold cyan]http://localhost:8082[/bold cyan]")
    else:
        content_lines.append("1. All manifests merged on 'main'.")
        content_lines.append(f"2. Sync in ArgoCD (http://localhost:8080):\n   [bold cyan]root-app[/bold cyan] -> [bold cyan]{project_name}-apps[/bold cyan] -> [bold cyan]{app_name}[/bold cyan]")
        content_lines.append(f"3. Access deployed microservice (Port-Forward):\n   [bold cyan]kubectl port-forward -n {app_name} svc/{app_name} 8082:80[/bold cyan]\n   Open: [bold cyan]http://localhost:8082[/bold cyan]")

    content = "\n".join(content_lines)
    if RICH_AVAILABLE:
        from rich import box
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(content)



def main():
    # 1. Parse CLI arguments
    args = parse_args()
    project_name = args.project_name.strip().lower()
    group_name = args.group_name.strip().lower()
    app_name = args.app_name.strip().lower()
    app_image = "nginx:1.27-alpine"
    app_port = 80
    target_namespace = app_name
    repo_root = Path(__file__).resolve().parents[2]

    # 2. Resolve .env file relative to Current Working Directory (CWD)
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # Resolve platform, config & registry
    target_platform = get_target_platform(env_file_path)
    config = get_config(env_file_path, cli_overrides={"admin_email": args.group_owner})
    registry_provider = get_registry_provider(target_platform)
    app_image = registry_provider.resolve_image("nginx", "nginx:1.27-alpine")

    # 3. Validate required environment variables (strictly from .env or CLI)
    validate_required_env_vars(
        config.gitlab_required_vars,
        env_file_path=env_file_path,
        cli_overrides={config.gitlab_required_vars[0]: args.group_owner},
    )
    group_owner = config.admin_email
    gitlab_http_url = config.gitlab_http_url
    root_pass, _ = get_gitlab_credentials()

    print_header(f"Provision GitOps Project: '{project_name}' (App: '{app_name}')")

    # 4. Prerequisite check
    if not check_prerequisites(verbose=args.check_prereqs):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 5. Resolve environment parameters
    project_id = config.project_id or get_active_gcp_project(env_file_path) or "Unknown"
    active_user = config.admin_email or get_active_gcloud_user() or "None"
    repo_ssh_url = f"git@gitlab-omnibus.gitlab.svc.cluster.local:{group_name}/{project_name}.git"


    # 5. Display Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Platform / Project ID": f"{target_platform.upper()} / {project_id}",
        "Target Project": f"{group_name}/{project_name}",
        "Target Application": f"{app_name} (ns: {target_namespace}, port: {app_port})",
        "Group Owner": group_owner,
        "Active User / Identity": active_user,
        "Environment File": env_display,
    }
    if args.manifest_update:
        params_summary["Mode"] = "Manifests Only"
    if args.mr_approve:
        params_summary["MR Auto-Merge"] = "[bold yellow]YES (-m)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Project Provisioning Parameters")


    # 6. Itemized Pre-Check BEFORE Confirmation Prompt
    print_header("GitLab & GitOps State Pre-Check")
    precheck = check_project_state_fast(group_name, project_name, app_name, group_owner, root_pass=root_pass)

    proj_icon = "[✓]" if precheck["project_exists"] else "[✗]"
    proj_status = f"Exists ('{group_name}/{project_name}')" if precheck["project_exists"] else "Not Created (will create)"

    branch_icon = "[✓]" if precheck["main_branch_exists"] else "[✗]"
    branch_status = "Initialized with commits" if precheck["main_branch_exists"] else "Empty / Not Initialized"

    app_icon = "[✓]" if precheck["app_manifest_exists"] else "[✗]"
    app_status = f"Exists (manifests/{app_name}-app.yaml)" if precheck["app_manifest_exists"] else f"Not Configured (will create '{app_name}')"

    if precheck.get("platform_app_exists"):
        platform_icon = "[✓]"
        platform_status = f"Merged on 'main' (manifests/apps/{project_name}.yaml)"
    elif precheck.get("open_mr"):
        platform_icon = "[✓]"
        platform_status = f"Open Onboarding MR !{precheck['open_mr'].get('iid')}"
    else:
        platform_icon = "[✗]"
        platform_status = "Not Configured (will create MR)"

    if args.manifest_update:
        print_info(f"  {proj_icon} GitLab Project '{group_name}/{project_name}'    : {proj_status}")
        print_info(f"  {branch_icon} Default Branch 'main'                        : {branch_status}")
        print_info(f"  {app_icon} App '{app_name}' Manifests                      : {app_status}")
        print_info(f"  {platform_icon} Platform Manifest Integration             : {platform_status}")
    else:
        group_icon = "[✓]" if precheck["group_exists"] else "[✗]"
        group_status = f"Exists ('{group_name}')" if precheck["group_exists"] else "Not Created (will create)"

        owner_icon = "[✓]" if precheck["owner_has_access"] else "[✗]"
        owner_status = f"Owner access granted ('{group_owner}')" if precheck["owner_has_access"] else "Not Configured (will grant)"

        argocd_icon = "[✓]" if precheck["argocd_has_access"] else "[✗]"
        argocd_status = "Reporter access granted" if precheck["argocd_has_access"] else "Not Configured (will grant)"

        print_info(f"  {group_icon} GitLab Group '{group_name}'                    : {group_status}")
        print_info(f"  {owner_icon} Group Owner Access ('{group_owner}')          : {owner_status}")
        print_info(f"  {argocd_icon} Service User Access ('argocd-readonly')      : {argocd_status}")
        print_info(f"  {proj_icon} GitLab Project '{group_name}/{project_name}'    : {proj_status}")
        print_info(f"  {branch_icon} Default Branch 'main'                        : {branch_status}")
        print_info(f"  {app_icon} App '{app_name}' Manifests                      : {app_status}")
        print_info(f"  {platform_icon} Platform Onboarding Merge Request         : {platform_status}")

    # Prompt user confirmation
    if not confirm_action(f"Proceed with provisioning project '{project_name}' (App: '{app_name}') and onboarding to GitOps?", auto_approve=args.auto_approve):
        print_warning("Project provisioning aborted by user.")
        sys.exit(0)

    if args.dry_run:
        print_info("[yellow]EXISTS/SKIP[/yellow] Running in DRY-RUN mode. No changes will be applied.")
        print_success("Dry-run validation completed successfully.")
        sys.exit(0)

    # 7. Phase 1: Ensure GitLab Group, Project, and Permissions via python-gitlab SDK
    print_header("Phase 1: Configure GitLab Group, Project & Permissions")
    if args.manifest_update:
        print_info("[yellow]EXISTS/SKIP[/yellow] Skipping Phase 1 (GitLab group/user permissions) in --manifest-update mode.")
    else:
        # 1. Ensure GitLab Group exists
        group = ensure_gitlab_group(group_name)

        # 2. Ensure Group Owner exists & has Owner (50) access
        owner_user = ensure_gitlab_user(email=group_owner)
        ensure_group_member(group, owner_user, access_level=50)

        # 3. Ensure argocd-readonly service account exists & has Reporter (20) access
        argo_user = ensure_gitlab_user(email="argocd-readonly@workshop.local", username="argocd-readonly", name="ArgoCD Read-Only Service Account")
        ensure_group_member(group, argo_user, access_level=20)

        # 4. Ensure GitLab Project exists with initialized main branch
        project = ensure_gitlab_project(group, project_name, initialize_with_readme=True, default_branch="main")
        print_success(f"GitLab group '{group_name}' and project '{project_name}' ready with Owner ('{group_owner}') and Reporter ('argocd-readonly') permissions!")

    # Ensure image pull secret in workload namespace for air-gapped platforms (e.g. Harbor on GDC)
    if hasattr(registry_provider, "ensure_image_pull_secret"):
        registry_provider.ensure_image_pull_secret(target_namespace, dry_run=args.dry_run)

    # 8. Phase 2: Render and Seed Manifests into Project Repository
    print_header(f"Phase 2: Seed Application '{app_name}' in Project Repository")
    template_dir = Path(__file__).resolve().parent / "manifest_template"
    if not template_dir.exists():
        print_error(f"Manifest template directory not found at: {template_dir}")
        sys.exit(1)

    template_context = {
        "PROJECT_NAME": project_name,
        "GITLAB_GROUP": group_name,
        "GITLAB_HOST": "gitlab-omnibus.gitlab.svc.cluster.local",
        "REPO_SSH_URL": repo_ssh_url,
        "APP_NAME": app_name,
        "APP_IMAGE": app_image,
        "APP_PORT": str(app_port),
    }

    def render_project_templates(dest_dir: Path):
        manifests_dir = dest_dir / "manifests"
        manifests_dir.mkdir(parents=True, exist_ok=True)

        # 1. Render README.md
        render_template_file(template_dir / "README.md.tmpl", dest_dir / "README.md", template_context)

        # 2. Render manifests/project.yaml
        render_template_file(template_dir / "manifests" / "project.yaml.tmpl", manifests_dir / "project.yaml", template_context)

        # 3. Render manifests/<app_name>-app.yaml
        render_template_file(template_dir / "manifests" / "app.yaml.tmpl", manifests_dir / f"{app_name}-app.yaml", template_context)
        print_info(f"Rendered application manifest: manifests/{app_name}-app.yaml")

        # 4. Render manifests/<app_name>/ directory with workload definitions
        app_workload_dir = manifests_dir / app_name
        app_workload_dir.mkdir(parents=True, exist_ok=True)
        for tmpl_file in (template_dir / "manifests" / "app_workload").glob("*.tmpl"):
            dest_file_name = tmpl_file.name[:-5] if tmpl_file.name.endswith(".tmpl") else tmpl_file.name
            render_template_file(tmpl_file, app_workload_dir / dest_file_name, template_context)
        print_info(f"Rendered workload manifests in: manifests/{app_name}/")

        # 5. Maintain root manifests/kustomization.yaml resources
        root_kustomization_path = manifests_dir / "kustomization.yaml"
        app_ref = f"{app_name}-app.yaml"
        if not root_kustomization_path.exists():
            kust_content = (
                "apiVersion: kustomize.config.k8s.io/v1beta1\n"
                "kind: Kustomization\n\n"
                "resources:\n"
                "  - project.yaml\n"
                f"  - {app_ref}\n"
            )
            root_kustomization_path.write_text(kust_content)
            print_info("Created root manifests/kustomization.yaml")
        else:
            kust_content = root_kustomization_path.read_text()
            lines = kust_content.splitlines()
            res_indices = [i for i, line in enumerate(lines) if line.strip() == "resources:"]
            if res_indices:
                has_proj = any("project.yaml" in line for line in lines)
                has_app = any(app_ref in line for line in lines)
                if not has_proj:
                    lines.insert(res_indices[0] + 1, "  - project.yaml")
                if not has_app:
                    lines.append(f"  - {app_ref}")
                root_kustomization_path.write_text("\n".join(lines) + "\n")
            else:
                lines.append("\nresources:")
                lines.append("  - project.yaml")
                lines.append(f"  - {app_ref}")
                root_kustomization_path.write_text("\n".join(lines) + "\n")
            print_info(f"Updated manifests/kustomization.yaml to include '{app_ref}'")

    p2_has_changes, p2_branch, p2_mr_url = sync_git_repo_with_mr(
        project_path=f"{group_name}/{project_name}",
        branch_prefix=f"feature/add-{app_name}",
        commit_message=f"Add application '{app_name}' to project '{project_name}'",
        mr_title=f"Add Application '{app_name}' to Project '{project_name}'",
        mr_description=f"Adds `{app_name}` microservice and ArgoCD Application manifest for `{group_name}/{project_name}`.",
        update_files_callback=render_project_templates,
        assignee=group_owner,
        root_pass=root_pass,
        target_branch="main",
        auto_approve=args.auto_approve,
        mr_approve=args.mr_approve,
        dry_run=args.dry_run,
    )

    # 9. Phase 3: Add Root Application Manifest to gitops-platform/manifests via MR
    print_header("Phase 3: Create Platform Onboarding Merge Request")

    def update_platform_manifests(dest_dir: Path):
        apps_dir = dest_dir / "manifests" / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        app_manifest_path = apps_dir / f"{project_name}.yaml"
        platform_tmpl = template_dir / "platform_apps" / "project_app.yaml.tmpl"
        render_template_file(platform_tmpl, app_manifest_path, template_context)
        print_info(f"Added project root application: manifests/apps/{project_name}.yaml ({project_name}-apps)")

    mr_title = f"Onboard Project '{project_name}' to GitOps Platform"
    mr_desc = (
        f"## Onboard Project: `{project_name}`\n\n"
        f"- **Project Repository**: `{group_name}/{project_name}.git`\n"
        f"- **Group Owner**: `{group_owner}`\n"
        f"- **Initial Application**: `{app_name}`\n"
        f"- **Target Namespace**: `{target_namespace}`\n"
        f"- **App-of-Apps Entrypoint**: `manifests/apps/{project_name}.yaml`\n\n"
        f"Merging this MR connects `{project_name}` to ArgoCD. All future apps within `{project_name}` can be deployed self-service without modifying the platform repository."
    )

    p3_has_changes, p3_branch, p3_mr_url = sync_git_repo_with_mr(
        project_path="gitops-platform/manifests",
        branch_prefix=f"feature/onboard-{project_name}",
        commit_message=f"Onboard project '{project_name}' to GitOps platform",
        mr_title=mr_title,
        mr_description=mr_desc,
        update_files_callback=update_platform_manifests,
        assignee=group_owner,
        root_pass=root_pass,
        target_branch="main",
        auto_approve=args.auto_approve,
        mr_approve=args.mr_approve,
        dry_run=args.dry_run,
    )


    print_completion_banner(project_name, group_name, app_name, group_owner, p2_mr_url=p2_mr_url, p3_mr_url=p3_mr_url)


if __name__ == "__main__":
    main()
