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

"""Prerequisites provider for Google Distributed Cloud (GDC) Sandbox."""

import os
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_required_env_vars() -> List[str]:
    """Return mandatory environment variables for GDC-Sandbox."""
    return ["CLUSTER_NAME"]


def check_prerequisites(verbose: bool = False, env_path: Optional[Path] = None) -> bool:
    """Check CLI dependencies and cluster reachability for GDC-Sandbox."""
    errors = []
    warnings = []
    checks = []

    # 1. Rich library check
    if common.RICH_AVAILABLE:
        checks.append(("[SUCCESS]", "Python 'rich' package is installed."))
    else:
        warnings.append("Python 'rich' package not found. (Install with: pip install rich)")

    # 2. python-gitlab check
    try:
        import gitlab  # noqa: F401
        checks.append(("[SUCCESS]", "Python 'python-gitlab' package is installed."))
    except ImportError:
        errors.append("Python 'python-gitlab' package not found. (Install with: pip install python-gitlab)")

    # 3. kubectl CLI check
    if common.check_tool_installed("kubectl"):
        checks.append(("[SUCCESS]", "kubectl CLI is installed."))
    else:
        errors.append("kubectl CLI is NOT installed. Please install kubectl.")

    # 4. gdcloud CLI check
    if common.check_tool_installed("gdcloud"):
        checks.append(("[SUCCESS]", "gdcloud CLI is installed."))
    else:
        warnings.append("gdcloud CLI not found. (Needed for fetching cluster credentials)")

    # 5. GDC Management plane check (for Phase 2 cluster creation)
    mgmt_kubeconfig = os.environ.get("GDC_MANAGEMENT_KUBECONFIG") or "/home/sandboxuser10/org-1-admin-kubeconfig"
    if mgmt_kubeconfig and Path(mgmt_kubeconfig).exists():
        checks.append(("[SUCCESS]", f"GDC Management KUBECONFIG found: '{mgmt_kubeconfig}'"))
    else:
        warnings.append(f"GDC Management KUBECONFIG not found at '{mgmt_kubeconfig}'.")

    # 6. Standard Cluster KUBECONFIG check
    kubeconfig = os.environ.get("KUBECONFIG")
    if kubeconfig and Path(kubeconfig).exists():
        checks.append(("[SUCCESS]", f"Standard cluster KUBECONFIG found: '{kubeconfig}'"))
        code, out, err = common.run_command(["kubectl", "cluster-info"], check=False, capture_output=True)
        if code == 0:
            checks.append(("[SUCCESS]", "Standard cluster Kubernetes API server is reachable."))
        else:
            warnings.append(f"Target cluster in KUBECONFIG is not yet reachable: {err or out} (Will be verified/connected in Phase 2)")
    else:
        checks.append(("[INFO]", f"Standard cluster KUBECONFIG '{kubeconfig}' does not exist yet. (Will be generated upon cluster provisioning in Phase 2)"))

    # 7. GDC Platform Admin Identity check
    platform_admin = os.environ.get("PLATFORM_ADMIN") or os.environ.get("GCP_PROJECT_OWNER")
    if platform_admin:
        checks.append(("[SUCCESS]", f"GDC Platform Admin identity: '{platform_admin}'"))
    else:
        warnings.append("PLATFORM_ADMIN or GCP_PROJECT_OWNER not specified in .env.")

    all_ok = len(errors) == 0

    if verbose:
        common.print_header("GDC Prerequisites Verification")
        for status, msg in checks:
            if status == "[SUCCESS]":
                common.print_success(msg)
            else:
                common.print_info(msg)
        for warn in warnings:
            common.print_warning(warn)
        for err in errors:
            common.print_error(err)
    elif not all_ok or warnings:
        if not all_ok:
            common.print_header("Prerequisites Issues Detected")
        for err in errors:
            common.print_error(err)
        for warn in warnings:
            common.print_warning(warn)

    return all_ok
