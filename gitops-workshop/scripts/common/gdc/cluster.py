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

"""Cluster lifecycle provider for Google Distributed Cloud (GDC) Sandbox."""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common

if common.RICH_AVAILABLE:
    from rich.table import Table


def get_management_kubeconfig() -> Optional[str]:
    """Return path to GDC management control plane kubeconfig if available."""
    configured = os.environ.get("GDC_MANAGEMENT_KUBECONFIG")
    if configured and Path(configured).exists():
        return configured
    default_admin = Path("/home/sandboxuser10/org-1-admin-kubeconfig")
    if default_admin.exists():
        return str(default_admin)
    return None


def get_gdc_project_id() -> str:
    """Return GDC parent project namespace where Cluster CR resides."""
    return (
        os.environ.get("GDC_PROJECT_ID")
        or "project-lowhigh"
    )


def sync_cluster_manifests(cluster_name: str, platform_admin: Optional[str] = None, target_dir: Optional[Path] = None) -> Path:
    """Populate .deployed-manifests/gdc_cluster/ with live cluster name in the overlay patches."""
    if target_dir is None:
        target_dir = common.get_deployed_manifests_dir()

    cluster_dir = target_dir / "gdc_cluster"
    if not cluster_dir.exists():
        cluster_dir = target_dir / "cluster"
    if not cluster_dir.exists():
        common.ensure_deployed_manifests_dir()
        cluster_dir = target_dir / "gdc_cluster"

    node_pool_name = f"{cluster_name}-nodes"
    overlay_dir = cluster_dir / "overlays" / "gdc"

    # 1. Update cluster-patch.yaml in overlay
    cluster_patch = overlay_dir / "cluster-patch.yaml"
    if cluster_patch.exists():
        content = cluster_patch.read_text()
        content = content.replace("TEMPLATE_CLUSTER_NAME", cluster_name)
        content = content.replace("TEMPLATE_NODE_POOL_NAME", node_pool_name)
        # Also support NOT_CONFIGURED_ as fallback
        content = content.replace("NOT_CONFIGURED_CLUSTER_NAME", cluster_name)
        content = content.replace("NOT_CONFIGURED_NODE_POOL_NAME", node_pool_name)
        cluster_patch.write_text(content)
        common.print_info(f"Updated deployed cluster overlay patch with name: '{cluster_name}'")

    return overlay_dir




def ensure_cluster_credentials(cluster_name: str, project_id: str, kubeconfig_path: str) -> bool:
    """Fetch/update standard cluster kubeconfig via gdcloud clusters get-credentials."""
    common.print_info(f"Retrieving standard cluster credentials for '{cluster_name}' via gdcloud...")
    cmd = [
        "gdcloud", "clusters", "get-credentials", cluster_name,
        "--standard",
        f"--project={project_id}",
        "--quiet",
    ]
    env = dict(os.environ)
    env["KUBECONFIG"] = kubeconfig_path

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode == 0:
        common.print_success(f"Cluster credentials saved to '{kubeconfig_path}'.")
        return True
    else:
        common.print_warning(f"Could not retrieve credentials via gdcloud: {res.stderr or res.stdout}")
        return False


def wait_for_cluster_ready(
    cluster_name: str,
    project_id: str,
    mgmt_kubeconfig: str,
    timeout_seconds: Optional[int] = None,
    poll_interval: int = 15
) -> bool:
    """Poll GDC management plane for standard cluster Ready condition."""
    if timeout_seconds is None:
        timeout_seconds = int(os.environ.get("GDC_CLUSTER_TIMEOUT", "18000"))
    common.print_info(f"Waiting for GDC standard cluster '{cluster_name}' in project '{project_id}' to become Ready (Timeout: {int(timeout_seconds/3600)}h)...")
    start_time = time.time()
    last_log_time = 0.0
    last_state = None

    while time.time() - start_time < timeout_seconds:
        cmd = [
            "kubectl", "--kubeconfig", mgmt_kubeconfig, "-n", project_id,
            "get", "cluster.cluster.gdc.goog", cluster_name, "-o", "json"
        ]
        code, out, _ = common.run_command(cmd, check=False, capture_output=True)
        if code == 0 and out:
            try:
                data = json.loads(out)
                status = data.get("status", {})
                state = status.get("clusterState", "Unknown")
                conditions = status.get("conditions", [])
                is_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)

                elapsed_min = int((time.time() - start_time) / 60)
                if is_ready or state == "Running":
                    common.print_success(f"GDC Standard cluster '{cluster_name}' is Ready (State: {state}, {elapsed_min}m elapsed).")
                    return True

                now = time.time()
                if state != last_state or (now - last_log_time >= 60):
                    common.print_info(f"Cluster '{cluster_name}' status: state={state}, {elapsed_min}m elapsed. Waiting...")
                    last_state = state
                    last_log_time = now
            except Exception:
                pass
        time.sleep(poll_interval)

    common.print_error(f"Timed out waiting for cluster '{cluster_name}' after {timeout_seconds}s.")
    return False


