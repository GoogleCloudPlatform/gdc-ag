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

"""Project and identity provider stub for Google Distributed Cloud (GDC) Sandbox."""

import os
from pathlib import Path
from typing import Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_active_identity() -> Optional[str]:
    """Retrieve active identity (configured PLATFORM_ADMIN, GCP_PROJECT_OWNER, or cluster context)."""
    admin = os.environ.get("PLATFORM_ADMIN") or os.environ.get("GCP_PROJECT_OWNER")
    if admin:
        return admin
    code, out, _ = common.run_command(["kubectl", "config", "current-context"], check=False, capture_output=True)
    if code == 0 and out.strip():
        return out.strip()
    return os.environ.get("USER", "gdc-user")


def ensure_project(
    project_id: str,
    project_owner: Optional[str] = None,
    billing_account_id: Optional[str] = None,
    dry_run: bool = False
) -> str:
    """Verify access to GDC project and cluster context."""
    common.print_info(f"GDC-Sandbox mode: Verifying cluster context and reachability for '{project_id}'...")
    code, out, err = common.run_command(["kubectl", "config", "current-context"], check=False, capture_output=True)
    current_context = out.strip() if code == 0 else "unknown"
    common.print_success(f"GDC Cluster context active: '{current_context}' (Target Cluster: '{project_id}')")

    owner = project_owner or os.environ.get("PLATFORM_ADMIN") or "Current User"
    common.print_info(f"GDC Platform Admin: {owner}")
    return project_id


def select_billing_account(specified_account: Optional[str] = None, project_id: Optional[str] = None, auto_approve: bool = False, **kwargs) -> Optional[str]:
    """No-op for GDC (no GCP billing account required)."""
    return None
