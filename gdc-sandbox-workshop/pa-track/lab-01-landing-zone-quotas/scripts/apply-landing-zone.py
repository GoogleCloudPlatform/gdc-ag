#!/usr/bin/env python3

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
apply-landing-zone.py
---------------------
Production-grade automation script for GDC Platform Administrators to validate
and provision multi-tenant landing zones, ResourceQuotas, and LimitRanges.
"""

import argparse
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
import yaml


class TerminalColor:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{TerminalColor.CYAN}[INFO]{TerminalColor.RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{TerminalColor.GREEN}[SUCCESS]{TerminalColor.RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{TerminalColor.YELLOW}[WARN]{TerminalColor.RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{TerminalColor.RED}[ERROR]{TerminalColor.RESET} {msg}", file=sys.stderr)


def parse_k8s_quantity(val: Any) -> float:
    """
    Parses a Kubernetes resource quantity string into a comparable base float.
    Examples: '250m' -> 0.25, '4' -> 4.0, '512Mi' -> 512*1024*1024, '8Gi' -> 8*1024*1024*1024
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s:
        return 0.0

    # Milli-units (e.g., 250m)
    if s.endswith("m"):
        try:
            return float(s[:-1]) / 1000.0
        except ValueError:
            pass

    # Binary SI units (Ki, Mi, Gi, Ti, Pi)
    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "k": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for unit, factor in multipliers.items():
        if s.endswith(unit):
            try:
                num = float(s[: -len(unit)])
                return num * factor
            except ValueError:
                pass

    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Unrecognized Kubernetes resource quantity format: '{val}'")


def validate_project_config(project: Dict[str, Any]) -> List[str]:
    """
    Validates a single project entry in the configuration.
    Returns a list of validation error messages (empty if valid).
    """
    errors: List[str] = []
    name = project.get("name")
    if not name or not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", name):
        errors.append(f"Invalid or missing project name: '{name}'. Must be a valid DNS-1123 label.")

    # Validate ResourceQuota
    quota = project.get("quota")
    if not quota:
        errors.append(f"Project '{name}' missing required 'quota' block.")
    else:
        reqs = quota.get("requests", {})
        lims = quota.get("limits", {})
        try:
            req_cpu = parse_k8s_quantity(reqs.get("cpu", "0"))
            lim_cpu = parse_k8s_quantity(lims.get("cpu", "0"))
            if lim_cpu > 0 and req_cpu > lim_cpu:
                errors.append(f"Project '{name}': requests.cpu ({reqs.get('cpu')}) exceeds limits.cpu ({lims.get('cpu')}).")

            req_mem = parse_k8s_quantity(reqs.get("memory", "0"))
            lim_mem = parse_k8s_quantity(lims.get("memory", "0"))
            if lim_mem > 0 and req_mem > lim_mem:
                errors.append(f"Project '{name}': requests.memory ({reqs.get('memory')}) exceeds limits.memory ({lims.get('memory')}).")
        except ValueError as ex:
            errors.append(f"Project '{name}' quota format error: {ex}")

    # Validate LimitRange
    lr = project.get("limitRange", {}).get("container", {})
    if lr:
        try:
            min_cpu = parse_k8s_quantity(lr.get("min", {}).get("cpu", "0"))
            def_req_cpu = parse_k8s_quantity(lr.get("defaultRequest", {}).get("cpu", "0"))
            def_lim_cpu = parse_k8s_quantity(lr.get("default", {}).get("cpu", "0"))
            max_cpu = parse_k8s_quantity(lr.get("max", {}).get("cpu", "0"))

            if min_cpu > 0 and def_req_cpu > 0 and min_cpu > def_req_cpu:
                errors.append(f"Project '{name}' LimitRange: min CPU ({lr.get('min', {}).get('cpu')}) > defaultRequest CPU ({lr.get('defaultRequest', {}).get('cpu')}).")
            if def_req_cpu > 0 and def_lim_cpu > 0 and def_req_cpu > def_lim_cpu:
                errors.append(f"Project '{name}' LimitRange: defaultRequest CPU > default limit CPU.")
            if max_cpu > 0 and def_lim_cpu > 0 and def_lim_cpu > max_cpu:
                errors.append(f"Project '{name}' LimitRange: default limit CPU > max CPU.")
        except ValueError as ex:
            errors.append(f"Project '{name}' limitRange format error: {ex}")

    return errors


