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

"""Platform adapter factory and dispatcher for gitops-workshop.

Decouples high-level orchestrator scripts from platform-specific implementations
(Google Cloud Platform vs. Google Distributed Cloud Sandbox).
"""

import os
import sys
from pathlib import Path
from typing import Dict, Literal, Optional


# Ensure scripts/common is on sys.path
common_dir = str(Path(__file__).resolve().parent)
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

PlatformType = Literal["gcp", "gdc"]


def get_target_platform(env_path: Optional[Path] = None) -> PlatformType:
    """Determine the active platform target ('gcp' or 'gdc'). Defaults to 'gcp'."""
    if env_path is not None and env_path.exists() and env_path.is_file():
        # Read directly from env file if present
        has_gcp_markers = False
        has_gdc_markers = False
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    if " #" in line:
                        line = line.split(" #", 1)[0].strip()
                    k, v = line.split("=", 1)
                    k_clean = k.strip()
                    if k_clean == "TARGET_PLATFORM":
                        return v.strip().strip("'\"").lower()  # type: ignore
                    if k_clean.startswith("GCP_") or k_clean.startswith("GKE_"):
                        has_gcp_markers = True
                    elif k_clean.startswith("GDC_"):
                        has_gdc_markers = True
        except Exception:
            pass

        if has_gdc_markers and not has_gcp_markers:
            return "gdc"
        if has_gcp_markers and not has_gdc_markers:
            return "gcp"

    return os.environ.get("TARGET_PLATFORM", "gcp").strip().lower()  # type: ignore


def get_prereqs_provider(platform: Optional[str] = None):
    """Return the prerequisites provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import prereqs
        except (ImportError, ValueError):
            from gdc import prereqs
        return prereqs
    try:
        from .gcp import prereqs
    except (ImportError, ValueError):
        from gcp import prereqs
    return prereqs


def get_project_provider(platform: Optional[str] = None):
    """Return the project & environment provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import project
        except (ImportError, ValueError):
            from gdc import project
        return project
    try:
        from .gcp import project
    except (ImportError, ValueError):
        from gcp import project
    return project


def get_cluster_provider(platform: Optional[str] = None):
    """Return the cluster lifecycle provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import cluster
        except (ImportError, ValueError):
            from gdc import cluster
        return cluster
    try:
        from .gcp import cluster
    except (ImportError, ValueError):
        from gcp import cluster
    return cluster


def get_registry_provider(platform: Optional[str] = None):
    """Return the container registry & image provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import registry
        except (ImportError, ValueError):
            from gdc import registry
        return registry
    try:
        from .gcp import registry
    except (ImportError, ValueError):
        from gcp import registry
    return registry


def get_auth_provider(platform: Optional[str] = None):
    """Return the identity & authentication provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import auth
        except (ImportError, ValueError):
            from gdc import auth
        return auth
    try:
        from .gcp import auth
    except (ImportError, ValueError):
        from gcp import auth
    return auth


def get_cleanup_provider(platform: Optional[str] = None):
    """Return the teardown & cleanup provider for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import cleanup
        except (ImportError, ValueError):
            from gdc import cleanup
        return cleanup
    try:
        from .gcp import cleanup
    except (ImportError, ValueError):
        from gcp import cleanup
    return cleanup


def get_config_provider(platform: Optional[str] = None):
    """Return the configuration provider module for the active platform."""
    plat = platform or get_target_platform()
    if plat == "gdc":
        try:
            from .gdc import config
        except (ImportError, ValueError):
            from gdc import config
        return config
    try:
        from .gcp import config
    except (ImportError, ValueError):
        from gcp import config
    return config


def get_config(
    env_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Optional[str]]] = None
):
    """Resolve active platform configuration from environment file and CLI overrides."""
    plat = get_target_platform(env_path)
    target_env = env_path or (Path.cwd() / ".env")
    env_dict = {}
    if target_env.exists() and target_env.is_file():
        try:
            import common
            env_dict = common.load_dotenv(target_env)
        except Exception:
            pass

    provider = get_config_provider(plat)
    return provider.load_config(env_dict, cli_overrides=cli_overrides)

