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

"""Project and identity provider for Google Cloud Platform (GCP) in application-workshop."""

import os
from pathlib import Path
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_active_gcp_project(env_path: Optional[Path] = None) -> Optional[str]:
    """Retrieve GCP project ID from .env, environment variable, or gcloud config."""
    common.load_dotenv(env_path)
    env_proj = os.environ.get("GCP_PROJECT")
    if env_proj:
        return env_proj
    if not common.check_tool_installed("gcloud"):
        return None
    code, out, _ = common.run_command(
        ["gcloud", "config", "get-value", "project"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out.strip():
        project = out.strip().splitlines()[-1]
        if project and "(unset)" not in project:
            return project
    return None


def get_active_gcloud_user() -> Optional[str]:
    """Retrieve active authenticated user from gcloud config."""
    if not common.check_tool_installed("gcloud"):
        return None
    code, out, _ = common.run_command(
        ["gcloud", "config", "get-value", "account"],
        check=False,
        capture_output=True,
    )
    if code == 0 and out.strip():
        user = out.strip().splitlines()[-1]
        if user and "(unset)" not in user:
            return user
    return None


def get_active_identity() -> Optional[str]:
    """Return active authenticated GCP identity."""
    return get_active_gcloud_user()
