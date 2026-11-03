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

"""Bootstrap script for gitops-workshop.

Provisions cloud project/context, verifies environment dependencies, and configures workshop prerequisites.
Supports Google Cloud Platform (GCP) and Google Distributed Cloud (GDC) via decoupled platform providers.
"""

import argparse
import os
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from common import (
    check_prerequisites,
    confirm_action,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_next_steps,
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
    get_config,
)



def parse_args():
    parser = argparse.ArgumentParser(
        description="Bootstrap GitOps workshop environment (GCP / GDC-Sandbox)"
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
        help="Simulate execution without modifying infrastructure.",
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
        "--project",
        help="GCP Project name/ID (or GDC context). Sourced from .env or created if missing.",
    )
    parser.add_argument(
        "--project-owner",
        "--owner",
        help="Project owner/admin email (e.g. user@domain.com). Sourced from GCP_PROJECT_OWNER in .env.",
    )
    parser.add_argument(
        "-b",
        "--billing-account",
        help="GCP Billing Account ID. Sourced from GCP_BILLING_ACCOUNT in .env.",
    )
    parser.add_argument(
        "--region",
        help="GCP Region for GKE cluster. Defaults to GCP_REGION in .env or us-central1.",
    )
    parser.add_argument(
        "--cluster-name",
        help="Name of cluster. Defaults to GKE_CLUSTER_NAME / CLUSTER_NAME in .env.",
    )
    return parser.parse_args()


def main():
    # 1. Parse arguments first to get --env-file option
    args = parse_args()

    # 2. Resolve .env file relative to Current Working Directory (CWD), not script location
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 3. Determine target platform & load providers
    target_platform = args.platform or get_target_platform(env_file_path)
    prereqs_provider = get_prereqs_provider(target_platform)
    project_provider = get_project_provider(target_platform)

    # 4. Load configuration & validate required environment variables based on platform
    config = get_config(
        env_file_path,
        cli_overrides={
            "project_id": args.project,
            "region": args.region,
            "cluster_name": args.cluster_name,
            "admin_email": args.project_owner,
        },
    )
    validate_required_env_vars(
        config.required_vars,
        env_file_path=env_file_path,
    )

    project_id = config.project_id
    region = config.region
    cluster_name = config.cluster_name
    project_owner = config.admin_email
    specified_billing = args.billing_account or os.environ.get("GCP_BILLING_ACCOUNT")


    print_header(f"GitOps Workshop Bootstrap ({target_platform.upper()} Mode)")

    # 5. Prerequisite check
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 6. Select Billing Account (if applicable to platform)
    billing_account_id = None
    if hasattr(project_provider, "select_billing_account"):
        billing_account_id = project_provider.select_billing_account(
            specified_account=specified_billing,
            project_id=project_id,
            auto_approve=args.auto_approve
        )

    # 7. Display Execution Parameter Summary Table
    active_user = project_provider.get_active_identity() or "None"
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "Project / Cluster ID": project_id,
        "Project Owner": project_owner or "None (Current User)",
        "Billing Account": billing_account_id or ("Not Applicable" if target_platform == "gdc" else "Not Linked / None"),
        "Region / Cluster": f"{region} / {cluster_name}",
        "Active User / Identity": active_user,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Bootstrap Configuration Parameters")

    # 8. Prompt user for confirmation before proceeding
    if not confirm_action(f"Do you want to proceed with bootstrapping this {target_platform.upper()} environment?", auto_approve=args.auto_approve):
        sys.exit(0)

    # 9. Ensure Project existence / cluster context setup
    print_header(f"Phase 1: {target_platform.upper()} Project & Environment Verification")
    project_id = project_provider.ensure_project(
        project_id,
        project_owner=project_owner,
        billing_account_id=billing_account_id,
        dry_run=args.dry_run
    )

    if args.dry_run:
        print_warning("Running in DRY-RUN mode. No changes will be applied.")

    # 10. Display Next Steps Banner
    print_next_steps(
        project_id,
        project_owner=project_owner,
        next_script="scripts/bootstrap/provision_cluster.py",
        platform=target_platform,
        env_file=args.env_file,
    )


if __name__ == "__main__":
    main()
