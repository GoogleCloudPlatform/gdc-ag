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

"""GDC platform configuration provider."""

import os
from pathlib import Path
from typing import Dict, List, Optional


class GDCConfig:
    """Strongly-typed runtime configuration for Google Distributed Cloud (GDC)."""

    def __init__(self, env: Dict[str, str], cli_overrides: Optional[Dict[str, Optional[str]]] = None):
        overrides = cli_overrides or {}

        self.platform: str = "gdc"
        self.admin_email: str = (
            overrides.get("admin_email")
            or env.get("PLATFORM_ADMIN")
            or os.environ.get("PLATFORM_ADMIN")
            or "platform-admin@example.com"
        ).strip()

        self.cluster_name: str = (
            overrides.get("cluster_name")
            or env.get("CLUSTER_NAME")
            or os.environ.get("CLUSTER_NAME")
            or "gitops-platform1"
        ).strip()

        self.project_id: str = (
            overrides.get("project_id")
            or env.get("GDC_PROJECT_ID")
            or os.environ.get("GDC_PROJECT_ID")
            or "project-lowhigh"
        ).strip()

        self.region: str = "n/a"

        self.kubeconfig_path: str = (
            overrides.get("kubeconfig_path")
            or env.get("KUBECONFIG")
            or os.environ.get("KUBECONFIG")
            or f"/home/sandboxuser10/{self.cluster_name}-kubeconfig"
        ).strip()

        self.management_kubeconfig: str = (
            env.get("GDC_MANAGEMENT_KUBECONFIG")
            or os.environ.get("GDC_MANAGEMENT_KUBECONFIG")
            or "/home/sandboxuser10/org-1-admin-kubeconfig"
        ).strip()

        self.argocd_server_url: str = (
            env.get("ARGOCD_SERVER_URL")
            or os.environ.get("ARGOCD_SERVER_URL")
            or "https://localhost:8088"
        ).strip()

        self.gitlab_http_url: str = (
            env.get("GITLAB_HTTP_URL")
            or os.environ.get("GITLAB_HTTP_URL")
            or "http://localhost:8081"
        ).strip()

        self.harbor_url: str = (
            env.get("HARBOR_URL")
            or os.environ.get("HARBOR_URL")
            or ""
        ).strip()

        self.auth_mode: str = (
            env.get("AUTH_MODE")
            or os.environ.get("AUTH_MODE")
            or "oidc"
        ).strip()

        self.required_vars: List[str] = ["CLUSTER_NAME", "PLATFORM_ADMIN"]
        self.gitlab_required_vars: List[str] = ["PLATFORM_ADMIN", "GITLAB_HTTP_URL"]
        self.raw_env: Dict[str, str] = env


def load_config(env: Dict[str, str], cli_overrides: Optional[Dict[str, Optional[str]]] = None) -> GDCConfig:
    """Create and return a GDCConfig instance."""
    return GDCConfig(env, cli_overrides=cli_overrides)
