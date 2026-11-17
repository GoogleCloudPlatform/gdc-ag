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

"""Teardown script for application-workshop.

Idempotently removes a deployed application (translate-api or upload-api) from
ArgoCD and Kubernetes without deleting the GitLab project repository or
platform App-of-Apps configuration owned by gitops-workshop.
"""

import argparse
from pathlib import Path
import shutil
import sys
from typing import List

# Add scripts/common directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent / "common"))
from common import (
    confirm_action,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_parameter_summary,
    print_success,
    run_command,
    validate_required_env_vars,
)
from platform_adapter import (
    get_config,
    get_prereqs_provider,
    get_project_provider,
    get_target_platform,
)


def discover_available_apps(repo_root: Path) -> List[str]:
    apps_dir = repo_root / "apps"
    if not apps_dir.exists():
        return []
    return sorted(p.name for p in apps_dir.iterdir() if p.is_dir())


def parse_args(available_apps: List[str]):
    parser = argparse.ArgumentParser(
        description="Teardown Deployed GitOps Application Workload (GCP / GDC)"
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env configuration file (relative to current working directory). Default: .env",
    )
    parser.add_argument(
        "--platform",
        choices=["gcp", "gdc"],
        help="Target platform override (gcp | gdc). Defaults to TARGET_PLATFORM in .env.",
    )
    parser.add_argument(
        "-r",
        "--repo",
        help="Target GitLab project repository (<group>/<project>).",
    )
    parser.add_argument(
        "-g",
        "--group",
        help="GitLab group name. Defaults to GITLAB_GROUP in .env or 'workloads'.",
    )
    parser.add_argument(
        "-p",
        "--project-name",
        help="GitLab project name. Defaults to GITLAB_PROJECT in .env.",
    )
    parser.add_argument(
        "-a",
        "--app-name",
        choices=available_apps if available_apps else None,
        help=f"Application to remove. Available: {', '.join(available_apps)}",
    )
    parser.add_argument(
        "--all-apps",
        action="store_true",
        help="Remove all workshop applications (translate-api and upload-api).",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Check tool dependencies and environment setup without making changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without deleting resources.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve teardown prompts without interactive confirmation.",
    )
    return parser.parse_args()


def main():
    repo_root = Path(__file__).resolve().parent.parent
    available_apps = discover_available_apps(repo_root)
    args = parse_args(available_apps)

    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    cli_group = args.group
    cli_project = args.project_name
    if args.repo and "/" in args.repo:
        cli_group, cli_project = args.repo.strip().strip("/").split("/", 1)

    target_platform = args.platform or get_target_platform(env_file_path)
    prereqs_provider = get_prereqs_provider(target_platform)
    project_provider = get_project_provider(target_platform)

    config = get_config(
        env_file_path,
        cli_overrides={
            "platform": target_platform,
            "gitlab_group": cli_group,
            "gitlab_project": cli_project,
            "app_name": args.app_name,
        },
    )

    validate_required_env_vars(config.required_vars, env_file_path=env_file_path)

    print_header(f"Application Workshop Cleanup ({target_platform.upper()} Mode)")

    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    target_apps = available_apps if args.all_apps else [config.app_name]
    active_identity = project_provider.get_active_identity() or "None"
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"

    params_summary = {
        "Target Platform": target_platform.upper(),
        "Applications to Remove": ", ".join(target_apps),
        "Target K8s Namespaces": ", ".join(target_apps),
        "GitLab Project Repo": f"{config.gitlab_group}/{config.gitlab_project} (kept intact)",
        "Active Identity": active_identity,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Application Cleanup Parameters")

    if not confirm_action(
        f"Remove deployed resources for {', '.join(target_apps)}?",
        auto_approve=args.auto_approve,
    ):
        sys.exit(0)

    for app_name in target_apps:
        run_command(
            ["pkill", "-f", f"svc/{app_name}"],
            description=f"Stopping port-forward for {app_name}",
            check=False,
            dry_run=args.dry_run,
        )
        print_info(f"Removing ArgoCD Application '{app_name}'...")
        run_command(
            ["kubectl", "delete", "application", app_name, "-n", "argocd", "--ignore-not-found=true"],
            description=f"Deleting ArgoCD Application {app_name}",
            check=False,
            dry_run=args.dry_run,
        )
        print_info(f"Deleting workload namespace '{app_name}'...")
        run_command(
            ["kubectl", "delete", "namespace", app_name, "--ignore-not-found=true", "--wait=false"],
            description=f"Deleting namespace {app_name}",
            check=False,
            dry_run=args.dry_run,
        )

    deployed_dir = repo_root / ".deployed-manifests"
    if deployed_dir.exists() and not args.dry_run:
        shutil.rmtree(deployed_dir)
        print_info("Cleaned local .deployed-manifests/ working directory.")

    print_success(f"Application teardown complete for: {', '.join(target_apps)}.")


if __name__ == "__main__":
    main()
