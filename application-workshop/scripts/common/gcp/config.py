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

"""GCP platform configuration provider for application-workshop."""

import os
from typing import Dict, List, Optional


class GCPConfig:
    """Strongly-typed runtime configuration for Google Cloud Platform (GCP)."""

    def __init__(
        self,
        env: Dict[str, str],
        cli_overrides: Optional[Dict[str, Optional[str]]] = None,
    ):
        overrides = cli_overrides or {}

        self.platform: str = "gcp"
        self.admin_email: str = (
            overrides.get("admin_email")
            or env.get("GCP_PROJECT_OWNER")
            or os.environ.get("GCP_PROJECT_OWNER")
            or ""
        ).strip()

        self.cluster_name: str = (
            overrides.get("cluster_name")
            or env.get("GKE_CLUSTER_NAME")
            or os.environ.get("GKE_CLUSTER_NAME")
            or "gitops-demo-cluster"
        ).strip()

        self.project_id: str = (
            overrides.get("project_id")
            or env.get("GCP_PROJECT")
            or os.environ.get("GCP_PROJECT")
            or ""
        ).strip()

        self.region: str = (
            overrides.get("region")
            or env.get("GCP_REGION")
            or os.environ.get("GCP_REGION")
            or "us-central1"
        ).strip()

        self.gar_repository: str = (
            env.get("GAR_REPOSITORY")
            or os.environ.get("GAR_REPOSITORY")
            or "gitops-workloads"
        ).strip()

        self.gitlab_group: str = (
            overrides.get("gitlab_group")
            or env.get("GITLAB_GROUP")
            or os.environ.get("GITLAB_GROUP")
            or "workloads"
        ).strip()

        self.gitlab_project: str = (
            overrides.get("gitlab_project")
            or env.get("GITLAB_PROJECT")
            or os.environ.get("GITLAB_PROJECT")
            or "translate-project"
        ).strip()

        self.app_name: str = (
            overrides.get("app_name")
            or env.get("APP_NAME")
            or os.environ.get("APP_NAME")
            or "translate-api"
        ).strip()

        self.app_image_tag: str = (
            overrides.get("app_image_tag")
            or env.get("APP_IMAGE_TAG")
            or os.environ.get("APP_IMAGE_TAG")
            or "v1.0.0"
        ).strip()

        self.argocd_server_url: str = (
            env.get("ARGOCD_SERVER_URL")
            or os.environ.get("ARGOCD_SERVER_URL")
            or "http://localhost:8080"
        ).strip()

        self.gitlab_http_url: str = (
            env.get("GITLAB_HTTP_URL")
            or os.environ.get("GITLAB_HTTP_URL")
            or "http://localhost:8081"
        ).strip()

        self.translate_api_key: str = (
            env.get("TRANSLATE_APP_API_KEY")
            or os.environ.get("TRANSLATE_APP_API_KEY")
            or "sample-key-12345"
        ).strip()

        self.keycloak_url: str = (
            env.get("KEYCLOAK_URL")
            or os.environ.get("KEYCLOAK_URL")
            or "http://keycloak:8080"
        ).strip()

        self.keycloak_realm: str = (
            env.get("KEYCLOAK_REALM")
            or os.environ.get("KEYCLOAK_REALM")
            or "sandbox"
        ).strip()

        self.required_vars: List[str] = ["GCP_PROJECT", "GCP_REGION", "GKE_CLUSTER_NAME"]
        self.raw_env: Dict[str, str] = env


def load_config(
    env: Dict[str, str], cli_overrides: Optional[Dict[str, Optional[str]]] = None
) -> GCPConfig:
    """Create and return a GCPConfig instance."""
    return GCPConfig(env, cli_overrides=cli_overrides)
