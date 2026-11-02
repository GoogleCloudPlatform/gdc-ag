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

"""Shared helper utilities and Rich CLI UX formatting for gitops-workshop automation scripts."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Auto-discover known local virtual environments if packages are in venv
for venv_path in [
    Path.cwd() / ".venv",
    Path(__file__).resolve().parents[2] / ".venv",
    Path.cwd() / "venv",
]:
    if venv_path.exists():
        for site_pkg in venv_path.glob("lib/python*/site-packages"):
            if site_pkg.exists() and str(site_pkg) not in sys.path:
                sys.path.insert(0, str(site_pkg))

# Try importing rich, provide fallback if missing
try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.status import Status
    from rich.table import Table
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None
    box = None


def load_dotenv(env_path: Optional[Path] = None, override: bool = True) -> Dict[str, str]:
    """Parse .env file and set environment variables. Never modifies the .env file.
    
    Defaults to .env in current working directory (Path.cwd()).
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path).resolve()

    env_vars = {}
    if not env_path.exists() or not env_path.is_file():
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if " #" in line:
                line = line.split(" #", 1)[0].strip()
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env_vars[key] = val
            if override or key not in os.environ:
                os.environ[key] = val
    return env_vars


def validate_required_env_vars(
    required_vars: List[str],
    env_file_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, str]:
    """Validate that required environment variables / CLI inputs are present and non-empty.
    
    If any required variable is missing, prints a formatted Rich table and exits with code 1.
    Returns a dictionary of the validated variables and their values.
    """
    target_env = env_file_path or (Path.cwd() / ".env")
    env_vars = {}
    if target_env.exists() and target_env.is_file():
        env_vars = load_dotenv(target_env, override=True)

    resolved_values = {}
    missing_vars = []
    overrides = cli_overrides or {}

    for var in required_vars:
        # Check CLI override first, then env_vars from target env file, then os.environ
        cli_val = overrides.get(var)
        file_val = env_vars.get(var)
        if env_file_path is not None:
            val = cli_val if cli_val is not None else (file_val if file_val is not None else "")
        else:
            val = cli_val if cli_val is not None else (file_val if file_val is not None else os.environ.get(var, ""))
        val = val.strip()
        if not val:
            missing_vars.append(var)
        else:
            resolved_values[var] = val



    if missing_vars:
        env_display = str(env_file_path or (Path.cwd() / ".env"))
        if RICH_AVAILABLE and console:
            table = Table(title="[bold red]Missing Required Environment Variables[/bold red]", show_header=True, header_style="bold magenta")
            table.add_column("Variable", style="cyan", width=25)
            table.add_column("Status", width=15)
            table.add_column("Source / Resolution", style="yellow")
            
            for var in required_vars:
                if var in missing_vars:
                    table.add_row(var, "[bold red]MISSING[/bold red]", f"Set in {env_display} or pass via CLI flag")
                else:
                    table.add_row(var, "[bold green]PRESENT[/bold green]", resolved_values[var])
            
            console.print(table)
            print_error(f"Missing required configuration in {env_display}. Please populate required variables before continuing.")
        else:
            print(f"ERROR: Missing required environment variables in {env_display}: {', '.join(missing_vars)}")
        sys.exit(1)

    return resolved_values


def print_header(title: str):
    """Print a styled section header."""
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(f"[bold cyan]{title}[/bold cyan]", expand=False))
    else:
        print(f"\n=== {title} ===")


def print_success(msg: str):
    """Print a success message."""
    if RICH_AVAILABLE:
        console.print(f"[bold green][SUCCESS][/bold green] {msg}")
    else:
        print(f"[SUCCESS] {msg}")


def print_info(msg: str):
    """Print an informational message."""
    if RICH_AVAILABLE:
        console.print(f"[bold blue][INFO][/bold blue] {msg}")
    else:
        print(f"[INFO] {msg}")


def print_warning(msg: str):
    """Print a warning/skip message."""
    if RICH_AVAILABLE:
        console.print(f"[bold yellow][EXISTS/SKIP][/bold yellow] {msg}")
    else:
        print(f"[SKIP] {msg}")


def print_error(msg: str):
    """Print an error message."""
    if RICH_AVAILABLE:
        console.print(f"[bold red][ERROR][/bold red] {msg}")
    else:
        print(f"[ERROR] {msg}")


