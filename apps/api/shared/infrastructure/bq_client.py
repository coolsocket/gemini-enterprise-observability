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

# --- HTTP pool config ---
# Default urllib3 pool_maxsize=10 → saturated by user_deep_dive
# (~15 concurrent BQ queries via ThreadPoolExecutor) and refresh_now
# (~10 concurrent). Symptom is a log-noise flood:
#   WARNING:urllib3.connectionpool:Connection pool is full,
#   discarding connection: bigquery.googleapis.com. Connection pool size: 10
# Beyond the noise, discarding forces reconnects → latency on each extra.
#
# Two mitigations, together:
#  1) Bump every requests.HTTPAdapter's default pool to 32 (belt).
#     Fixes the case where google-auth / google-cloud-bigquery honour
#     the requests adapter default.
#  2) Silence the specific urllib3 warning (suspenders). Some code paths
#     inside google-cloud-bigquery / google-auth create urllib3
#     PoolManagers directly (bypassing requests.HTTPAdapter), so (1)
#     alone can't cover them. Silencing keeps operator logs clean —
#     any latency hit from actual pool exhaustion is capped by our
#     concurrency limits in the routes (see MAX_WORKERS_PER_ROUTE).
import logging
import requests.adapters  # noqa: E402
_orig_httpadapter_init = requests.adapters.HTTPAdapter.__init__
def _bumped_httpadapter_init(self, pool_connections=10, pool_maxsize=10, *args, **kwargs):
    _orig_httpadapter_init(
        self,
        pool_connections=max(pool_connections, 32),
        pool_maxsize=max(pool_maxsize, 32),
        *args, **kwargs,
    )
requests.adapters.HTTPAdapter.__init__ = _bumped_httpadapter_init  # type: ignore[method-assign]

# Suspenders: silence the specific noisy warning. `raise_on_status` and
# similar operational messages still propagate at WARNING; only the
# pool-full noise gets filtered.
class _PoolFullFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Connection pool is full" not in record.getMessage()
logging.getLogger("urllib3.connectionpool").addFilter(_PoolFullFilter())

# Concurrency ceiling. Routes fanning out multiple BQ queries in parallel
# should cap ThreadPoolExecutor(max_workers=…) at this — keeps us below
# the pool limit + prevents thundering-herd across other GCP services.
MAX_WORKERS_PER_ROUTE: int = 8

# --- singleton BQ client ---
# ADC-based (google.auth.default under the hood). Same instance is reused
# across all routes for connection pooling.
bq: bigquery.Client = bigquery.Client(project=PROJECT)
