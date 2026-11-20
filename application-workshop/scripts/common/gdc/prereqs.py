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

"""Prerequisites provider for Google Distributed Cloud (GDC) in application-workshop."""

import os
from pathlib import Path
import sys
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_required_env_vars() -> List[str]:
    """Return mandatory environment variables for GDC."""
    return ["CLUSTER_NAME"]


def check_prerequisites(verbose: bool = False, env_path: Optional[Path] = None) -> bool:
    """Check all CLI dependencies and environment setup for GDC application deployment."""
    errors = []
    warnings = []
    checks = []

    if common.RICH_AVAILABLE:
        checks.append(("[SUCCESS]", "Python 'rich' package is installed."))
    else:
        warnings.append("Python 'rich' package not found. (Install with: pip install rich)")

    try:
        import gitlab  # noqa: F401
        checks.append(("[SUCCESS]", "Python 'python-gitlab' package is installed."))
    except ImportError:
        errors.append("Python 'python-gitlab' package not found. (Install with: pip install python-gitlab)")

    for tool_name, hint in [
        ("kubectl", "Please install kubectl."),
        ("docker", "Docker is required to build and push container images to Harbor."),
        ("git", "git is required to push manifests to GitLab."),
    ]:
        if common.check_tool_installed(tool_name):
            checks.append(("[SUCCESS]", f"{tool_name} CLI is installed."))
        else:
            errors.append(f"{tool_name} CLI is NOT installed. {hint}")

    if common.check_tool_installed("gdcloud"):
        checks.append(("[SUCCESS]", "gdcloud CLI is installed."))
    else:
        warnings.append("gdcloud CLI not found on PATH (relying on pre-configured KUBECONFIG and HARBOR_URL).")

    env_vars = common.load_dotenv(env_path)
    cluster_name = (env_vars.get("CLUSTER_NAME") or os.environ.get("CLUSTER_NAME") or "").strip()
    if cluster_name:
        checks.append(("[SUCCESS]", f"Target GDC cluster configured: '{cluster_name}'"))
        default_kc = Path.home() / ".kube" / f"gdc-{cluster_name}.kubeconfig"
        if default_kc.exists() and not os.environ.get("KUBECONFIG"):
            os.environ["KUBECONFIG"] = str(default_kc)
    else:
        errors.append("Missing required variable CLUSTER_NAME in .env.")

    if common.check_tool_installed("kubectl"):
        code, out, _ = common.run_command(
            ["kubectl", "config", "current-context"], check=False, capture_output=True
        )
        if code == 0 and out.strip():
            checks.append(("[SUCCESS]", f"Active kubectl context: '{out.strip()}'"))
        else:
            warnings.append("No active kubectl context detected. Ensure KUBECONFIG is set.")

    all_ok = len(errors) == 0

    if verbose:
        common.print_header("GDC Application Workshop Prerequisites Verification")
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
