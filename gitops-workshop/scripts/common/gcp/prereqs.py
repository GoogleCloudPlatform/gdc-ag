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

"""Prerequisites provider for Google Cloud Platform (GCP)."""

import shutil
from typing import List, Optional
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_required_env_vars() -> List[str]:
    """Return the list of mandatory environment variables for GCP."""
    return ["GCP_PROJECT", "GCP_REGION", "GKE_CLUSTER_NAME", "GCP_PROJECT_OWNER"]


def check_prerequisites(verbose: bool = False, env_path: Optional[Path] = None) -> bool:
    """Check all CLI dependencies and environment setup for GCP."""
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

    # 3. gcloud CLI check
    if common.check_tool_installed("gcloud"):
        checks.append(("[SUCCESS]", "gcloud CLI is installed."))
    else:
        errors.append("gcloud CLI is NOT installed. Please install Google Cloud SDK.")

    # 4. kubectl CLI check
    if common.check_tool_installed("kubectl"):
        checks.append(("[SUCCESS]", "kubectl CLI is installed."))
    else:
        errors.append("kubectl CLI is NOT installed. Please install kubectl.")

    # 5. gke-gcloud-auth-plugin CLI check
    if common.check_tool_installed("gke-gcloud-auth-plugin"):
        checks.append(("[SUCCESS]", "gke-gcloud-auth-plugin is installed."))
    else:
        errors.append(
            "gke-gcloud-auth-plugin is NOT installed (required for GKE cluster authentication).\n"
            "  -> Fix: Run 'gcloud components install gke-gcloud-auth-plugin' (or sudo apt install google-cloud-cli-gke-gcloud-auth-plugin)"
        )

    # 6. GCP Project check
    from .project import get_active_gcp_project, get_active_gcloud_user
    project = get_active_gcp_project(env_path)
    if project:
        checks.append(("[SUCCESS]", f"Active GCP Project configured: '{project}'"))
    else:
        checks.append(("[INFO]", "No GCP Project configured in .env or gcloud. (Will be created on bootstrap)"))

    # 7. Active gcloud User & Session Token check
    user = get_active_gcloud_user()
    if user:
        checks.append(("[SUCCESS]", f"Active gcloud User: '{user}'"))
        code, _, _ = common.run_command(["gcloud", "auth", "print-access-token"], check=False, capture_output=True)
        if code != 0:
            errors.append(
                f"Active gcloud user session for '{user}' is expired or requires re-authentication.\n"
                f"  -> Fix: Run 'gcloud auth login {user}'"
            )
        else:
            checks.append(("[SUCCESS]", "Active gcloud user session token is valid."))
    else:
        errors.append("No active gcloud user authenticated. (Run: gcloud auth login)")

    # 8. Application Default Credentials (ADC) check
    code, _, _ = common.run_command(["gcloud", "auth", "application-default", "print-access-token"], check=False, capture_output=True)
    if code != 0:
        errors.append(
            "Application Default Credentials (ADC) are expired or not configured (required for GKE / kubectl authentication).\n"
            "  -> Fix: Run 'gcloud auth application-default login'"
        )
    else:
        checks.append(("[SUCCESS]", "Application Default Credentials (ADC) are valid."))

    # 9. Active kubectl Context check (if configured)
    if common.check_tool_installed("kubectl"):
        code, out, _ = common.run_command(["kubectl", "config", "current-context"], check=False, capture_output=True)
        if code == 0 and out.strip():
            checks.append(("[SUCCESS]", f"Active kubectl context: '{out.strip()}'"))

    all_ok = len(errors) == 0

    if verbose:
        common.print_header("GCP Prerequisites Verification")
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