def print_parameter_summary(params: Dict[str, str], title: str = "Execution Configuration"):
    """Display a formatted summary table of execution parameters."""
    if RICH_AVAILABLE:
        table = Table(
            title=f"[bold]{title}[/bold]",
            title_justify="left",
            show_header=True,
            header_style="bold magenta",
            box=box.ROUNDED,
            expand=False,
        )
        table.add_column("Parameter Name", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")
        for key, val in params.items():
            if val is not None and str(val).strip():
                table.add_row(key, str(val))
        console.print()
        console.print(table)
    else:
        print(f"\n--- {title} ---")
        for key, val in params.items():
            if val is not None and str(val).strip():
                print(f"  {key:<24}: {val}")
        print("----------------------------")


def confirm_action(prompt_text: str = "Do you want to proceed with execution?", auto_approve: bool = False) -> bool:
    """Prompt the user for confirmation before proceeding."""
    if auto_approve:
        print_info("Auto-approved via --auto-approve / -y flag. Proceeding...")
        return True

    if RICH_AVAILABLE:
        answer = console.input(f"\n[bold yellow]?[/bold yellow] [bold]{prompt_text}[/bold] [y/N]: ").strip().lower()
    else:
        answer = input(f"\n? {prompt_text} [y/N]: ").strip().lower()

    if answer in ["y", "yes"]:
        print_success("User confirmed. Proceeding with execution...")
        return True
    else:
        print_warning("Execution cancelled by user.")
        return False


def print_next_steps(
    project_id: str,
    project_owner: Optional[str] = None,
    next_script: str = "scripts/bootstrap/provision_cluster.py",
    platform: str = "gcp",
    env_file: Optional[Union[str, Path]] = None,
):
    """Display instructions for the user to run the next script."""
    owner = project_owner or "<PROJECT_OWNER_EMAIL>"
    print_success("Phase 1 Bootstrap & Project verification completed successfully.")

    env_flag = ""
    if env_file:
        env_str = str(env_file)
        if env_str not in [".env", str(Path.cwd() / ".env")]:
            env_flag = f" -e {env_str}"

    if platform.lower() == "gdc":
        kubeconfig = os.environ.get("KUBECONFIG", "$HOME/lowhigh-dev-kubeconfig")
        content = (
            f"1. Verified GDC Cluster Context & Reachability:\n"
            f"   [bold cyan]export KUBECONFIG={kubeconfig}[/bold cyan]\n"
            f"   [bold cyan]kubectl cluster-info[/bold cyan]\n"
            f"2. Run the next provision script:\n"
            f"   [bold cyan]python3 {next_script}{env_flag}[/bold cyan]"
        )
        plain_content = (
            f"1. export KUBECONFIG={kubeconfig}\n"
            f"   kubectl cluster-info\n"
            f"2. python3 {next_script}{env_flag}"
        )
    else:
        content = (
            f"1. Authenticate with gcloud as the Project Owner:\n"
            f"   [bold cyan]gcloud auth login {owner}[/bold cyan]\n"
            f"2. Set active gcloud project context:\n"
            f"   [bold cyan]gcloud config set project {project_id}[/bold cyan]\n"
            f"3. Run the next provision script:\n"
            f"   [bold cyan]python3 {next_script}{env_flag}[/bold cyan]"
        )
        plain_content = (
            f"1. gcloud auth login {owner}\n"
            f"2. gcloud config set project {project_id}\n"
            f"3. python3 {next_script}{env_flag}"
        )

    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(content, title="[bold cyan]Next Steps[/bold cyan]", box=box.ROUNDED, expand=False))
    else:
        print("\n--- Next Steps ---")
        print(plain_content)


