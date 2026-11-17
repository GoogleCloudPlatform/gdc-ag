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

"""Platform adapter factory for application-workshop.

Resolves the active target platform ('gcp' or 'gdc') and dynamically loads
the corresponding provider modules for prerequisites, project context, and container registry.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import common


def get_target_platform(env_path: Optional[Path] = None) -> str:
    """Resolve TARGET_PLATFORM from .env or environment variables (defaults to 'gcp')."""
    common.load_dotenv(env_path)
    platform = os.environ.get("TARGET_PLATFORM", "gcp").strip().lower()
    if platform not in ("gcp", "gdc"):
        common.print_warning(
            f"Unrecognized TARGET_PLATFORM='{platform}'. Defaulting to 'gcp'."
        )
        return "gcp"
    return platform


def get_config(
    env_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Any:
    """Return strongly-typed configuration object for the active platform."""
    env = common.load_dotenv(env_path)
    platform = (cli_overrides or {}).get("platform") or get_target_platform(env_path)
    if platform == "gdc":
        from gdc import config as gdc_config
        return gdc_config.load_config(env, cli_overrides=cli_overrides)
    from gcp import config as gcp_config
    return gcp_config.load_config(env, cli_overrides=cli_overrides)


def get_prereqs_provider(platform: Optional[str] = None):
    """Return prerequisites provider module for the target platform."""
    target = (platform or get_target_platform()).lower()
    if target == "gdc":
        from gdc import prereqs as gdc_prereqs
        return gdc_prereqs
    from gcp import prereqs as gcp_prereqs
    return gcp_prereqs


def get_project_provider(platform: Optional[str] = None):
    """Return project/identity provider module for the target platform."""
    target = (platform or get_target_platform()).lower()
    if target == "gdc":
        from gdc import project as gdc_project
        return gdc_project
    from gcp import project as gcp_project
    return gcp_project


def get_registry_provider(platform: Optional[str] = None):
    """Return container registry provider module for the target platform."""
    target = (platform or get_target_platform()).lower()
    if target == "gdc":
        from gdc import registry as gdc_registry
        return gdc_registry
    from gcp import registry as gcp_registry
    return gcp_registry
