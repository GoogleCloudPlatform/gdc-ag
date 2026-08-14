#!/usr/bin/env python3

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
provision-rbac.py
-----------------
Production-grade automation script for GDC Platform Administrators to bulk-apply
Keycloak OIDC identity group mappings, custom ClusterRoles, RoleBindings, and
CI/CD ServiceAccount tokens across multi-tenant namespaces.
"""

import argparse
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
import yaml


class TerminalColor:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{TerminalColor.CYAN}[INFO]{TerminalColor.RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{TerminalColor.GREEN}[SUCCESS]{TerminalColor.RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{TerminalColor.YELLOW}[WARN]{TerminalColor.RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{TerminalColor.RED}[ERROR]{TerminalColor.RESET} {msg}", file=sys.stderr)


def load_custom_roles(manifest_path: str) -> List[Dict[str, Any]]:
    """Loads ClusterRole definitions from 01-custom-roles.yaml."""
    if not os.path.exists(manifest_path):
        log_warn(f"Custom roles manifest not found at {manifest_path}. Skipping automatic ClusterRole loading.")
        return []
    with open(manifest_path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    return [d for d in docs if d and isinstance(d, dict)]


def build_rolebindings_and_sas(tenant: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Constructs RoleBinding, ServiceAccount, and Secret manifests for a given tenant configuration.
    """
    ns = tenant["namespace"]
    manifests: List[Dict[str, Any]] = []

    # Process RoleBindings
    for rb in tenant.get("roleBindings", []):
        role_name = rb["role"]
        binding_name = rb.get("bindingName", f"{ns}-{role_name}-binding")
        subjects: List[Dict[str, str]] = []

        for grp in rb.get("groups", []):
            subjects.append({
                "kind": "Group",
                "name": str(grp),
                "apiGroup": "rbac.authorization.k8s.io",
            })
        for usr in rb.get("users", []):
            subjects.append({
                "kind": "User",
                "name": str(usr),
                "apiGroup": "rbac.authorization.k8s.io",
            })

        rb_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": binding_name,
                "namespace": ns,
                "labels": {
                    "gdc.google.com/tenant": ns.split("-")[0],
                    "app.kubernetes.io/managed-by": "gdc-rbac-provisioner",
                },
            },
            "subjects": subjects,
            "roleRef": {
                "kind": "ClusterRole",
                "name": role_name,
                "apiGroup": "rbac.authorization.k8s.io",
            },
        }
        manifests.append(rb_manifest)

    # Process ServiceAccounts and Tokens
    for sa in tenant.get("serviceAccounts", []):
        sa_name = sa["name"]
        pipeline = sa.get("pipeline", "ci-cd")
        role_name = sa.get("role", "gdc-cicd-deployer-role")

        # 1. ServiceAccount
        sa_manifest = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": sa_name,
                "namespace": ns,
                "labels": {
                    "gdc.google.com/pipeline": pipeline,
                    "app.kubernetes.io/managed-by": "gdc-rbac-provisioner",
                },
            },
        }
        manifests.append(sa_manifest)

        # 2. Token Secret
        if sa.get("createTokenSecret", True):
            secret_manifest = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": f"{sa_name}-token",
                    "namespace": ns,
                    "annotations": {
                        "kubernetes.io/service-account.name": sa_name,
                    },
                    "labels": {
                        "gdc.google.com/pipeline": pipeline,
                    },
                },
                "type": "kubernetes.io/service-account-token",
            }
            manifests.append(secret_manifest)

        # 3. RoleBinding for ServiceAccount
        sa_binding_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": f"{sa_name}-{ns}-binding",
                "namespace": ns,
                "labels": {
                    "gdc.google.com/pipeline": pipeline,
                    "app.kubernetes.io/managed-by": "gdc-rbac-provisioner",
                },
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": sa_name,
                    "namespace": ns,
                }
            ],
            "roleRef": {
                "kind": "ClusterRole",
                "name": role_name,
                "apiGroup": "rbac.authorization.k8s.io",
            },
        }
        manifests.append(sa_binding_manifest)

    return manifests