def build_manifests_for_project(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Constructs declarative Kubernetes manifests (Namespace, ResourceQuota, LimitRange)
    for a given project specification.
    """
    name = project["name"]
    tier = project.get("tier", "standard")
    owner = project.get("owner", "platform-admin@example.com")
    cost_center = project.get("costCenter", "UNASSIGNED")
    data_class = project.get("dataClassification", "internal")
    env = project.get("environment", "development")
    desc = project.get("description", f"Tenant namespace for {name}")

    manifests: List[Dict[str, Any]] = []

    # 1. Namespace
    ns_manifest = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": name,
            "labels": {
                "gdc.google.com/tenant": project.get("tenant", name.split("-")[0]),
                "gdc.google.com/environment": env,
                "gdc.google.com/tier": tier,
                "gdc.google.com/cost-center": str(cost_center),
                "gdc.google.com/data-classification": data_class,
                "app.kubernetes.io/managed-by": "gdc-landing-zone-engine",
            },
            "annotations": {
                "gdc.google.com/description": desc,
                "gdc.google.com/owner": owner,
            },
        },
    }
    manifests.append(ns_manifest)

    # 2. ResourceQuota
    quota_cfg = project.get("quota", {})
    hard_spec: Dict[str, str] = {}

    reqs = quota_cfg.get("requests", {})
    if "cpu" in reqs:
        hard_spec["requests.cpu"] = str(reqs["cpu"])
    if "memory" in reqs:
        hard_spec["requests.memory"] = str(reqs["memory"])
    if "storage" in reqs:
        hard_spec["requests.storage"] = str(reqs["storage"])
    if "gpu" in reqs:
        hard_spec["requests.nvidia.com/gpu"] = str(reqs["gpu"])

    lims = quota_cfg.get("limits", {})
    if "cpu" in lims:
        hard_spec["limits.cpu"] = str(lims["cpu"])
    if "memory" in lims:
        hard_spec["limits.memory"] = str(lims["memory"])
    if "gpu" in lims and lims["gpu"] != "0":
        hard_spec["limits.nvidia.com/gpu"] = str(lims["gpu"])

    counts = quota_cfg.get("counts", {})
    for k, v in counts.items():
        if k == "pods":
            hard_spec["pods"] = str(v)
        elif k == "persistentvolumeclaims":
            hard_spec["persistentvolumeclaims"] = str(v)
        elif k in ("deployments", "statefulsets", "daemonsets"):
            hard_spec[f"count/{k}.apps"] = str(v)
        elif k in ("jobs", "cronjobs"):
            hard_spec[f"count/{k}.batch"] = str(v)
        elif k in ("configmaps", "secrets", "services"):
            hard_spec[f"count/{k}"] = str(v)
        else:
            hard_spec[f"count/{k}"] = str(v)

    network = quota_cfg.get("network", {})
    if "services" in network:
        hard_spec["services"] = str(network["services"])
    if "servicesLoadbalancers" in network:
        hard_spec["services.loadbalancers"] = str(network["servicesLoadbalancers"])
    if "servicesNodeports" in network:
        hard_spec["services.nodeports"] = str(network["servicesNodeports"])

    quota_manifest = {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {
            "name": f"{name}-quota",
            "namespace": name,
            "labels": {
                "gdc.google.com/tier": tier,
                "app.kubernetes.io/managed-by": "gdc-landing-zone-engine",
            },
        },
        "spec": {"hard": hard_spec},
    }
    manifests.append(quota_manifest)

    # 3. LimitRange
    lr_cfg = project.get("limitRange", {})
    lr_items: List[Dict[str, Any]] = []

    c_lr = lr_cfg.get("container", {})
    if c_lr:
        c_item: Dict[str, Any] = {"type": "Container"}
        if "default" in c_lr:
            c_item["default"] = {k: str(v) for k, v in c_lr["default"].items()}
        if "defaultRequest" in c_lr:
            c_item["defaultRequest"] = {k: str(v) for k, v in c_lr["defaultRequest"].items()}
        if "min" in c_lr:
            c_item["min"] = {k: str(v) for k, v in c_lr["min"].items()}
        if "max" in c_lr:
            max_dict: Dict[str, str] = {}
            for k, v in c_lr["max"].items():
                if k == "gpu":
                    if str(v) != "0":
                        max_dict["nvidia.com/gpu"] = str(v)
                else:
                    max_dict[k] = str(v)
            c_item["max"] = max_dict
        if "maxLimitRequestRatio" in c_lr:
            c_item["maxLimitRequestRatio"] = {k: str(v) for k, v in c_lr["maxLimitRequestRatio"].items()}
        lr_items.append(c_item)

    pvc_lr = lr_cfg.get("pvc", {})
    if pvc_lr:
        pvc_item = {
            "type": "PersistentVolumeClaim",
            "min": {"storage": str(pvc_lr.get("minStorage", "1Gi"))},
            "max": {"storage": str(pvc_lr.get("maxStorage", "100Gi"))},
        }
        lr_items.append(pvc_item)

    if lr_items:
        limit_manifest = {
            "apiVersion": "v1",
            "kind": "LimitRange",
            "metadata": {
                "name": f"{name}-limits",
                "namespace": name,
                "labels": {
                    "gdc.google.com/tier": tier,
                    "app.kubernetes.io/managed-by": "gdc-landing-zone-engine",
                },
            },
            "spec": {"limits": lr_items},
        }
        manifests.append(limit_manifest)

    return manifests


def apply_manifests(manifests: List[Dict[str, Any]], kubeconfig: Optional[str], dry_run: bool) -> bool:
    """
    Serializes manifests to YAML and submits them to kubectl apply.
    """
    yaml_docs = yaml.dump_all(manifests, sort_keys=False)

    if dry_run:
        print(f"\n{TerminalColor.BOLD}=== [DRY-RUN] Manifest Output ==={TerminalColor.RESET}")
        print(yaml_docs)
        print(f"{TerminalColor.BOLD}=== End of Manifest Output ==={TerminalColor.RESET}\n")
        return True

    cmd = ["kubectl", "apply", "-f", "-"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])

    try:
        proc = subprocess.run(
            cmd,
            input=yaml_docs,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().splitlines():
                log_success(line)
            return True
        else:
            log_error(f"kubectl apply failed with exit code {proc.returncode}")
            print(proc.stderr, file=sys.stderr)
            return False
    except FileNotFoundError:
        log_error("kubectl binary not found in PATH.")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GDC Platform Administrator: Apply Multi-Tenant Landing Zone Quotas & Limits",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects_config.yaml"),
        help="Path to projects_config.yaml landing zone specification",
    )
    parser.add_argument(
        "--kubeconfig",
        "-k",
        default=os.getenv("KUBECONFIG"),
        help="Path to cluster kubeconfig file (or use KUBECONFIG env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and render generated Kubernetes manifests without applying them",
    )
    parser.add_argument(
        "--project",
        "-p",
        help="Filter and apply only a specific project name from the configuration",
    )

    args = parser.parse_args()

    print(f"{TerminalColor.BOLD}================================================================={TerminalColor.RESET}")
    print(f"{TerminalColor.BOLD}🚀 GDC Landing Zone & Multi-Tenant Quota Provisioner{TerminalColor.RESET}")
    print(f"{TerminalColor.BOLD}================================================================={TerminalColor.RESET}")
    log_info(f"Loading landing zone configuration: {args.config}")

    if not os.path.exists(args.config):
        log_error(f"Configuration file not found: {args.config}")
        sys.exit(1)

    try:
        with open(args.config, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as ex:
        log_error(f"Failed to parse YAML configuration: {ex}")
        sys.exit(1)

    projects = config_data.get("projects", [])
    if not projects:
        log_error("No 'projects' list defined in configuration.")
        sys.exit(1)

    if args.project:
        projects = [p for p in projects if p.get("name") == args.project]
        if not projects:
            log_error(f"Project '{args.project}' not found in configuration.")
            sys.exit(1)

    # Validation Phase
    log_info("Validating landing zone project schemas and quota specifications...")
    has_errors = False
    for p in projects:
        errs = validate_project_config(p)
        if errs:
            has_errors = True
            for err in errs:
                log_error(err)
        else:
            log_info(f"Project '{p.get('name')}' schema validation passed.")

    if has_errors:
        log_error("Validation failed. Please resolve configuration errors before applying.")
        sys.exit(1)

    log_success("All project definitions validated successfully.")

    # Manifest Generation & Application
    all_manifests: List[Dict[str, Any]] = []
    for p in projects:
        p_manifests = build_manifests_for_project(p)
        all_manifests.extend(p_manifests)

    log_info(f"Generated {len(all_manifests)} Kubernetes manifests across {len(projects)} tenant projects.")
    
    if args.dry_run:
        log_warn("Running in DRY-RUN mode. No cluster modifications will be made.")
    else:
        log_info("Applying manifests to GDC cluster...")

    success = apply_manifests(all_manifests, args.kubeconfig, args.dry_run)
    if not success:
        log_error("Landing zone provisioning encountered errors.")
        sys.exit(1)

    if not args.dry_run:
        print(f"\n{TerminalColor.GREEN}{TerminalColor.BOLD}🎉 Landing Zone successfully provisioned and enforced!{TerminalColor.RESET}")
        print(f"Run `./verify-quotas.sh` to inspect live consumption vs limits.\n")


if __name__ == "__main__":
    main()
