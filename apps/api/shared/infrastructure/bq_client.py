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

"""Shared BigQuery client + runtime config.

Was inlined in apps/api/main.py; extracted 2026-07-06 as part of the
TDDD refactor. Every route module imports its BQ handle from here so
that (a) there's one place to configure ADC / retries / connection
pooling, and (b) tests / notebooks can monkey-patch it in one spot.

Env vars (read at import time — same behavior as before the extract):
  BQ_PROJECT         (required — or GOOGLE_CLOUD_PROJECT as fallback)
  BQ_DATASET         (default: ge_observability)
  SIM_PREFIX         (default: sim- — prefix stripped from actor emails)
"""
from __future__ import annotations

import os
from typing import Optional

from google.cloud import bigquery

# --- runtime config (read once at import; env-var-driven, no CLI args) ---
PROJECT: Optional[str] = os.environ.get("BQ_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
DATASET: str = os.environ.get("BQ_DATASET", "ge_observability")
SIM_PREFIX: str = os.environ.get("SIM_PREFIX", "sim-")

if not PROJECT:
    raise RuntimeError(
        "BQ_PROJECT (or GOOGLE_CLOUD_PROJECT) env var required. "
        "Set it in .env or on the command line — see docs/DEPLOYMENT.md."
    )

# --- singleton BQ client ---
# ADC-based (google.auth.default under the hood). Same instance is reused
# across all routes for connection pooling.
bq: bigquery.Client = bigquery.Client(project=PROJECT)


def table(name: str) -> str:
    """Fully-qualified `project.dataset.name` for use in SQL string interpolation."""
    return f"{PROJECT}.{DATASET}.{name}"
