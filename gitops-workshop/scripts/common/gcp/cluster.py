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

"""Cluster and networking lifecycle provider for Google Cloud Platform (GCP)."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def gke_cluster_exists(cluster_name: str, region: str, project_id: Optional[str] = None) -> bool:
    """Check if a GKE cluster exists in the specified region."""
    if not common.check_tool_installed("gcloud"):
        return False
    cmd = ["gcloud", "container", "clusters", "describe", cluster_name, f"--region={region}"]
    if project_id:
        cmd.append(f"--project={project_id}")
    code, _, _ = common.run_command(cmd, check=False, capture_output=True)
    return code == 0


def configure_kubectl_credentials(cluster_name: str, region: str, project_id: str, dry_run: bool = False):
    """Configure local kubectl credentials context for the GKE cluster."""
    common.print_info(f"Configuring kubectl context for cluster '{cluster_name}'...")
    code, out, err = common.run_command(
        [
            "gcloud", "container", "clusters", "get-credentials", cluster_name,
            f"--region={region}",
            f"--project={project_id}"
        ],
        description=f"Fetching kubectl credentials for '{cluster_name}'",
        dry_run=dry_run,
        check=False
    )
    if not dry_run and code != 0:
        common.print_error(f"Failed to configure kubectl credentials. Details:\n{err}")
    else:
        common.print_success(f"kubectl context configured for '{cluster_name}'.")


def enable_gcp_services(project_id: str, services: List[str], dry_run: bool = False):
    """Enable required GCP APIs/services for the project idempotently."""
    for service in services:
        common.print_info(f"Enabling GCP service '{service}' for project '{project_id}'...")
        code, out, err = common.run_command(
            ["gcloud", "services", "enable", service, f"--project={project_id}"],
            description=f"Enabling GCP service '{service}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to enable GCP service '{service}'. Details:\n{err}")
            sys.exit(1)
        common.print_success(f"GCP service '{service}' enabled.")


def vpc_network_exists(network_name: str, project_id: str) -> bool:
    """Check if a VPC network exists in the GCP project."""
    if not common.check_tool_installed("gcloud"):
        return False
    code, _, _ = common.run_command(
        ["gcloud", "compute", "networks", "describe", network_name, f"--project={project_id}"],
        check=False,
        capture_output=True
    )
    return code == 0


def ensure_vpc_network(network_name: str, project_id: str, dry_run: bool = False) -> str:
    """Idempotently create an auto-subnet VPC network in the project if it does not exist."""
    if vpc_network_exists(network_name, project_id):
        common.print_warning(f"VPC Network '{network_name}' already exists in project '{project_id}'.")
    else:
        common.print_info(f"VPC Network '{network_name}' does not exist. Creating auto-subnet VPC network...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "networks", "create", network_name,
                "--subnet-mode=auto",
                f"--project={project_id}"
            ],
            description=f"Creating VPC network '{network_name}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to create VPC network '{network_name}'. Details:\n{err}")
            sys.exit(1)
        common.print_success(f"VPC Network '{network_name}' created successfully.")

    return network_name


def cloud_router_exists(router_name: str, region: str, project_id: str) -> bool:
    """Check if a Cloud Router exists in the GCP project."""
    if not common.check_tool_installed("gcloud"):
        return False
    code, _, _ = common.run_command(
        ["gcloud", "compute", "routers", "describe", router_name, f"--region={region}", f"--project={project_id}"],
        check=False,
        capture_output=True
    )
    return code == 0


def cloud_nat_exists(nat_name: str, router_name: str, region: str, project_id: str) -> bool:
    """Check if a Cloud NAT gateway exists in the GCP project."""
    if not common.check_tool_installed("gcloud"):
        return False
    code, _, _ = common.run_command(
        ["gcloud", "compute", "routers", "nats", "describe", nat_name, f"--router={router_name}", f"--region={region}", f"--project={project_id}"],
        check=False,
        capture_output=True
    )
    return code == 0


def ensure_cloud_nat(network_name: str, region: str, project_id: str, dry_run: bool = False):
    """Ensure Cloud Router and Cloud NAT exist for private GKE node outbound egress."""
    router_name = f"{network_name}-router"
    nat_name = f"{network_name}-nat"

    # 1. Cloud Router
    if cloud_router_exists(router_name, region, project_id):
        common.print_warning(f"Cloud Router '{router_name}' already exists in region '{region}'.")
    else:
        common.print_info(f"Creating Cloud Router '{router_name}' on network '{network_name}'...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "routers", "create", router_name,
                f"--network={network_name}",
                f"--region={region}",
                f"--project={project_id}"
            ],
            description=f"Creating Cloud Router '{router_name}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to create Cloud Router '{router_name}'. Details:\n{err}")

    # 2. Cloud NAT
    if cloud_nat_exists(nat_name, router_name, region, project_id):
        common.print_warning(f"Cloud NAT '{nat_name}' already exists.")
    else:
        common.print_info(f"Creating Cloud NAT gateway '{nat_name}' for outbound egress...")
        code, out, err = common.run_command(
            [
                "gcloud", "compute", "routers", "nats", "create", nat_name,
                f"--router={router_name}",
                "--auto-allocate-nat-external-ips",
                "--nat-all-subnet-ip-ranges",
                f"--region={region}",
                f"--project={project_id}"
            ],
            description=f"Creating Cloud NAT '{nat_name}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to create Cloud NAT '{nat_name}'. Details:\n{err}")
        else:
            common.print_success(f"Cloud NAT gateway '{nat_name}' configured successfully.")


def ensure_cluster(
    cluster_name: str,
    region: str,
    project_id: str,
    network_name: Optional[str] = None,
    enable_private_nodes: bool = True,
    dry_run: bool = False
):
    """Provision a GKE Autopilot cluster idempotently."""
    actual_network = network_name or f"{cluster_name}-vpc"

    # 1. Ensure required GCP APIs are enabled for GKE
    enable_gcp_services(project_id, ["container.googleapis.com", "compute.googleapis.com"], dry_run=dry_run)

    # 2. Ensure VPC Network exists
    ensure_vpc_network(actual_network, project_id, dry_run=dry_run)

    # 3. Ensure Cloud NAT exists for private nodes egress
    if enable_private_nodes:
        ensure_cloud_nat(actual_network, region, project_id, dry_run=dry_run)

    # 4. Create GKE Autopilot cluster
    if gke_cluster_exists(cluster_name, region, project_id):
        common.print_warning(f"GKE Autopilot cluster '{cluster_name}' already exists in region '{region}'.")
    else:
        cmd = [
            "gcloud", "container", "clusters", "create-auto", cluster_name,
            f"--region={region}",
            f"--network={actual_network}",
            f"--project={project_id}",
            "--quiet"
        ]
        if enable_private_nodes:
            cmd.append("--enable-private-nodes")

        common.print_info(f"Creating GKE Autopilot cluster '{cluster_name}' (Private Nodes) in region '{region}' on network '{actual_network}'...")
        code, out, err = common.run_command(
            cmd,
            description=f"Provisioning GKE Autopilot cluster '{cluster_name}' on network '{actual_network}'",
            dry_run=dry_run,
            check=False
        )
        if not dry_run and code != 0:
            common.print_error(f"Failed to create GKE Autopilot cluster '{cluster_name}'. Details:\n{err}")
            sys.exit(1)
        common.print_success(f"GKE Autopilot cluster '{cluster_name}' created successfully.")

    # 5. Configure kubectl context
    configure_kubectl_credentials(cluster_name, region, project_id, dry_run=dry_run)


def get_cluster_info(cluster_name: str, region: str, project_id: str) -> Dict[str, Any]:
    """Retrieve metadata about the cluster."""
    return {
        "cluster_name": cluster_name,
        "region": region,
        "project_id": project_id,
        "cluster_type": "GKE Autopilot",
        "storage_class": "standard-rwo",
    }


# Alias for backward compatibility
ensure_gke_autopilot_cluster = ensure_cluster
