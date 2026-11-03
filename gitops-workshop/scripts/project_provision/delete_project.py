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
Interactive and explicit deletion tool for tenant projects and empty groups in GitLab and GitOps platform.

Safety & Operational Standards:
- Strictly requires manual typing of the project/group name as confirmation.
- NO -y / --auto-approve flag exists (cannot be automated).
- Prominent red DESTRUCTIVE action warning.
- Empty group protection: Refuses to delete any group containing projects or subgroups.
- Interactive project listing with post-delete refresh loop.
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
from typing import Any, Dict, List, Optional, Tuple

# Ensure shared scripts/common directory is in python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

from common import (  # noqa: E402
    RICH_AVAILABLE,
    check_prerequisites,
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

from gitlab_utils import (  # noqa: E402
    get_gitlab_client,
    get_gitlab_credentials,
    sync_git_repo_with_mr,
)

if RICH_AVAILABLE:
    from rich.panel import Panel
    from rich.table import Table


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Delete a tenant project or empty group in GitLab and clean up GitOps platform integration."
    )
    parser.add_argument(
        "--group",
        "-g",
        dest="group_name",
        type=str,
        default=None,
        help="GitLab group name (e.g. core-banking, ecommerce, workloads)",
    )
    parser.add_argument(
        "--project",
        "-p",
        dest="project_name",
        type=str,
        default=None,
        help="Name of the specific project repository to delete directly without interactive listing",
    )
    parser.add_argument(
        "--delete-group",
        action="store_true",
        help="Delete the specified group. Only succeeds if the group is completely empty (no projects or subgroups).",
    )
    parser.add_argument(
        "-m",
        "--mr-approve",
        action="store_true",
        help="Automatically approve and merge created GitLab Merge Requests via API",
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


def print_destructive_warning(target_type: str, target_name: str, extra_details: Optional[List[str]] = None):
    """Display prominent red warning panel before destructive operations."""
    details_str = ""
    if extra_details:
        details_str = "\n" + "\n".join(f"  • {item}" for item in extra_details)

    warning_text = (
        f"[bold red]⚠️  DESTRUCTIVE ACTION WARNING ⚠️[/bold red]\n\n"
        f"You are about to permanently delete the {target_type}: [bold yellow]{target_name}[/bold yellow]\n"
        f"{details_str}\n\n"
        f"[bold white on red] THIS ACTION CANNOT BE UNDONE. [/bold white on red]\n"
        f"All repository source code, Git branches, commit history, and platform catalog entries will be permanently removed."
    )
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(warning_text, title="[bold red]CRITICAL: PERMANENT DELETION[/bold red]", border_style="red", expand=False))
        console.print()
    else:
        print("\n=======================================================")
        print(f"⚠️  DESTRUCTIVE ACTION: PERMANENTLY DELETING {target_type.upper()}: {target_name}")
        print("=======================================================\n")


def prompt_typed_confirmation(expected_string: str, prompt_label: str) -> bool:
    """Prompt the user to explicitly type the exact name to confirm deletion."""
    prompt_text = f"Type [bold red]'{expected_string}'[/bold red] to permanently delete ({prompt_label}): "
    if RICH_AVAILABLE:
        console.print(prompt_text, end="")
    else:
        print(f"Type '{expected_string}' to permanently delete ({prompt_label}): ", end="")

    try:
        user_input = input().strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.")
        return False

    return user_input == expected_string


def cleanup_gitops_platform_manifest(project_name: str, root_pass: str, mr_approve: bool = False):
    """Remove project entry from gitops-platform/manifests repository via Merge Request."""
    print_info(f"Checking for GitOps platform integration in 'gitops-platform/manifests'...")

    def remove_platform_entry(dest_dir: Path):
        app_manifest = dest_dir / "manifests" / "apps" / f"{project_name}.yaml"
        if app_manifest.exists():
            app_manifest.unlink()
            print_info(f"Removed platform catalog file: manifests/apps/{project_name}.yaml")
        else:
            print_info(f"No platform entry found at manifests/apps/{project_name}.yaml")

    sync_git_repo_with_mr(
        project_path="gitops-platform/manifests",
        branch_prefix=f"feature/remove-{project_name}",
        commit_message=f"Remove project '{project_name}' from GitOps platform catalog",
        mr_title=f"Remove Project '{project_name}' from GitOps Platform",
        mr_description=f"Decommission project `{project_name}` and remove its App-of-Apps entrypoint.",
        update_files_callback=remove_platform_entry,
        root_pass=root_pass,
        target_branch="main",
        mr_approve=mr_approve,
    )


