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

"""Container registry and image resolution provider for Google Cloud Platform (GCP)."""

from pathlib import Path
from typing import Optional


def resolve_image(component: str, default_upstream: str) -> str:
    """Resolve container image reference for GCP (returns standard upstream public image)."""
    return default_upstream


def ensure_image_pull_secret(namespace: str, service_account: Optional[str] = None, dry_run: bool = False) -> None:
    """Ensure image pull secret exists in namespace for GCP (no-op for public registries)."""
    pass


def prepare_argocd_kustomization(manifest_dir: Path) -> Path:
    """Return path to ArgoCD Kustomization directory or manifest for GCP."""
    return manifest_dir


def prepare_gitlab_kustomization(manifest_dir: Path) -> Path:
    """Return path to GitLab Kustomization directory or manifest for GCP."""
    return manifest_dir

