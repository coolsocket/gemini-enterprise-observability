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

"""Shared runtime constants + JSON helpers.

Extracted from apps/api/main.py (2026-07-06, Phase 2 of the TDDD split).
Phase 3 moved the view catalogue + `snapshot_name` into the observability
context (apps/api/contexts/observability/domain/view_registry.py). This
module keeps the truly cross-cutting pieces (`_json_safe`, `_VALID_ORIGINS`,
`LICENSE_REFRESH_INTERVAL_SEC`) and re-exports the moved names so existing
imports (`from apps.api.shared.common import VIEWS, snapshot_name, ...`)
keep working without touching consumers.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import os
from typing import Any

# --- Compat re-exports (moved to contexts/observability/domain in Phase 3) ---
# Keep imports working for anything that still reaches into shared/common
# for the view registry. New code should import from the context directly.
from apps.api.contexts.observability.domain.view_registry import (  # noqa: F401
    VIEWS,
    VIEWS_WITH_ORIGIN,
    VIEWS_WITH_ENGINE,
    VIEW_TIME_COL,
    snapshot_name,
)


# License refresh cadence for the seat-count auto-refresh loop (24h default).
# Set to 0 to disable the background loop entirely (still exposed via
# POST /api/refresh/seats).
LICENSE_REFRESH_INTERVAL_SEC = int(os.environ.get("LICENSE_REFRESH_INTERVAL_SEC", str(24 * 3600)))

# Snapshot re-materialization cadence for the in-process auto-refresh loop
# (6h default). Snapshots (s_*) are what the dashboard reads by default;
# without a cadence they freeze at the last manual POST /api/refresh — the
# "vivo stuck at 7.9" bug (2026-07-15). This loop is the deploy-target-
# agnostic guarantee (works on Cloud Run / VM / local) that snapshots stay
# current. Set to 0 to disable (e.g. when a BQ Scheduled Query owns refresh).
SNAPSHOT_REFRESH_INTERVAL_SEC = int(os.environ.get("SNAPSHOT_REFRESH_INTERVAL_SEC", str(6 * 3600)))


_VALID_ORIGINS = {"HUMAN", "AUTOMATION", "UNKNOWN", "SIMULATED"}


def _json_safe(v: Any) -> Any:
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v
