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

"""Project and identity lifecycle provider for Google Cloud Platform (GCP)."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_active_gcp_project(env_path: Optional[Path] = None) -> Optional[str]:
    """Retrieve GCP project ID from .env, environment variable, or gcloud config."""
    common.load_dotenv(env_path)

    env_proj = os.environ.get("GCP_PROJECT")
    if env_proj:
        return env_proj

    if not common.check_tool_installed("gcloud"):
        return None
    code, out, _ = common.run_command(
        ["gcloud", "config", "get-value", "project"],
        check=False,
        capture_output=True
    )
    if code == 0 and out.strip():
        project = out.strip().splitlines()[-1]
        if project and "(unset)" not in project:
            return project
    return None


def get_active_gcloud_user() -> Optional[str]:
    """Retrieve active authenticated user from gcloud config."""
    if not common.check_tool_installed("gcloud"):
        return None
    code, out, _ = common.run_command(
        ["gcloud", "config", "get-value", "account"],
        check=False,
        capture_output=True
    )
    if code == 0 and out.strip():
        user = out.strip().splitlines()[-1]
        if user and "(unset)" not in user:
            return user
    return None


def get_active_identity() -> Optional[str]:
    """Standard provider method to return active authenticated identity."""
    return get_active_gcloud_user()


def get_available_billing_accounts() -> List[Dict[str, str]]:
    """Query open GCP billing accounts via gcloud."""
    if not common.check_tool_installed("gcloud"):
        return []
    code, out, _ = common.run_command(
        ["gcloud", "billing", "accounts", "list", "--filter=open=true", "--format=json"],
        check=False,
        capture_output=True
    )
    if code != 0 or not out.strip():
        return []

    try:
        data = json.loads(out)
        accounts = []
        for item in data:
            raw_name = item.get("name", "")
            acct_id = raw_name.split("/")[-1] if "/" in raw_name else raw_name
            display_name = item.get("displayName", acct_id)
            accounts.append({
                "id": acct_id,
                "name": display_name,
                "raw_name": raw_name
            })
        return accounts
    except Exception:
        return []


def get_gcp_project_billing_account(project_id: str) -> Optional[str]:
    """Retrieve current billing account linked to a GCP project."""
    if not common.check_tool_installed("gcloud"):
        return None
    code, out, _ = common.run_command(
        ["gcloud", "billing", "projects", "describe", project_id, "--format=value(billingAccountName)"],
        check=False,
        capture_output=True
    )
    if code == 0 and out.strip():
        raw_name = out.strip()
        acct_id = raw_name.split("/")[-1] if "/" in raw_name else raw_name
        return acct_id if acct_id else None
    return None


def select_billing_account(
    specified_account: Optional[str] = None,
    project_id: Optional[str] = None,
    auto_approve: bool = False
) -> Optional[str]:
    """Select a GCP billing account.
    
    If specified_account is provided (via CLI or .env), returns it.
    If project_id exists and already has a linked billing account, reuses it if no specified_account provided.
    Otherwise queries open billing accounts and presents an interactive selection list or auto-selects if single/non-interactive.
    """
    if specified_account:
        return specified_account.split("/")[-1]

    if project_id and gcp_project_exists(project_id):
        current_acct = get_gcp_project_billing_account(project_id)
        if current_acct:
            common.print_warning(f"Reusing existing billing account '{current_acct}' linked to project '{project_id}'.")
            return current_acct

    accounts = get_available_billing_accounts()
    if not accounts:
        common.print_warning("No open GCP billing accounts found or accessible via gcloud.")
        return None

    if len(accounts) == 1:
        acct = accounts[0]
        common.print_info(f"Auto-selected open billing account: '{acct['name']}' ({acct['id']})")
        return acct["id"]

    if auto_approve:
        acct = accounts[0]
        common.print_info(f"Auto-selected first open billing account: '{acct['name']}' ({acct['id']})")
        return acct["id"]

    common.print_header("Select GCP Billing Account")
    if common.RICH_AVAILABLE:
        from rich.table import Table
        table = Table(show_header=True, header_style="bold magenta", expand=False)
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("Billing Account Name", style="green", width=35)
        table.add_column("Account ID", style="yellow", width=25)
        for idx, acct in enumerate(accounts, 1):
            table.add_row(str(idx), acct["name"], acct["id"])
        common.console.print(table)

        prompt_str = f"\n[bold yellow]?[/bold yellow] Select billing account [1-{len(accounts)}]: "
        selection = common.console.input(prompt_str).strip()
    else:
        print("Available Billing Accounts:")
        for idx, acct in enumerate(accounts, 1):
            print(f"  [{idx}] {acct['name']} (ID: {acct['id']})")
        selection = input(f"\nSelect billing account [1-{len(accounts)}]: ").strip()

    try:
        idx = int(selection) - 1
        if 0 <= idx < len(accounts):
            selected = accounts[idx]
            common.print_success(f"Selected billing account: '{selected['name']}' ({selected['id']})")
            return selected["id"]
    except ValueError:
        pass

    common.print_warning("Invalid selection. Proceeding without linking billing account.")
    return None


def link_gcp_project_billing(project_id: str, billing_account_id: str, dry_run: bool = False):
    """Link GCP project to a billing account if not already linked."""
    if not billing_account_id:
        return
    clean_billing_account_id = billing_account_id.split("/")[-1]
    current_acct = get_gcp_project_billing_account(project_id)
    if current_acct and current_acct == clean_billing_account_id:
        common.print_warning(f"GCP Project '{project_id}' is already linked to billing account '{clean_billing_account_id}'.")
        return

    common.print_info(f"Linking GCP project '{project_id}' to billing account '{clean_billing_account_id}'...")
    code, out, err = common.run_command(
        ["gcloud", "billing", "projects", "link", project_id, f"--billing-account={clean_billing_account_id}"],
        description=f"Linking project {project_id} to billing account {clean_billing_account_id}",
        dry_run=dry_run,
        check=False
    )
    if not dry_run and code != 0:
        common.print_error(f"Failed to link billing account. Details:\n{err}")
    else:
        common.print_success(f"GCP Project '{project_id}' linked to billing account '{clean_billing_account_id}'.")


def gcp_project_exists(project_id: str) -> bool:
    """Check if a GCP project exists and is accessible via gcloud."""
    if not common.check_tool_installed("gcloud"):
        return False
    code, _, _ = common.run_command(
        ["gcloud", "projects", "describe", project_id],
        check=False,
        capture_output=True
    )
    return code == 0


def gcp_project_has_workshop_label(project_id: str) -> bool:
    """Check if a GCP project has the 'google-source=gitops-workshop' label."""
    if not common.check_tool_installed("gcloud"):
        return False
    code, out, _ = common.run_command(
        ["gcloud", "projects", "describe", project_id, "--format=value(labels.google-source)"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out and out.strip() == "gitops-workshop":
        return True
    return False


def ensure_project(
    project_id: str,
    project_owner: Optional[str] = None,
    billing_account_id: Optional[str] = None,
    dry_run: bool = False
) -> str:
    """Ensure GCP project exists; if not, create it automatically with google-source=gitops-workshop label, set gcloud config, link billing, and seed owner."""
    if gcp_project_exists(project_id):
        common.print_warning(f"GCP Project '{project_id}' already exists.")
        # Ensure google-source=gitops-workshop label is present
        common.run_command(
            ["gcloud", "projects", "update", project_id, "--update-labels=google-source=gitops-workshop"],
            description="Tagging project with google-source=gitops-workshop label",
            dry_run=dry_run,
            check=False,
            capture_output=True,
        )
    else:
        common.print_info(f"GCP Project '{project_id}' does not exist. Creating GCP project with 'google-source=gitops-workshop' label...")
        code, out, err = common.run_command(
            ["gcloud", "projects", "create", project_id, "--name", project_id, "--labels=google-source=gitops-workshop"],
            description=f"Creating GCP Project '{project_id}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to create GCP Project '{project_id}'. Details:\n{err}")
            sys.exit(1)
        common.print_success(f"GCP Project '{project_id}' created successfully with 'google-source=gitops-workshop' label.")

    # Set as active gcloud project
    common.run_command(
        ["gcloud", "config", "set", "project", project_id],
        description=f"Setting active gcloud project to '{project_id}'",
        dry_run=dry_run
    )

    # Link Billing Account if provided
    if billing_account_id:
        link_gcp_project_billing(project_id, billing_account_id, dry_run=dry_run)

    # Seed Project Owner/Admin IAM role if specified
    if project_owner:
        member = project_owner
        if not any(member.startswith(prefix) for prefix in ["user:", "group:", "serviceAccount:"]):
            member = f"user:{project_owner}"

        common.print_info(f"Seeding project owner IAM binding for '{member}'...")
        common.run_command(
            [
                "gcloud", "projects", "add-iam-policy-binding", project_id,
                f"--member={member}",
                "--role=roles/owner"
            ],
            description=f"Adding IAM owner policy binding for {member}",
            dry_run=dry_run,
            check=False
        )
    return project_id


# Alias for backward compatibility
ensure_gcp_project = ensure_project
