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

"""Project and identity provider for Google Distributed Cloud (GDC) in application-workshop."""

import os
from pathlib import Path
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


def get_active_identity() -> Optional[str]:
    """Return active GDC identity from .env or gdcloud config."""
    user = os.environ.get("GDC_PLATFORM_ADMIN_USER") or os.environ.get("GDC_APP_OPERATOR_USER")
    if user:
        return user
    if common.check_tool_installed("gdcloud"):
        code, out, _ = common.run_command(
            ["gdcloud", "config", "get", "core/account"],
            check=False,
            capture_output=True,
        )
        if code == 0 and out.strip():
            return out.strip().splitlines()[-1]
    return "platform-admin@example.com"
