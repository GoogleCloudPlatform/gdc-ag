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

"""Teardown and cleanup provider for Google Cloud Platform (GCP)."""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
from .project import gcp_project_exists, gcp_project_has_workshop_label
from .cluster import (
    cloud_nat_exists,
    cloud_router_exists,
    gke_cluster_exists,
    vpc_network_exists,
)


def teardown_platform(
    project: str,
    cluster_name: str,
    region: str,
    network_name: str,
    delete_project: bool = False,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> bool:
    """Tear down GKE cluster, Cloud NAT, Cloud Router, firewall rules, VPC network, and optionally GCP project."""
    router_name = f"{network_name}-router"
    nat_name = f"{network_name}-nat"

    project_present = gcp_project_exists(project)
    has_workshop_label = gcp_project_has_workshop_label(project) if project_present else False
    cluster_present = gke_cluster_exists(cluster_name, region, project)
    nat_present = cloud_nat_exists(nat_name, router_name, region, project)
    router_present = cloud_router_exists(router_name, region, project)
    vpc_present = vpc_network_exists(network_name, project)

    if dry_run:
        common.print_warning("Running in DRY-RUN mode. No infrastructure will be deleted.")
        return False

    # 1. Terminate local port forwards
    common.print_header("Step 1: Terminate Local Port-Forwards")
    common.run_command(["pkill", "-f", "kubectl port-forward"], description="Terminating active port-forward processes", check=False)
    common.print_success("Local port-forward daemons terminated.")

    # 2. Delete GKE cluster
    common.print_header(f"Step 2: Delete GKE Autopilot Cluster '{cluster_name}'")
    if cluster_present:
        common.print_info(f"Deleting GKE cluster '{cluster_name}' in region '{region}' (this may take 3-5 minutes)...")
        code, out, err = common.run_command(
            [
                "gcloud", "container", "clusters", "delete", cluster_name,
                f"--region={region}",
                f"--project={project}",
                "--quiet"
            ],
            description=f"Deleting GKE cluster '{cluster_name}'",
            check=False,
            capture_output=True,
        )
        if code != 0:
            common.print_error(f"Failed to delete GKE cluster '{cluster_name}':\n{err}")
        else:
            common.print_success(f"GKE cluster '{cluster_name}' deleted successfully.")
    else:
        common.print_info(f"[yellow]EXISTS/SKIP[/yellow] GKE cluster '{cluster_name}' does not exist or was already deleted.")

    # 3. Delete Cloud NAT
    common.print_header(f"Step 3: Delete Cloud NAT '{nat_name}'")
    if nat_present:
        common.print_info(f"Deleting Cloud NAT '{nat_name}' from router '{router_name}'...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "routers", "nats", "delete", nat_name,
                f"--router={router_name}",
                f"--region={region}",
                f"--project={project}",
                "--quiet"
            ],
            description=f"Deleting Cloud NAT '{nat_name}'",
            check=False,
            capture_output=True,
        )
        if code != 0:
            common.print_warning(f"Could not delete Cloud NAT '{nat_name}': {err}")
        else:
            common.print_success(f"Cloud NAT '{nat_name}' deleted successfully.")
    else:
        common.print_info(f"[yellow]EXISTS/SKIP[/yellow] Cloud NAT '{nat_name}' does not exist or was already deleted.")

    # 4. Delete Cloud Router
    common.print_header(f"Step 4: Delete Cloud Router '{router_name}'")
    if router_present:
        common.print_info(f"Deleting Cloud Router '{router_name}' in region '{region}'...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "routers", "delete", router_name,
                f"--region={region}",
                f"--project={project}",
                "--quiet"
            ],
            description=f"Deleting Cloud Router '{router_name}'",
            check=False,
            capture_output=True,
        )
        if code != 0:
            common.print_warning(f"Could not delete Cloud Router '{router_name}': {err}")
        else:
            common.print_success(f"Cloud Router '{router_name}' deleted successfully.")
    else:
        common.print_info(f"[yellow]EXISTS/SKIP[/yellow] Cloud Router '{router_name}' does not exist or was already deleted.")

    # 5. Clean up Firewall rules
    common.print_header(f"Step 5: Clean Up Firewall Rules on '{network_name}'")
    fw_code, fw_out, _ = common.run_command(
        [
            "gcloud", "compute", "firewall-rules", "list",
            f"--filter=network:{network_name}",
            f"--project={project}",
            "--format=value(name)"
        ],
        description="Listing custom firewall rules",
        check=False,
        capture_output=True,
    )
    if fw_code == 0 and fw_out and fw_out.strip():
        for fw_rule in fw_out.strip().splitlines():
            fw_rule = fw_rule.strip()
            if fw_rule:
                common.print_info(f"Deleting firewall rule '{fw_rule}'...")
                common.run_command(
                    ["gcloud", "compute", "firewall-rules", "delete", fw_rule, f"--project={project}", "--quiet"],
                    description=f"Deleting firewall rule '{fw_rule}'",
                    check=False,
                    capture_output=True,
                )
        common.print_success("Firewall rules cleaned up.")
    else:
        common.print_info("[yellow]EXISTS/SKIP[/yellow] No custom firewall rules found.")

    # 6. Delete VPC Network
    common.print_header(f"Step 6: Delete VPC Network '{network_name}'")
    if vpc_present:
        common.print_info(f"Deleting VPC network '{network_name}' in project '{project}'...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "networks", "delete", network_name,
                f"--project={project}",
                "--quiet"
            ],
            description=f"Deleting VPC network '{network_name}'",
            check=False,
            capture_output=True,
        )
        if code != 0:
            common.print_warning(f"Could not delete VPC network '{network_name}': {err}")
        else:
            common.print_success(f"VPC network '{network_name}' deleted successfully.")
    else:
        common.print_info(f"[yellow]EXISTS/SKIP[/yellow] VPC network '{network_name}' does not exist or was already deleted.")

    # 7. Optional GCP Project deletion
    project_deleted = False
    if delete_project:
        common.print_header(f"Step 7: Permanent GCP Project Deletion: '{project}'")
        if not gcp_project_has_workshop_label(project):
            common.print_error(
                f"Refusing to delete GCP project '{project}'!\n"
                f"Safety Guard: Project is missing the 'google-source=gitops-workshop' label.\n"
                f"This project was not created by the GitOps workshop automation and will NOT be deleted."
            )
        else:
            warning_box = (
                f"[bold red]⚠️  CRITICAL DESTRUCTIVE ACTION WARNING ⚠️[/bold red]\n\n"
                f"You are about to permanently delete the entire GCP Project: [bold yellow]{project}[/bold yellow]\n"
                f"All billing associations, IAM policies, and cloud resources in this project will be destroyed.\n\n"
                f"[bold white on red] THIS ACTION CANNOT BE UNDONE. [/bold white on red]"
            )
            if common.RICH_AVAILABLE:
                from rich.panel import Panel
                common.console.print()
                common.console.print(Panel(warning_box, title="[bold red]Permanent GCP Project Deletion[/bold red]", border_style="red", expand=False))
                common.console.print()
            else:
                print(f"\n⚠️  CRITICAL: You are about to permanently delete the GCP project: {project}")

            confirmed = False
            if auto_approve:
                confirmed = True
            else:
                prompt_text = f"Type '{project}' to permanently delete the GCP project (type project ID): "
                try:
                    user_input = input(prompt_text).strip()
                    confirmed = (user_input == project)
                except (KeyboardInterrupt, EOFError):
                    print("\nOperation cancelled.")
                    confirmed = False

            if confirmed:
                common.print_info(f"Deleting GCP project '{project}'...")
                proj_code, _, proj_err = common.run_command(
                    ["gcloud", "projects", "delete", project, "--quiet"],
                    description=f"Deleting GCP project '{project}'",
                    check=False,
                    capture_output=True,
                )
                if proj_code == 0:
                    common.print_success(f"GCP project '{project}' deleted successfully.")
                    project_deleted = True
                else:
                    common.print_error(f"Failed to delete GCP project '{project}':\n{proj_err}")
            else:
                common.print_warning(f"Confirmation input did not match '{project}'. GCP project deletion skipped.")

    return project_deleted