def apply_manifests(manifests: List[Dict[str, Any]], kubeconfig: Optional[str], dry_run: bool) -> bool:
    """Serializes manifests to YAML and submits them to kubectl apply."""
    yaml_docs = yaml.dump_all(manifests, sort_keys=False)

    if dry_run:
        print(f"\n{TerminalColor.BOLD}=== [DRY-RUN] RBAC Manifest Output ==={TerminalColor.RESET}")
        print(yaml_docs)
        print(f"{TerminalColor.BOLD}=== End of RBAC Manifest Output ==={TerminalColor.RESET}\n")
        return True

    cmd = ["kubectl", "apply", "-f", "-"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])

    try:
        proc = subprocess.run(
            cmd,
            input=yaml_docs,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().splitlines():
                log_success(line)
            return True
        else:
            log_error(f"kubectl apply failed with exit code {proc.returncode}")
            print(proc.stderr, file=sys.stderr)
            return False
    except FileNotFoundError:
        log_error("kubectl binary not found in PATH.")
        return False


def print_summary_matrix(tenants: List[Dict[str, Any]]) -> None:
    """Prints an identity mapping summary table."""
    print(f"\n{TerminalColor.BOLD}📋 RBAC Provisioning Governance Matrix:{TerminalColor.RESET}")
    print(f"{'NAMESPACE':<16} {'BINDING NAME':<34} {'ROLE':<24} {'SUBJECTS'}")
    print("-" * 105)
    for t in tenants:
        ns = t["namespace"]
        for rb in t.get("roleBindings", []):
            b_name = rb.get("bindingName", f"{ns}-{rb['role']}")
            role = rb["role"]
            subs = []
            for g in rb.get("groups", []):
                subs.append(f"Group:{g}")
            for u in rb.get("users", []):
                subs.append(f"User:{u}")
            print(f"{ns:<16} {b_name:<34} {role:<24} {', '.join(subs)}")
        for sa in t.get("serviceAccounts", []):
            b_name = f"{sa['name']}-{ns}-binding"
            role = sa.get("role", "gdc-cicd-deployer-role")
            print(f"{ns:<16} {b_name:<34} {role:<24} ServiceAccount:{sa['name']}")
    print("-" * 105 + "\n")


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    roles_path_default = os.path.join(script_dir, "..", "manifests", "01-custom-roles.yaml")
    config_path_default = os.path.join(script_dir, "identity_mappings.yaml")

    parser = argparse.ArgumentParser(
        description="GDC Platform Administrator: Bulk-Provision RBAC & Keycloak OIDC Mappings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        default=config_path_default,
        help="Path to identity_mappings.yaml configuration file",
    )
    parser.add_argument(
        "--roles-manifest",
        "-r",
        default=roles_path_default,
        help="Path to 01-custom-roles.yaml ClusterRole definitions",
    )
    parser.add_argument(
        "--kubeconfig",
        "-k",
        default=os.getenv("KUBECONFIG"),
        help="Path to cluster kubeconfig file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and render generated Kubernetes RBAC manifests without applying them",
    )
    parser.add_argument(
        "--namespace",
        "-n",
        help="Filter and apply RBAC only for a specific tenant namespace",
    )

    args = parser.parse_args()

    print(f"{TerminalColor.BOLD}================================================================={TerminalColor.RESET}")
    print(f"{TerminalColor.BOLD}🛡️ GDC Air-Gapped RBAC & Identity Mapping Provisioner{TerminalColor.RESET}")
    print(f"{TerminalColor.BOLD}================================================================={TerminalColor.RESET}")
    log_info(f"Loading identity mappings from: {args.config}")

    if not os.path.exists(args.config):
        log_error(f"Configuration file not found: {args.config}")
        sys.exit(1)

    try:
        with open(args.config, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as ex:
        log_error(f"Failed to parse YAML configuration: {ex}")
        sys.exit(1)

    tenants = config_data.get("tenants", [])
    if not tenants:
        log_error("No 'tenants' found in identity configuration.")
        sys.exit(1)

    if args.namespace:
        tenants = [t for t in tenants if t.get("namespace") == args.namespace]
        if not tenants:
            log_error(f"Namespace '{args.namespace}' not found in configuration.")
            sys.exit(1)

    # 1. Load ClusterRoles
    all_manifests: List[Dict[str, Any]] = []
    if os.path.exists(args.roles_manifest):
        log_info(f"Loading custom ClusterRoles from: {args.roles_manifest}")
        custom_roles = load_custom_roles(args.roles_manifest)
        all_manifests.extend(custom_roles)
        log_info(f"Loaded {len(custom_roles)} ClusterRole definitions.")

    # 2. Build RoleBindings and ServiceAccounts
    log_info("Generating RoleBindings, ServiceAccounts, and Token Secrets for tenants...")
    for t in tenants:
        tenant_manifests = build_rolebindings_and_sas(t)
        all_manifests.extend(tenant_manifests)

    log_info(f"Total manifests to apply: {len(all_manifests)}")
    print_summary_matrix(tenants)

    if args.dry_run:
        log_warn("Running in DRY-RUN mode. No cluster modifications will be made.")
    else:
        log_info("Applying RBAC and ServiceAccount manifests to GDC cluster...")

    success = apply_manifests(all_manifests, args.kubeconfig, args.dry_run)
    if not success:
        log_error("RBAC provisioning encountered errors.")
        sys.exit(1)

    if not args.dry_run:
        print(f"\n{TerminalColor.GREEN}{TerminalColor.BOLD}🎉 RBAC and Identity Mappings successfully applied!{TerminalColor.RESET}")
        print(f"Run `./test-permissions.sh` to test permissions and tenant isolation.\n")


if __name__ == "__main__":
    main()
