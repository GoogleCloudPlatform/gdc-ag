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

"""Prerequisites provider for Google Cloud Platform (GCP) in application-workshop."""

from pathlib import Path
import sys
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_required_env_vars() -> List[str]:
    """Return mandatory environment variables for GCP."""
    return ["GCP_PROJECT", "GCP_REGION", "GKE_CLUSTER_NAME"]


def check_prerequisites(verbose: bool = False, env_path: Optional[Path] = None) -> bool:
    """Check all CLI dependencies and environment setup for GCP application deployment."""
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
        ("gcloud", "Please install Google Cloud SDK."),
        ("kubectl", "Please install kubectl."),
        ("docker", "Docker is required to build and push container images to Artifact Registry."),
        ("git", "git is required to push manifests to GitLab."),
    ]:
        if common.check_tool_installed(tool_name):
            checks.append(("[SUCCESS]", f"{tool_name} CLI is installed."))
        else:
            errors.append(f"{tool_name} CLI is NOT installed. {hint}")

    from .project import get_active_gcp_project, get_active_gcloud_user
    project = get_active_gcp_project(env_path)
    if project:
        checks.append(("[SUCCESS]", f"Active GCP Project configured: '{project}'"))
    else:
        warnings.append("No GCP_PROJECT configured in .env or gcloud config.")

    user = get_active_gcloud_user()
    if user:
        checks.append(("[SUCCESS]", f"Active gcloud User: '{user}'"))
    else:
        errors.append("No active gcloud user authenticated. (Run: gcloud auth login)")

    if common.check_tool_installed("kubectl"):
        code, out, _ = common.run_command(
            ["kubectl", "config", "current-context"], check=False, capture_output=True
        )
        if code == 0 and out.strip():
            checks.append(("[SUCCESS]", f"Active kubectl context: '{out.strip()}'"))

    all_ok = len(errors) == 0

    if verbose:
        common.print_header("GCP Application Workshop Prerequisites Verification")
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