def cleanup_argocd_resources(project_name: str):
    """Clean up live ArgoCD Application and AppProject if present in Kubernetes."""
    print_info(f"Checking live Kubernetes cluster for ArgoCD resources for '{project_name}'...")
    # 1. Delete ArgoCD Application
    app_check = ["kubectl", "get", "app", f"{project_name}-apps", "-n", "argocd"]
    code, _, _ = run_command(app_check, description="Checking ArgoCD App", check=False, capture_output=True)
    if code == 0:
        print_info(f"Deleting live ArgoCD Application '{project_name}-apps'...")
        run_command(
            ["kubectl", "delete", "app", f"{project_name}-apps", "-n", "argocd", "--cascade=foreground"],
            description="Deleting ArgoCD Application",
            check=False,
            capture_output=True,
        )
        print_success(f"Deleted ArgoCD Application '{project_name}-apps'.")

    # 2. Delete ArgoCD AppProject
    proj_check = ["kubectl", "get", "appproject", project_name, "-n", "argocd"]
    code, _, _ = run_command(proj_check, description="Checking ArgoCD AppProject", check=False, capture_output=True)
    if code == 0:
        print_info(f"Deleting live ArgoCD AppProject '{project_name}'...")
        run_command(
            ["kubectl", "delete", "appproject", project_name, "-n", "argocd"],
            description="Deleting ArgoCD AppProject",
            check=False,
            capture_output=True,
        )
        print_success(f"Deleted ArgoCD AppProject '{project_name}'.")


def delete_single_project(gl: Any, group_name: str, project_name: str, root_pass: str, mr_approve: bool = False) -> bool:
    """Safely and permanently delete a single project."""
    full_path = f"{group_name}/{project_name}"
    try:
        project = gl.projects.get(full_path)
    except Exception as e:
        print_error(f"Project '{full_path}' not found in GitLab: {e}")
        return False

    extra_details = [
        f"GitLab Repository : http://localhost:8081/{full_path}",
        f"GitLab Project ID : {project.id}",
        f"Default Branch    : {project.default_branch or 'main'}",
        f"GitOps Catalog    : manifests/apps/{project_name}.yaml",
        f"ArgoCD App-of-Apps: {project_name}-apps",
    ]

    print_destructive_warning("Project Repository", full_path, extra_details)

    if not prompt_typed_confirmation(project_name, f"enter '{project_name}'"):
        print_warning(f"Confirmation input did not match '{project_name}'. Deletion aborted.")
        return False

    print_info(f"Deleting project '{full_path}' in GitLab...")
    try:
        project.delete()
        print_success(f"Project '{full_path}' deleted successfully from GitLab!")
    except Exception as e:
        print_error(f"Failed to delete project '{full_path}': {e}")
        return False

    # Clean up GitOps Platform repo & ArgoCD live objects
    try:
        cleanup_gitops_platform_manifest(project_name, root_pass, mr_approve=mr_approve)
    except Exception as e:
        print_warning(f"Could not clean platform manifest in GitLab repo: {e}")

    try:
        cleanup_argocd_resources(project_name)
    except Exception as e:
        print_warning(f"Could not clean live ArgoCD cluster resources: {e}")

    print_success(f"Cleanup for project '{full_path}' complete!")
    return True


def delete_single_group(gl: Any, group_name: str) -> bool:
    """Safely delete an empty group."""
    try:
        group = gl.groups.get(group_name)
    except Exception as e:
        print_error(f"Group '{group_name}' not found in GitLab: {e}")
        return False

    # Verify group is empty
    projects = group.projects.list(all=True)
    subgroups = group.subgroups.list(all=True)

    if len(projects) > 0 or len(subgroups) > 0:
        print_error(
            f"Cannot delete group '{group_name}' because it is NOT empty!\n"
            f"  - Active Projects: {len(projects)}\n"
            f"  - Active Subgroups: {len(subgroups)}\n\n"
            f"Please delete all projects inside '{group_name}' first."
        )
        if len(projects) > 0:
            print_info("Remaining projects inside this group:")
            for p in projects:
                print_info(f"  • {p.name} ({p.path_with_namespace})")
        return False

    extra_details = [
        f"GitLab Group Path : http://localhost:8081/{group_name}",
        f"GitLab Group ID   : {group.id}",
        f"Projects Inside   : 0 (Empty)",
    ]

    print_destructive_warning("Empty Group", group_name, extra_details)

    if not prompt_typed_confirmation(group_name, f"enter '{group_name}'"):
        print_warning(f"Confirmation input did not match '{group_name}'. Group deletion aborted.")
        return False

    print_info(f"Deleting empty group '{group_name}' in GitLab...")
    try:
        group.delete()
        print_success(f"Group '{group_name}' deleted successfully from GitLab!")
        return True
    except Exception as e:
        print_error(f"Failed to delete group '{group_name}': {e}")
        return False


