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

"""Step 2: Integrate & Push Application Manifests to Existing GitLab Repository.

Assumes the target GitLab project repository (<group>/<project>.git) and ArgoCD
App-of-Apps wiring (<project>-apps) were already provisioned in gitops-workshop.
Clones the existing project repository into a temporary directory, overwrites
manifests/ with the declarative Kustomize manifests for <app-name> (preserving
manifests/project.yaml), and pushes a feature branch + Merge Request only when
manifest changes are detected.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
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
from gitlab_utils import (
    get_gitlab_credentials,
    sync_git_repo_with_mr,
    verify_existing_gitlab_repo,
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
    """Search apps/<app_name>/ for Dockerfiles and return [(image_name, build_context_dir), ...]."""
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
    """Return sorted list of workload names under apps/<app-name>/."""
    apps_dir = repo_root / "apps"
    if not apps_dir.exists():
        return []
    return sorted(
        p.name
        for p in apps_dir.iterdir()
        if p.is_dir() and (p / "manifests").exists()
    )


def parse_args(available_apps: List[str]):
    parser = argparse.ArgumentParser(
        description="Step 2: Integrate & Push Application Manifests to GitLab Project Repository"
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
        help="Target GitLab project repository (<group>/<project>) provisioned in gitops-workshop.",
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
        help=f"Application to deploy from apps/<app-name>/. Available: {', '.join(available_apps)}",
    )
    parser.add_argument(
        "-t",
        "--image-tag",
        help="Container image tag. Defaults to APP_IMAGE_TAG in .env or 'v1.0.0'.",
    )
    parser.add_argument(
        "--image",
        help="Explicit container image reference override (for single-image apps).",
    )
    parser.add_argument(
        "--configure-remote",
        action="store_true",
        help="Configure a 'gitlab' git remote on the local repository pointing to the GitLab project.",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Check tool dependencies and environment setup without making changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without pushing to GitLab.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    parser.add_argument(
        "-m",
        "--mr-approve",
        action="store_true",
        help="Automatically approve and merge created GitLab Merge Requests via API.",
    )
    return parser.parse_args()


def resolve_staged_or_default_images(
    repo_root: Path,
    explicit_image: Optional[str],
    registry_provider,
    app_name: str,
    image_tag: str,
    env_file_path: Path,
) -> Dict[str, str]:
    """Resolve service image map from staged .deployed-manifests/<app_name>/base/app.properties or Dockerfile discovery."""
    app_root = repo_root / "apps" / app_name
    discovered = discover_app_dockerfiles(app_root)
    if not discovered:
        discovered = [(app_name, app_root)]

    staged_props = repo_root / ".deployed-manifests" / app_name / "base" / "app.properties"
    staged_kv: Dict[str, str] = {}
    if staged_props.exists():
        for line in staged_props.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                staged_kv[k.strip()] = v.strip()

    image_map: Dict[str, str] = {}
    for svc_name, _ in discovered:
        env_key = "IMAGE_" + svc_name.upper().replace("-", "_")
        if explicit_image and len(discovered) == 1:
            image_map[svc_name] = explicit_image.strip()
        elif env_key in staged_kv and staged_kv[env_key]:
            image_map[svc_name] = staged_kv[env_key]
        elif len(discovered) == 1 and "IMAGE" in staged_kv and staged_kv["IMAGE"]:
            image_map[svc_name] = staged_kv["IMAGE"]
        else:
            image_map[svc_name] = registry_provider.resolve_app_image(
                app_name=svc_name,
                image_tag=image_tag,
                env_path=env_file_path,
            )
    return image_map


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


def configure_local_git_remote(
    repo_root: Path,
    gitlab_http_url: str,
    group_name: str,
    project_name: str,
    dry_run: bool = False,
) -> str:
    """Configure or update 'gitlab' remote on the local repository."""
    remote_url = f"{gitlab_http_url.rstrip('/')}/{group_name}/{project_name}.git"
    if dry_run:
        print_info(f"[DRY-RUN] Would configure git remote 'gitlab' -> {remote_url}")
        return remote_url

    res = subprocess.run(
        ["git", "remote", "get-url", "gitlab"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        subprocess.run(["git", "remote", "set-url", "gitlab", remote_url], cwd=str(repo_root), check=False)
        print_info(f"Updated git remote 'gitlab' -> [bold cyan]{remote_url}[/bold cyan]")
    else:
        subprocess.run(["git", "remote", "add", "gitlab", remote_url], cwd=str(repo_root), check=False)
        print_success(f"Added git remote 'gitlab' -> [bold cyan]{remote_url}[/bold cyan]")
    return remote_url


def trigger_argocd_refresh(project_name: str, app_name: str, dry_run: bool = False):
    """Annotate ArgoCD applications with hard refresh so new GitLab commits are detected immediately."""
    if dry_run:
        return
    for target_app in [f"{project_name}-apps", app_name]:
        subprocess.run(
            [
                "kubectl",
                "annotate",
                "application",
                target_app,
                "-n",
                "argocd",
                "argocd.argoproj.io/refresh=hard",
                "--overwrite",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def print_completion_banner(
    gitlab_http_url: str,
    argocd_url: str,
    group_name: str,
    project_name: str,
    app_name: str,
    workload_mr_url: Optional[str] = None,
):
    """Display completion banner with GitLab MR, ArgoCD Sync, and Port-Forward verification."""
    print_success(f"Application '{app_name}' manifests integrated into GitLab repo '{group_name}/{project_name}'.")
    target_ns = app_name
    repo_url = f"{gitlab_http_url.rstrip('/')}/{group_name}/{project_name}"
    local_port = "8083" if app_name == "upload-api" else "8082"

    lines = [
        f"1. Project Repository ('{group_name}/{project_name}'):\n"
        f"   [bold cyan]{repo_url}[/bold cyan]\n"
    ]
    if workload_mr_url:
        lines.append(
            f"2. Merge Request (if not auto-merged with -m):\n"
            f"   [bold cyan]{workload_mr_url}[/bold cyan]\n"
        )
    lines.append(
        f"3. Synchronize in ArgoCD UI ([bold cyan]{argocd_url}[/bold cyan]):\n"
        f"   - Sync [bold yellow]{project_name}-apps[/bold yellow] -> [bold yellow]{app_name}[/bold yellow]\n"
        f"4. Port-Forward & Access Live Application:\n"
        f"   [bold cyan]kubectl port-forward -n {target_ns} svc/{app_name} {local_port}:80[/bold cyan]\n"
        f"   - Web UI: [bold cyan]http://localhost:{local_port}[/bold cyan]"
    )

    if RICH_AVAILABLE:
        console.print()
        console.print(
            Panel(
                "\n".join(lines),
                title=f"[bold green]Step 2 Complete: '{app_name}' Shipped via GitOps[/bold green]",
                box=box.ROUNDED,
                expand=False,
            )
        )
    else:
        print(f"\n--- Step 2 Complete: '{app_name}' Shipped via GitOps ---")
        for line in lines:
            print(line)


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
    manifests_src_dir = app_root / "manifests"
    if not manifests_src_dir.exists():
        print_error(
            f"Application manifests not found at {manifests_src_dir}. "
            f"Available apps: {', '.join(available_apps)}"
        )
        sys.exit(1)

    print_header(f"Step 2: Push '{app_name}' Manifests to GitLab ({target_platform.upper()} Mode)")

    # 4. Prerequisite verification
    if not prereqs_provider.check_prerequisites(verbose=args.check_prereqs, env_path=env_file_path):
        print_error("Prerequisites check failed. Please resolve missing tools before continuing.")
        sys.exit(1)

    if args.check_prereqs:
        print_success("All prerequisites verified successfully.")
        sys.exit(0)

    # 5. Resolve parameters
    group_name = config.gitlab_group
    project_name = config.gitlab_project
    project_path = f"{group_name}/{project_name}"
    image_tag = config.app_image_tag
    overlay_target = "gdc" if target_platform == "gdc" else "gcp"
    target_namespace = app_name

    image_map = resolve_staged_or_default_images(
        repo_root=repo_root,
        explicit_image=args.image,
        registry_provider=registry_provider,
        app_name=app_name,
        image_tag=image_tag,
        env_file_path=env_file_path,
    )
    image_summary = ", ".join(image_map.values())

    active_identity = project_provider.get_active_identity() or "None"
    gitlab_remote_url = f"{config.gitlab_http_url.rstrip('/')}/{project_path}.git"

    # 6. Display Execution Parameter Summary Table
    env_display = f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)"
    params_summary = {
        "Target Platform": target_platform.upper(),
        "GitLab Project Repo": project_path,
        "GitLab Remote URL": gitlab_remote_url,
        "Workload Application": f"{app_name} (apps/{app_name}/)",
        "Target K8s Namespace": target_namespace,
        "Kustomize Overlay": f"manifests/{app_name}/overlays/{overlay_target}",
        "Container Image(s)": image_summary,
        "Active Identity": active_identity,
        "Environment File": env_display,
    }
    if args.mr_approve:
        params_summary["MR Auto-Merge"] = "[bold yellow]YES (-m)[/bold yellow]"
    if args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    print_parameter_summary(params_summary, title="Step 2: GitLab Manifest Integration Parameters")

    # 7. Prompt user for confirmation
    if not confirm_action(
        f"Clone '{project_path}', overwrite '{app_name}' manifests, and push to GitLab?",
        auto_approve=args.auto_approve,
    ):
        sys.exit(0)

    # 8. Ensure target namespace and image pull secret exist before ArgoCD sync
    registry_provider.ensure_image_pull_secret(
        namespace=target_namespace,
        env_path=env_file_path,
        dry_run=args.dry_run,
    )

    # 9. Optional local git remote configuration
    if args.configure_remote:
        configure_local_git_remote(
            repo_root=repo_root,
            gitlab_http_url=config.gitlab_http_url,
            group_name=group_name,
            project_name=project_name,
            dry_run=args.dry_run,
        )

    # 10. Verify that the target GitLab project repo already exists (provisioned by gitops-workshop)
    print_header(f"Step 2a: Verify Existing GitLab Repository ({project_path})")
    root_pass, _ = get_gitlab_credentials()
    if not args.dry_run:
        verify_existing_gitlab_repo(project_path, config.gitlab_http_url)
        print_success(f"Verified existing GitLab repository '{project_path}'.")
    else:
        print_info(f"[DRY-RUN] Would verify existing GitLab repository '{project_path}'.")

    # 11. Clone <group>/<project>.git in temp dir, overwrite manifests/, and push MR
    print_header(f"Step 2b: Integrate '{app_name}' into {project_path}")

    def integrate_app_into_repo(working_dir: Path):
        dst_manifests = working_dir / "manifests"
        dst_manifests.mkdir(parents=True, exist_ok=True)

        # Remove any legacy apps/ source directory if previously pushed
        legacy_apps_dir = working_dir / "apps"
        if legacy_apps_dir.exists():
            shutil.rmtree(legacy_apps_dir)

        # 1. Write manifests/project.yaml matching gitops-workshop's AppProject specification
        shutil.rmtree(dst_manifests)
        dst_manifests.mkdir(parents=True, exist_ok=True)

        project_yaml_path = dst_manifests / "project.yaml"
        project_yaml_path.write_text(
            f"apiVersion: argoproj.io/v1alpha1\n"
            f"kind: AppProject\n"
            f"metadata:\n"
            f"  name: {project_name}\n"
            f"  namespace: argocd\n"
            f"spec:\n"
            f"  description: Workload project for {project_name}\n"
            f"  sourceRepos:\n"
            f"    - 'git@gitlab-omnibus.gitlab.svc.cluster.local:{project_path}.git'\n"
            f"  destinations:\n"
            f"    - namespace: '*'\n"
            f"      server: https://kubernetes.default.svc\n"
            f"  clusterResourceWhitelist:\n"
            f"    - group: '*'\n"
            f"      kind: '*'\n"
        )

        # 2. Copy apps/<app_name>/manifests/{base,overlays} into manifests/<app_name>/
        dst_app_manifests = dst_manifests / app_name
        dst_app_manifests.mkdir(parents=True, exist_ok=True)

        for subdir in ("base", "overlays"):
            src_sub = manifests_src_dir / subdir
            if src_sub.exists():
                shutil.copytree(src_sub, dst_app_manifests / subdir, dirs_exist_ok=True)

        # 3. Write rendered app.properties & app-secrets.properties into manifests/<app_name>/base/
        base_dir = dst_app_manifests / "base"
        base_dir.mkdir(parents=True, exist_ok=True)
        app_props, secret_props = render_app_properties(app_name, image_map, config)
        (base_dir / "app.properties").write_text(app_props)
        (base_dir / "app-secrets.properties").write_text(secret_props)

        # 4. Write manifests/<app_name>-app.yaml pointing to manifests/<app_name>/overlays/<gdc|gcp>
        app_cr_yaml = (
            f"apiVersion: argoproj.io/v1alpha1\n"
            f"kind: Application\n"
            f"metadata:\n"
            f"  name: {app_name}\n"
            f"  namespace: argocd\n"
            f"  labels:\n"
            f"    app.kubernetes.io/part-of: {group_name}\n"
            f"    gitops.platform/group: {group_name}\n"
            f"    gitops.platform/project: {project_name}\n"
            f"    gitops.platform/tier: workload\n"
            f"  finalizers:\n"
            f"    - resources-finalizer.argocd.argoproj.io\n"
            f"spec:\n"
            f"  project: {project_name}\n"
            f"  source:\n"
            f"    repoURL: git@gitlab-omnibus.gitlab.svc.cluster.local:{project_path}.git\n"
            f"    targetRevision: main\n"
            f"    path: manifests/{app_name}/overlays/{overlay_target}\n"
            f"  destination:\n"
            f"    server: https://kubernetes.default.svc\n"
            f"    namespace: {target_namespace}\n"
            f"  syncPolicy:\n"
            f"    syncOptions:\n"
            f"      - CreateNamespace=true\n"
        )
        (dst_manifests / f"{app_name}-app.yaml").write_text(app_cr_yaml)

        # 5. Write manifests/kustomization.yaml referencing project.yaml and <app_name>-app.yaml
        root_kustomization = (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n\n"
            "resources:\n"
            "  - project.yaml\n"
            f"  - {app_name}-app.yaml\n"
        )
        (dst_manifests / "kustomization.yaml").write_text(root_kustomization)

    _, _, workload_mr_url = sync_git_repo_with_mr(
        project_path=project_path,
        branch_prefix=f"feature/deploy-{app_name}",
        commit_message=f"Deploy {app_name} ({image_summary}) via {overlay_target.upper()} overlay",
        mr_title=f"Deploy {app_name} ({image_tag}) to namespace {target_namespace}",
        mr_description=(
            f"Ships `{app_name}` (`{image_summary}`) with Kustomize overlay "
            f"`manifests/{app_name}/overlays/{overlay_target}` into `{project_path}`."
        ),
        update_files_callback=integrate_app_into_repo,
        assignee=config.admin_email,
        root_pass=root_pass,
        target_branch="main",
        auto_approve=args.auto_approve,
        mr_approve=args.mr_approve,
        dry_run=args.dry_run,
    )

    # 12. Trigger ArgoCD hard refresh
    trigger_argocd_refresh(project_name, app_name, dry_run=args.dry_run)

    # 13. Print Completion Banner
    print_completion_banner(
        gitlab_http_url=config.gitlab_http_url,
        argocd_url=config.argocd_server_url,
        group_name=group_name,
        project_name=project_name,
        app_name=app_name,
        workload_mr_url=workload_mr_url,
    )


if __name__ == "__main__":
    main()