def run_command(
    cmd: List[str],
    description: str = "",
    dry_run: bool = False,
    check: bool = True,
    capture_output: bool = True,
    cwd: Optional[Union[str, Path]] = None,
) -> Tuple[int, str, str]:
    """Execute a system shell command with status logging."""
    cmd_str = " ".join(str(c) for c in cmd)
    cwd_str = str(cwd) if cwd else None
    if dry_run:
        print_info(f"[DRY-RUN] Would execute: {cmd_str}")
        return 0, "", ""

    if description:
        if RICH_AVAILABLE:
            with console.status(f"[bold blue]{description}...[/bold blue]"):
                res = subprocess.run(cmd, capture_output=capture_output, text=True, cwd=cwd_str)
        else:
            print(f"Executing: {description}...")
            res = subprocess.run(cmd, capture_output=capture_output, text=True, cwd=cwd_str)
    else:
        res = subprocess.run(cmd, capture_output=capture_output, text=True, cwd=cwd_str)

    if res.returncode != 0 and check:
        err_msg = f"Command failed with exit code {res.returncode}: {cmd_str}"
        if res.stderr:
            err_msg += f"\nStderr: {res.stderr.strip()}"
        print_error(err_msg)
        if not dry_run:
            sys.exit(res.returncode)

    return res.returncode, res.stdout or "", res.stderr or ""


def check_tool_installed(tool_name: str) -> bool:
    """Check if a CLI executable exists on PATH."""
    return shutil.which(tool_name) is not None


def ensure_k8s_namespace(namespace_name: str, dry_run: bool = False):
    """Ensure a Kubernetes namespace exists idempotently."""
    print_info(f"Ensuring Kubernetes namespace '{namespace_name}' exists...")
    code, out, err = run_command(
        ["kubectl", "create", "namespace", namespace_name, "--dry-run=client", "-o", "yaml"],
        check=False,
        capture_output=True
    )
    if code == 0 and out:
        if dry_run:
            print_info(f"[DRY-RUN] Would apply namespace '{namespace_name}'.")
        else:
            res = subprocess.run(["kubectl", "apply", "-f", "-"], input=out, text=True, capture_output=True)
            if res.returncode == 0:
                print_success(f"Kubernetes namespace '{namespace_name}' is ready.")
            else:
                err_detail = res.stderr.strip() if res.stderr else "Unknown error"
                if "gke-gcloud-auth-plugin" in err_detail or "invalid_grant" in err_detail or "reauth" in err_detail:
                    print_error(
                        f"Failed to ensure namespace '{namespace_name}' due to expired/invalid Google credentials.\n"
                        "Please run 'gcloud auth application-default login' and re-run the script."
                    )
                else:
                    print_error(f"Failed to ensure namespace '{namespace_name}'. Details:\n{err_detail}")
                sys.exit(1)


def get_deployed_manifests_dir() -> Path:
    """Return the path to the .deployed-manifests working directory."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / ".deployed-manifests"


def ensure_deployed_manifests_dir(force_reset: bool = False) -> Path:
    """Ensure .deployed-manifests exists, populated from manifests/ template directory."""
    repo_root = Path(__file__).resolve().parents[2]
    template_dir = repo_root / "manifests"
    deployed_dir = repo_root / ".deployed-manifests"

    if force_reset and deployed_dir.exists():
        shutil.rmtree(deployed_dir)

    if not deployed_dir.exists():
        shutil.copytree(template_dir, deployed_dir, dirs_exist_ok=True)
        print_info(f"Initialized deployed manifests copy from {template_dir.name}/ -> {deployed_dir.name}/")
    return deployed_dir



# Dynamic Dispatch via Platform Adapter
from platform_adapter import (  # noqa: E402
    get_target_platform,
    get_prereqs_provider,
    get_project_provider,
    get_cluster_provider,
    get_registry_provider,
    get_auth_provider,
    get_cleanup_provider,
)

def check_prerequisites(verbose: bool = False) -> bool:
    """Check prerequisites using active platform provider."""
    provider = get_prereqs_provider()
    return provider.check_prerequisites(verbose=verbose)


# Backward Compatibility Imports & Aliases for GCP
from gcp.project import (  # noqa: E402
    get_active_gcp_project,
    get_active_gcloud_user,
    get_available_billing_accounts,
    select_billing_account,
    link_gcp_project_billing,
    gcp_project_exists,
    gcp_project_has_workshop_label,
    ensure_project as ensure_gcp_project,
)

from gcp.cluster import (  # noqa: E402
    gke_cluster_exists,
    configure_kubectl_credentials,
    enable_gcp_services,
    vpc_network_exists,
    ensure_vpc_network,
    cloud_router_exists,
    cloud_nat_exists,
    ensure_cloud_nat,
    ensure_cluster as ensure_gke_autopilot_cluster,
    get_cluster_info,
)
