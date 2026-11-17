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

"""Step 1: Build Application Images & Push to Registry (Cross-Domain Transfer).

Automatically discovers all Dockerfiles under apps/<app-name>/ (supporting both
single-image workloads like apps/<app>/app/Dockerfile and multi-service workloads
like apps/<app>/frontend/Dockerfile + apps/<app>/api/Dockerfile), builds and
pushes each image (<service>:<tag>) to Harbor or Artifact Registry, configures
the workload namespace pull secret, and stages .deployed-manifests/<app-name>/.
"""

import argparse
import os
from pathlib import Path
import shutil
import sys
from typing import Dict, List, Optional, Tuple

# Add scripts/common directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent / "common"))
from common import (
    RICH_AVAILABLE,
    confirm_action,
    load_dotenv,
    print_error,
    print_header,
    print_info,
    print_parameter_summary,
    print_success,
    validate_required_env_vars,
)
from platform_adapter import (
    get_config,
    get_prereqs_provider,
    get_project_provider,
    get_registry_provider,
    get_target_platform,
)

if RICH_AVAILABLE:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel

    console = Console()


def discover_app_dockerfiles(app_root: Path) -> List[Tuple[str, Path]]:
    """Search apps/<app_name>/ for Dockerfiles and return [(image_name, build_context_dir), ...].

    - If a Dockerfile lives in apps/<app_name>/Dockerfile or apps/<app_name>/app/Dockerfile,
      its image name defaults to <app_name>.
    - If a Dockerfile lives in a service subfolder (e.g. apps/<app_name>/frontend/Dockerfile
      or apps/<app_name>/api/Dockerfile), its image name is the service folder name
      (e.g. 'frontend', 'api').
    """
    if not app_root.exists():
        return []

    ignored_dirs = {"manifests", "node_modules", ".git", "__pycache__", "dist"}
    discovered: List[Tuple[str, Path]] = []

    for df_path in sorted(app_root.rglob("Dockerfile")):
        rel_parts = df_path.relative_to(app_root).parts
        if any(part in ignored_dirs for part in rel_parts):
            continue
        service_dir = df_path.parent
        if service_dir == app_root or service_dir.name == "app":
            image_name = app_root.name
        else:
            image_name = service_dir.name
        discovered.append((image_name, service_dir))

    return discovered


def discover_available_apps(repo_root: Path) -> List[str]:
    """Return sorted list of workload names under apps/<app-name>/ that contain at least one Dockerfile."""
    apps_dir = repo_root / "apps"
    if not apps_dir.exists():
        return []
    return sorted(
        p.name
        for p in apps_dir.iterdir()
        if p.is_dir() and len(discover_app_dockerfiles(p)) > 0
    )