def ensure_cluster(
    cluster_name: str,
    region: Optional[str] = None,
    project_id: Optional[str] = None,
    network_name: Optional[str] = None,
    enable_private_nodes: bool = True,
    dry_run: bool = False
):
    """Ensure GDC standard cluster is created, ready, and accessible via local KUBECONFIG."""
    common.print_info(f"GDC-Sandbox mode: Ensuring standard cluster '{cluster_name}'...")

    gdc_project = project_id or get_gdc_project_id()
    mgmt_kubeconfig = get_management_kubeconfig()
    platform_admin = os.environ.get("PLATFORM_ADMIN") or os.environ.get("GCP_PROJECT_OWNER") or "platform-admin@example.com"
    target_kubeconfig = os.environ.get("KUBECONFIG") or f"/home/sandboxuser10/{cluster_name}-kubeconfig"

    # 1. Sync deployed cluster manifests
    deployed_dir = common.ensure_deployed_manifests_dir()
    overlay_dir = sync_cluster_manifests(cluster_name, platform_admin, target_dir=deployed_dir)

    # 2. Check if cluster already exists in GDC management plane
    cluster_exists = False
    cluster_ready = False

    if mgmt_kubeconfig:
        check_cmd = [
            "kubectl", "--kubeconfig", mgmt_kubeconfig, "-n", gdc_project,
            "get", "cluster.cluster.gdc.goog", cluster_name, "-o", "json"
        ]
        code, out, _ = common.run_command(check_cmd, check=False, capture_output=True)
        if code == 0 and out:
            try:
                data = json.loads(out)
                cluster_exists = True
                status = data.get("status", {})
                state = status.get("clusterState", "Unknown")
                conditions = status.get("conditions", [])
                cluster_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions) or state == "Running"
                common.print_info(f"Existing cluster '{cluster_name}' discovered in project '{gdc_project}' (State: {state}).")
            except Exception:
                pass

    # 3. Provision cluster if it does not exist
    if not cluster_exists:
        common.print_header(f"Provisioning GDC Standard Cluster: {cluster_name}")
        if dry_run:
            common.print_info(f"[DRY-RUN] Would apply {overlay_dir} to GDC project '{gdc_project}' via management control plane.")
            common.print_info(f"[DRY-RUN] Would wait for cluster '{cluster_name}' to reach Ready state.")
            common.print_info(f"[DRY-RUN] Would fetch cluster credentials to '{target_kubeconfig}'.")
            return

        if not mgmt_kubeconfig:
            common.print_error("Cannot create cluster: GDC management kubeconfig not found. Please set GDC_MANAGEMENT_KUBECONFIG in .env.")
            sys.exit(1)

        apply_cmd = [
            "kubectl", "--kubeconfig", mgmt_kubeconfig, "-n", gdc_project,
            "apply", "-k", str(overlay_dir)
        ]
        common.run_command(
            apply_cmd,
            description=f"Applying standard cluster declaration for '{cluster_name}' in '{gdc_project}'",
            dry_run=dry_run
        )

    else:
        common.print_success(f"GDC standard cluster '{cluster_name}' already declared.")

    # Wait for cluster to reach Ready state if not already ready
    if not cluster_ready:
        if dry_run:
            common.print_info(f"[DRY-RUN] Would wait for cluster '{cluster_name}' to reach Ready state.")
        else:
            if not wait_for_cluster_ready(cluster_name, gdc_project, mgmt_kubeconfig):
                common.print_error(f"Cluster '{cluster_name}' failed to reach Ready state.")
                sys.exit(1)

    # 4. Fetch/update standard cluster kubeconfig
    if not dry_run:
        if not (Path(target_kubeconfig).exists() and cluster_ready):
            ensure_cluster_credentials(cluster_name, gdc_project, target_kubeconfig)
        os.environ["KUBECONFIG"] = target_kubeconfig

    # 5. Check Node health and version on standard cluster
    if dry_run:
        common.print_info(f"[DRY-RUN] Would verify node readiness and default StorageClass on '{cluster_name}'.")
        return

    kc_env = ["--kubeconfig", target_kubeconfig] if Path(target_kubeconfig).exists() else []
    node_cmd = ["kubectl"] + kc_env + ["get", "nodes", "-o", "json"]
    code, out, err = common.run_command(node_cmd, check=False, capture_output=True)
    if code != 0:
        common.print_warning(f"Could not reach standard cluster nodes via '{target_kubeconfig}': {err or out}")
        return

    try:
        nodes_data = json.loads(out)
        nodes = nodes_data.get("items", [])
    except Exception as e:
        common.print_error(f"Failed to parse node information: {e}")
        nodes = []

    total_nodes = len(nodes)
    ready_nodes = 0
    k8s_versions = set()

    for node in nodes:
        conditions = node.get("status", {}).get("conditions", [])
        is_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
        if is_ready:
            ready_nodes += 1
        v = node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion")
        if v:
            k8s_versions.add(v)

    version_str = ", ".join(sorted(k8s_versions)) if k8s_versions else "unknown"

    # 6. Check StorageClass
    sc_cmd = ["kubectl"] + kc_env + ["get", "storageclass", "-o", "json"]
    sc_code, sc_out, _ = common.run_command(sc_cmd, check=False, capture_output=True)
    has_default_sc = False
    default_sc_name = "None"
    if sc_code == 0:
        try:
            sc_data = json.loads(sc_out)
            for sc in sc_data.get("items", []):
                name = sc.get("metadata", {}).get("name")
                annotations = sc.get("metadata", {}).get("annotations", {}) or {}
                if annotations.get("storageclass.kubernetes.io/is-default-class") == "true":
                    has_default_sc = True
                    default_sc_name = name
                    break
        except Exception:
            pass

    # 7. Formatted Cluster Health Summary Table
    if common.RICH_AVAILABLE:
        table = Table(title=f"GDC Cluster Readiness: [bold cyan]{cluster_name}[/bold cyan]", show_header=True)
        table.add_column("Component / Metric", style="cyan", width=30)
        table.add_column("Status / Value", style="bold green" if ready_nodes == total_nodes and total_nodes > 0 else "bold yellow")

        table.add_row("Cluster Reachability", "[bold green]ONLINE[/bold green]")
        table.add_row("Total Node Count", str(total_nodes))
        table.add_row("Ready Node Count", f"{ready_nodes} / {total_nodes} Ready")
        table.add_row("Kubernetes Version", version_str)
        table.add_row(
            "Default StorageClass",
            f"[bold green]{default_sc_name}[/bold green]" if has_default_sc else f"[bold yellow]{default_sc_name}[/bold yellow]"
        )
        table.add_row("Kubeconfig Path", target_kubeconfig)
        table.add_row("Specification Path", str(overlay_dir))

        common.console.print(table)
    else:
        print(f"Cluster: {cluster_name} (Status: ONLINE, Nodes: {ready_nodes}/{total_nodes} Ready, Version: {version_str}, StorageClass: {default_sc_name})")

    if ready_nodes == 0 or total_nodes == 0:
        common.print_warning(f"No nodes are ready yet in cluster '{cluster_name}'. Nodes may still be initializing.")
    else:
        common.print_success(f"GDC standard cluster '{cluster_name}' is fully ready and operational.")


def get_cluster_info(cluster_name: str, region: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Return cluster metadata for GDC."""
    return {
        "cluster_name": cluster_name,
        "cluster_type": "GDC Standard Cluster",
        "storage_class": "standard-rwo",
    }