def interactive_project_list_loop(gl: Any, group_name: str, root_pass: str, mr_approve: bool = False):
    """List projects in group, allow selection to delete, and refresh after deletion."""
    while True:
        try:
            group = gl.groups.get(group_name)
        except Exception as e:
            print_error(f"Group '{group_name}' not found in GitLab: {e}")
            return

        projects = group.projects.list(all=True)

        if not projects:
            print_info(f"\n[bold green]Group '{group_name}' is currently empty (0 projects).[/bold green]")
            print()
            try:
                ans = input(f"Would you like to delete this empty group '{group_name}' now? (y/n): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break

            if ans in ("y", "yes"):
                delete_single_group(gl, group_name)
            break

        # Display Project Selection Table
        print_header(f"Projects in Group: '{group_name}'")
        if RICH_AVAILABLE:
            table = Table(title=f"Projects in '{group_name}'", header_style="bold cyan")
            table.add_column("#", style="bold yellow", justify="right", width=4)
            table.add_column("Project Name", style="bold white")
            table.add_column("Full Path", style="cyan")
            table.add_column("Created At", style="dim")

            for idx, p in enumerate(projects, 1):
                created_str = getattr(p, "created_at", "")[:10] if hasattr(p, "created_at") else ""
                table.add_row(str(idx), p.name, p.path_with_namespace, created_str)

            console.print(table)
            console.print()
        else:
            print(f"\n--- Projects in '{group_name}' ---")
            for idx, p in enumerate(projects, 1):
                print(f"[{idx}] {p.name} ({p.path_with_namespace})")
            print()

        print_info("Options:")
        print_info("  • Enter a project number (e.g. 1) or project name to delete")
        print_info("  • Enter 'g' to attempt deleting the group")
        print_info("  • Enter 'q' or 'exit' to quit")
        print()

        try:
            choice = input(f"Select project to delete from '{group_name}': ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice.lower() in ("q", "quit", "exit", ""):
            print_info("Exiting project deletion.")
            break

        if choice.lower() == "g":
            delete_single_group(gl, group_name)
            continue

        selected_project_name = None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(projects):
                selected_project_name = projects[idx - 1].name
            else:
                print_error(f"Invalid selection: {idx}. Please choose between 1 and {len(projects)}.")
                continue
        else:
            # Match by name
            matching = [p for p in projects if p.name.lower() == choice.lower() or p.path.lower() == choice.lower()]
            if matching:
                selected_project_name = matching[0].name
            else:
                print_error(f"No project named '{choice}' found in group '{group_name}'.")
                continue

        if selected_project_name:
            delete_single_project(gl, group_name, selected_project_name, root_pass, mr_approve=mr_approve)
            print_info("\nRefreshing project list...")
            time.sleep(1)


def main():
    args = parse_args()

    # 1. Resolve .env file
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 2. Validate required environment variables
    env_config = validate_required_env_vars(
        ["GITLAB_HTTP_URL"],
        env_file_path=env_file_path,
    )
    gitlab_http_url = env_config["GITLAB_HTTP_URL"]
    root_pass, _ = get_gitlab_credentials()

    print_header("GitOps Tenant Project & Group Deletion")

    # 3. Check prerequisites
    if not check_prerequisites(verbose=args.check_prereqs):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)


    # 4. Connect to GitLab
    gl = get_gitlab_client(url=gitlab_http_url)

    # 5. Resolve Group Name
    group_name = args.group_name.strip().lower() if args.group_name else None

    if not group_name:
        # Discover available non-platform groups
        try:
            all_groups = [g for g in gl.groups.list(all=True) if g.full_path != "gitops-platform"]
        except Exception as e:
            print_error(f"Could not connect to GitLab to list groups: {e}")
            sys.exit(1)

        if not all_groups:
            print_info("No tenant groups found in GitLab.")
            sys.exit(0)

        print_header("Available Tenant Groups in GitLab")
        if RICH_AVAILABLE:
            table = Table(title="GitLab Groups", header_style="bold cyan")
            table.add_column("#", style="bold yellow", justify="right", width=4)
            table.add_column("Group Path", style="bold white")
            table.add_column("Projects Count", justify="center")

            for idx, g in enumerate(all_groups, 1):
                proj_count = len(g.projects.list(all=True))
                table.add_row(str(idx), g.full_path, str(proj_count))
            console.print(table)
            console.print()
        else:
            for idx, g in enumerate(all_groups, 1):
                print(f"[{idx}] {g.full_path}")

        try:
            grp_choice = input("Enter group number or name to manage (or 'q' to quit): ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

        if grp_choice.lower() in ("q", "quit", "exit", ""):
            sys.exit(0)

        if grp_choice.isdigit() and 1 <= int(grp_choice) <= len(all_groups):
            group_name = all_groups[int(grp_choice) - 1].full_path
        else:
            group_name = grp_choice.lower()

    # 6. Branch into specific action
    if args.delete_group:
        # Group deletion mode
        delete_single_group(gl, group_name)
    elif args.project_name:
        # Direct project deletion mode
        project_name = args.project_name.strip().lower()
        delete_single_project(gl, group_name, project_name, root_pass, mr_approve=args.mr_approve)
    else:
        # Interactive project selection loop
        interactive_project_list_loop(gl, group_name, root_pass, mr_approve=args.mr_approve)


if __name__ == "__main__":
    main()