def parse_args(available_apps: List[str]):
    parser = argparse.ArgumentParser(
        description="Step 1: Discover & Build Application Container Images and Push to Registry"
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env configuration file (relative to current working directory). Default: .env",
    )
    parser.add_argument(
        "--platform",
        choices=["gcp", "gdc"],
        help="Target platform override (gcp | gdc). Defaults to TARGET_PLATFORM in .env.",
    )
    parser.add_argument(
        "-r",
        "--repo",
        help="Target GitLab project repository path (<group>/<project>). Overrides GITLAB_GROUP/GITLAB_PROJECT.",
    )
    parser.add_argument(
        "-g",
        "--group",
        help="GitLab group name. Defaults to GITLAB_GROUP in .env or 'workloads'.",
    )
    parser.add_argument(
        "-p",
        "--project-name",
        help="GitLab project name. Defaults to GITLAB_PROJECT in .env.",
    )
    parser.add_argument(
        "-a",
        "--app-name",
        choices=available_apps if available_apps else None,
        help=f"Application to build from apps/<app-name>/. Available: {', '.join(available_apps)}",
    )
    parser.add_argument(
        "-t",
        "--image-tag",
        help="Container image tag. Defaults to APP_IMAGE_TAG in .env or 'v1.0.0'.",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Check tool dependencies and environment setup without making changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without building or pushing images.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    return parser.parse_args()


def render_app_properties(
    app_name: str,
    image_map: Dict[str, str],
    config,
) -> Tuple[str, str]:
    """Generate app.properties and app-secrets.properties content for single- or multi-image workloads."""
    lines: List[str] = []
    if len(image_map) == 1:
        only_ref = next(iter(image_map.values()))
        lines.append(f"IMAGE={only_ref}")
    for svc_name, img_ref in image_map.items():
        env_key = "IMAGE_" + svc_name.upper().replace("-", "_")
        lines.append(f"{env_key}={img_ref}")

    if app_name == "upload-api":
        bucket_name = os.environ.get("UPLOAD_BUCKET_NAME", f"{config.gitlab_project}-upload-archives")
        storage_endpoint = os.environ.get(
            "UPLOAD_STORAGE_ENDPOINT", "https://objectstorage.org-1.zone1.google.gdch.test"
        )
        access_key = os.environ.get("UPLOAD_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("UPLOAD_SECRET_ACCESS_KEY", "")
        lines.extend(
            [
                f"BUCKET_NAME={bucket_name}",
                f"STORAGE_ENDPOINT={storage_endpoint}",
                f"PLATFORM_ADMIN={config.admin_email}",
            ]
        )
        secret_props = (
            f"SECRET_ACCESS_KEY={secret_key}\n"
            f"ACCESS_KEY_ID={access_key}\n"
        )
        return "\n".join(lines) + "\n", secret_props

    lines.extend(
        [
            f"KEYCLOAK_URL={config.keycloak_url}",
            f"KEYCLOAK_REALM={config.keycloak_realm}",
        ]
    )
    secret_props = f"TRANSLATE_APP_API_KEY={config.translate_api_key}\n"
    return "\n".join(lines) + "\n", secret_props


def stage_deployed_manifests(
    repo_root: Path,
    app_name: str,
    image_map: Dict[str, str],
    config,
    dry_run: bool = False,
) -> Path:
    """Populate .deployed-manifests/<app_name>/ with rendered Kustomize properties."""
    src_manifests = repo_root / "apps" / app_name / "manifests"
    deployed_dir = repo_root / ".deployed-manifests" / app_name
    base_dir = deployed_dir / "base"

    summary_refs = ", ".join(f"{k}={v}" for k, v in image_map.items())
    if dry_run:
        print_info(f"[DRY-RUN] Would stage Kustomize properties in .deployed-manifests/{app_name}/base/ ({summary_refs})")
        return deployed_dir

    if deployed_dir.exists():
        shutil.rmtree(deployed_dir)
    shutil.copytree(src_manifests, deployed_dir, dirs_exist_ok=True)
    base_dir.mkdir(parents=True, exist_ok=True)

    app_props, secret_props = render_app_properties(app_name, image_map, config)
    (base_dir / "app.properties").write_text(app_props)
    (base_dir / "app-secrets.properties").write_text(secret_props)

    print_success(f"Staged Kustomize manifests in .deployed-manifests/{app_name}/ ({summary_refs})")
    return deployed_dir


def print_step1_next_steps(
    image_map: Dict[str, str],
    group_name: str,
    project_name: str,
    app_name: str,
    env_file: Optional[str] = None,
):
    """Display completion banner with instructions for Step 2 (push_manifests.py)."""
    print_success(f"Step 1 (Build & Registry Push for '{app_name}') completed successfully.")
    env_flag = f" -e {env_file}" if env_file and env_file != ".env" else ""
    img_lines = "\n".join(f"   • [bold cyan]{svc}[/bold cyan]: {ref}" for svc, ref in image_map.items())

    content = (
        f"1. Container Image(s) Ready in Registry:\n"
        f"{img_lines}\n\n"
        f"2. Proceed to Step 2 (Push Manifests into GitLab Repo '{group_name}/{project_name}'):\n"
        f"   [bold cyan]python3 scripts/push_manifests.py -r {group_name}/{project_name} -a {app_name}{env_flag}[/bold cyan]"
    )
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps (Step 2 of 2)[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps (Step 2 of 2) ---")
        for svc, ref in image_map.items():
            print(f"  - {svc}: {ref}")
        print(f"Run: python3 scripts/push_manifests.py -r {group_name}/{project_name} -a {app_name}{env_flag}")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    available_apps = discover_available_apps(repo_root)
    args = parse_args(available_apps)

    # 1. Load read-only .env file relative to current working directory
    env_file_path = (Path.cwd() / args.env_file).resolve()
    load_dotenv(env_file_path)

    # 2. Resolve repo override (-r group/project)
    cli_group = args.group
    cli_project = args.project_name
    if args.repo and "/" in args.repo:
        cli_group, cli_project = args.repo.strip().strip("/").split("/", 1)

    # 3. Determine target platform & load providers
    target_platform = args.platform or get_target_platform(env_file_path)
    prereqs_provider = get_prereqs_provider(target_platform)
    project_provider = get_project_provider(target_platform)
    registry_provider = get_registry_provider(target_platform)

    config = get_config(
        env_file_path,
        cli_overrides={
            "platform": target_platform,
            "gitlab_group": cli_group,
            "gitlab_project": cli_project,
            "app_name": args.app_name,
            "app_image_tag": args.image_tag,
        },
    )

    validate_required_env_vars(config.required_vars, env_file_path=env_file_path)

    app_name = config.app_name
    app_root = repo_root / "apps" / app_name
    discovered_dockerfiles = discover_app_dockerfiles(app_root)
    if not discovered_dockerfiles:
        print_error(
            f"No Dockerfile found under {app_root}. "
            f"Available apps: {', '.join(available_apps)}"
        )
        sys.exit(1)

    print_header(f"Step 1: Build '{app_name}' Image(s) & Push to Registry ({target_platform.upper()} Mode)")

    # 4. Prerequisite verification
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 5. Resolve target image reference(s) & namespace
    image_tag = config.app_image_tag
    group_name = config.gitlab_group
    project_name = config.gitlab_project
    target_namespace = app_name

    planned_images: Dict[str, str] = {}
    dockerfile_rel_paths: List[str] = []
    for svc_name, svc_dir in discovered_dockerfiles:
        planned_images[svc_name] = registry_provider.resolve_app_image(
            app_name=svc_name,
            image_tag=image_tag,
            env_path=env_file_path,
        )
        dockerfile_rel_paths.append(str((svc_dir / "Dockerfile").relative_to(repo_root)))

    active_identity = project_provider.get_active_identity() or "None"
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"

    params_summary = {
        "Target Platform": target_platform.upper(),
        "Cluster / Context": f"{config.cluster_name} ({config.project_id})",
        "Workload Application": f"{app_name} ({len(discovered_dockerfiles)} image(s))",
        "Discovered Dockerfiles": ", ".join(dockerfile_rel_paths),
        "Target Image(s)": ", ".join(planned_images.values()),
        "Target K8s Namespace": target_namespace,
        "GitLab Project Repo": f"{group_name}/{project_name}",
        "Active Identity": active_identity,
        "Environment File": env_display,
    }
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Step 1: Build & Registry Push Parameters")

    # 6. Prompt user for confirmation
    if not confirm_action(
        f"Build {len(discovered_dockerfiles)} image(s) for '{app_name}' ({', '.join(planned_images.keys())}) and push to {target_platform.upper()} registry?",
        auto_approve=args.auto_approve,
    ):
        sys.exit(0)

    # 7. Build and push each discovered Dockerfile
    pushed_images: Dict[str, str] = {}
    for svc_name, svc_dir in discovered_dockerfiles:
        pushed_ref = registry_provider.build_and_push_app_image(
            app_dir=svc_dir,
            app_name=svc_name,
            image_tag=image_tag,
            env_path=env_file_path,
            dry_run=args.dry_run,
        )
        pushed_images[svc_name] = pushed_ref

    # 8. Configure target namespace & image pull secret
    print_header(f"Step 1d: Configure Target Namespace & Pull Secret ({target_namespace})")
    registry_provider.ensure_image_pull_secret(
        namespace=target_namespace,
        env_path=env_file_path,
        dry_run=args.dry_run,
    )

    # 9. Stage rendered manifests in .deployed-manifests/<app_name>/
    stage_deployed_manifests(
        repo_root=repo_root,
        app_name=app_name,
        image_map=pushed_images,
        config=config,
        dry_run=args.dry_run,
    )

    # 10. Display next steps banner
    print_step1_next_steps(
        image_map=pushed_images,
        group_name=group_name,
        project_name=project_name,
        app_name=app_name,
        env_file=args.env_file,
    )


if __name__ == "__main__":
    main()
