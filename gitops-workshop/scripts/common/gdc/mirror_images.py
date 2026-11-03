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

"""Mirror required GitOps workshop container images to internal Harbor registry.

Pulls public container images, tags them for the private GDC Harbor registry,
and pushes them using robot credentials.
"""

import argparse
import os
import sys
from pathlib import Path

# Add common directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
from gdc.registry import mirror_required_images


def parse_args():
    parser = argparse.ArgumentParser(
        description="Mirror workshop container images to GDC private Harbor registry"
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env configuration file (relative to current execution directory). Default: .env",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check image status in local Docker and Harbor without pulling or pushing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without pulling or pushing images.",
    )
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Automatically approve execution prompts without interactive confirmation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-tagging and pushing images even if already present locally.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load environment variables
    env_file_path = (Path.cwd() / args.env_file).resolve()
    common.load_dotenv(env_file_path)

    common.print_header("GDC Container Image Mirroring Pipeline")

    # Validate required Harbor variables
    required_vars = ["HARBOR_URL", "HARBOR_PROJECT", "HARBOR_USERNAME", "HARBOR_PASSWORD"]
    env_config = common.validate_required_env_vars(required_vars, env_file_path=env_file_path)

    harbor_url = env_config["HARBOR_URL"]
    harbor_project = env_config["HARBOR_PROJECT"]
    harbor_user = env_config["HARBOR_USERNAME"]

    # Parameter Summary Table
    params_summary = {
        "Target Platform": "GDC",
        "Harbor URL": harbor_url,
        "Harbor Project": harbor_project,
        "Harbor Robot Account": harbor_user,
        "Environment File": f"{env_file_path.name} (found)" if env_file_path.exists() else f"{env_file_path.name} (not found)",
    }
    if args.check_only:
        params_summary["Execution Mode"] = "[yellow]CHECK-ONLY[/yellow]"
    elif args.dry_run:
        params_summary["Execution Mode"] = "[yellow]DRY-RUN[/yellow]"
    common.print_parameter_summary(params_summary, title="Harbor Mirroring Configuration")

    if not args.check_only:
        if not common.confirm_action("Do you want to proceed with mirroring images to Harbor?", auto_approve=args.auto_approve):
            sys.exit(0)

    success = mirror_required_images(
        check_only=args.check_only,
        dry_run=args.dry_run,
        force=args.force,
    )

    if not success:
        sys.exit(1)

    if not args.check_only:
        common.print_success("Phase 3 Image Mirroring completed successfully.")


if __name__ == "__main__":
    main()

