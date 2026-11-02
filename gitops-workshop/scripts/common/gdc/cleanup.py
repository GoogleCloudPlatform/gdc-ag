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

"""Teardown and cleanup provider for Google Distributed Cloud (GDC) Sandbox."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common

SYSTEM_NAMESPACES = {
    "default",
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "cert-manager",
    "file",
    "file-kubevirt-tenant",
    "file-system",
    "gke-managed-metrics-server",
    "gpc-system",
    "iam-system",
    "kubevirt-csi-driver",
    "mks-system",
    "mon-system",
    "obs-system",
    "oclcm-system",
    "rm-system",
    "unet-system",
}


def discover_workload_namespaces() -> Set[str]:
    """Discover tenant workload namespaces managed by ArgoCD."""
    discovered: Set[str] = set()
    code, out, _ = common.run_command(
        ["kubectl", "get", "applications", "-n", "argocd", "-o", "jsonpath={range .items[*]}{.spec.destination.namespace}{\"\\n\"}{end}"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out.strip():
        for line in out.strip().splitlines():
            ns = line.strip()
            if ns and ns not in SYSTEM_NAMESPACES and ns not in ("argocd", "gitlab"):
                discovered.add(ns)

    # Check for known workshop tenant namespaces if any exist in cluster
    known_tenants = ["frontend", "workloads"]
    for kt in known_tenants:
        check_code, _, _ = common.run_command(
            ["kubectl", "get", "namespace", kt], check=False, capture_output=True
        )
        if check_code == 0:
            discovered.add(kt)

    return discovered


def strip_argocd_application_finalizers():
    """Remove finalizers from ArgoCD applications to prevent namespace termination hangs."""
    common.print_info("Removing finalizers from ArgoCD applications...")
    code, out, _ = common.run_command(
        ["kubectl", "get", "applications", "-n", "argocd", "-o", "jsonpath={.items[*].metadata.name}"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out.strip():
        apps = out.strip().split()
        for app in apps:
            common.run_command(
                ["kubectl", "patch", "application", app, "-n", "argocd", "--type=merge", "-p", '{"metadata":{"finalizers":null}}'],
                check=False,
                capture_output=True,
            )
        common.run_command(
            ["kubectl", "delete", "applications", "-n", "argocd", "--all", "--timeout=30s"],
            check=False,
            capture_output=True,
        )
        common.print_success(f"Cleaned up {len(apps)} ArgoCD Application CR(s).")


def strip_argocd_appproject_finalizers():
    """Remove finalizers from custom ArgoCD AppProjects."""
    code, out, _ = common.run_command(
        ["kubectl", "get", "appprojects", "-n", "argocd", "-o", "jsonpath={.items[*].metadata.name}"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out.strip():
        projects = [p for p in out.strip().split() if p != "default"]
        for p in projects:
            common.run_command(
                ["kubectl", "patch", "appproject", p, "-n", "argocd", "--type=merge", "-p", '{"metadata":{"finalizers":null}}'],
                check=False,
                capture_output=True,
            )
        if projects:
            common.run_command(
                ["kubectl", "delete", "appprojects", "-n", "argocd"] + projects + ["--timeout=30s"],
                check=False,
                capture_output=True,
            )


def delete_cluster_scoped_resources():
    """Remove workshop-specific ClusterRoles, ClusterRoleBindings, and CRDs."""
    common.print_header("Step 6: Purge Cluster-Scoped Workshop Resources")
    resources = [
        ("clusterrolebinding", ["argocd-application-controller", "argocd-applicationset-controller", "argocd-server"]),
        ("clusterrole", ["argocd-application-controller", "argocd-applicationset-controller", "argocd-server"]),
        ("crd", ["applications.argoproj.io", "applicationsets.argoproj.io", "appprojects.argoproj.io"]),
    ]
    for kind, names in resources:
        for name in names:
            common.run_command(
                ["kubectl", "delete", kind, name, "--ignore-not-found=true"],
                check=False,
                capture_output=True,
            )
    common.print_success("Cluster-scoped workshop resources (ClusterRoles, Bindings, CRDs) purged.")


def teardown_platform(
    project: Optional[str] = None,
    cluster_name: Optional[str] = None,
    region: Optional[str] = None,
    network_name: Optional[str] = None,
    delete_project: bool = False,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> bool:
    """Tear down workshop namespaces (argocd, gitlab, workloads) in GDC-Sandbox without deleting cluster."""
    common.print_header("GDC-Sandbox Workshop Teardown")

    target_cluster = cluster_name or "lowhigh-dev"

    # 1. Discover namespaces to delete
    tenant_namespaces = discover_workload_namespaces()
    core_namespaces = ["argocd", "gitlab"]
    all_target_namespaces = list(tenant_namespaces) + core_namespaces

    common.print_info(f"Target GDC Cluster: [bold cyan]{target_cluster}[/bold cyan]")
    common.print_info(f"Namespaces to be purged: [bold yellow]{', '.join(all_target_namespaces)}[/bold yellow]")

    if dry_run:
        common.print_warning("Running in DRY-RUN mode. No cluster resources will be deleted.")
        for ns in all_target_namespaces:
            common.print_info(f"[DRY-RUN] Would delete namespace '{ns}'")
        common.print_info("[DRY-RUN] Would delete cluster-scoped ArgoCD ClusterRoles, ClusterRoleBindings, and CRDs.")
        return False

    # 2. Confirmation prompt
    prompt_msg = f"Are you sure you want to delete all workshop namespaces ({', '.join(all_target_namespaces)}) from '{target_cluster}'?"
    if not common.confirm_action(prompt_msg, auto_approve=auto_approve):
        common.print_info("Teardown cancelled by user.")
        return False

    # 3. Terminate local port-forwards
    common.print_header("Step 1: Terminate Local Port-Forwards")
    common.run_command(["pkill", "-f", "kubectl port-forward"], description="Terminating active port-forward processes", check=False)
    for pat in ["pf-*.log", "*-pf.log", "*port-forward*.log"]:
        for log_file in Path("/tmp").glob(pat):
            try:
                log_file.unlink(missing_ok=True)
            except Exception:
                pass
    common.print_success("Local port-forward processes terminated.")

    # 4. Strip ArgoCD Application finalizers to avoid namespace termination hang
    common.print_header("Step 2: Remove ArgoCD Application & Project Resources")
    strip_argocd_application_finalizers()
    strip_argocd_appproject_finalizers()

    # 5. Delete tenant workload namespaces
    if tenant_namespaces:
        common.print_header("Step 3: Delete Tenant Workload Namespaces")
        for tns in tenant_namespaces:
            common.print_info(f"Deleting workload namespace '{tns}'...")
            common.run_command(["kubectl", "delete", "namespace", tns, "--ignore-not-found=true"], check=False)
        common.print_success("Tenant workload namespaces deleted.")

    # 6. Delete core platform namespaces (argocd, gitlab)
    common.print_header("Step 4: Delete Core Platform Namespaces")
    for ns in core_namespaces:
        common.print_info(f"Deleting platform namespace '{ns}' (PVCs and storage will be released)...")
        common.run_command(["kubectl", "delete", "namespace", ns, "--ignore-not-found=true"], check=False)

    # 7. Wait for namespaces to terminate
    common.print_header("Step 5: Waiting for Namespace Deletion")
    start_time = time.time()
    timeout = 180
    pending = set(all_target_namespaces)

    while time.time() - start_time < timeout and pending:
        still_existing = set()
        for ns in list(pending):
            c, out, _ = common.run_command(["kubectl", "get", "namespace", ns], check=False, capture_output=True)
            if c == 0:
                still_existing.add(ns)
        pending = still_existing
        if not pending:
            break
        common.print_info(f"Waiting for namespaces to terminate: {', '.join(pending)}... ({int(time.time() - start_time)}s elapsed)")
        time.sleep(5)

    if pending:
        common.print_warning(f"Namespaces still terminating after {timeout}s: {', '.join(pending)}")
    else:
        common.print_success(f"All workshop namespaces ({', '.join(all_target_namespaces)}) successfully deleted.")

    # 8. Delete cluster-scoped resources (ClusterRoles, ClusterRoleBindings, CRDs)
    delete_cluster_scoped_resources()

    common.print_success(f"GDC standard cluster '{target_cluster}' is reset to a clean baseline.")
    return False
