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

"""Quota + tier configuration endpoints.

  GET  /api/quota/config    all quota_config KV pairs (tier.*, quota.*, license.*)
  POST /api/quota/config    set one quota_config key
  GET  /api/quota/overview  aggregated view for /quota page (totals + utilization + tiers + recent)
  POST /api/quota/tier      assign/update an actor's tier
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from google.cloud import bigquery

from apps.api.shared.infrastructure.bq_client import bq as _bq, PROJECT, DATASET
from apps.api.shared.common import _json_safe

log = logging.getLogger("ge-obs")

router = APIRouter()


@router.get("/api/quota/config")
def quota_config_get() -> dict[str, Any]:
    rows = list(_bq.query(
        f"SELECT key, value, updated_at, updated_by FROM `{PROJECT}.{DATASET}.quota_config`"
    ).result())
    return {r.key: {"value": r.value, "updated_at": r.updated_at.isoformat() if r.updated_at else None, "updated_by": r.updated_by} for r in rows}


@router.post("/api/quota/config")
def quota_config_set(key: str, value: str, by: str = "manual") -> dict[str, Any]:
    """MERGE-update a single row of quota_config. Frontend edit-in-place
    calls this per keystroke on the /quota page's editable cells.

    All three args are user-controlled → bound as bigquery.ScalarQueryParameter
    (the startswith("tier.") prefix guard does NOT prevent SQL injection —
    a payload `tier.foo'; DROP TABLE ...` still passes). See R2 challenge
    findings (commit 2f7f530) for the injection-safe rewrite.

    Args:
        key: MUST start with `tier.` / `quota.` OR be one of the legacy
             keys `purchased_seats` / `claimed_window_days`. Rejected otherwise.
        value: opaque string; interpreted by consumer (view SQL casts to INT64
               for daily limits, keeps as STRING for enums).
        by: attribution ("manual" from CLI, "ui" from frontend edit).
    """
    # Allow any key that starts with 'tier.' / 'quota.' / legacy purchased_seats / claimed_window_days
    if not (key.startswith("tier.") or key.startswith("quota.")
            or key in {"purchased_seats", "claimed_window_days"}):
        raise HTTPException(400, "key must start with 'tier.' / 'quota.' or be a legacy key")
    # Parameterize all three inputs. The prefix guard on `key` does NOT
    # prevent SQL injection — a payload like `tier.foo'; DROP TABLE ...`
    # still passes startswith("tier."). Bind via ScalarQueryParameter so
    # BQ treats them as literals.
    _bq.query(
        f"MERGE `{PROJECT}.{DATASET}.quota_config` t "
        f"USING (SELECT @key k, @value v) s "
        f"ON t.key = s.k "
        f"WHEN MATCHED THEN UPDATE SET value=s.v, updated_at=CURRENT_TIMESTAMP(), updated_by=@by "
        f"WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by) "
        f"VALUES (s.k, s.v, CURRENT_TIMESTAMP(), @by)",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("key",   "STRING", key),
                bigquery.ScalarQueryParameter("value", "STRING", value),
                bigquery.ScalarQueryParameter("by",    "STRING", by),
            ]
        ),
    ).result()
    return {"key": key, "value": value, "ok": True}


@router.get("/api/quota/overview")
def quota_overview() -> JSONResponse:
    """Everything the /quota page needs in one round trip."""
    import concurrent.futures
    queries = {
        "totals":      f"SELECT * FROM `{PROJECT}.{DATASET}.v_quota_totals`",
        "utilization": f"SELECT * FROM `{PROJECT}.{DATASET}.v_quota_utilization` ORDER BY utilization DESC LIMIT 500",
        "tiers":       f"SELECT actor_email, tier, notes, assigned_at, assigned_by FROM `{PROJECT}.{DATASET}.user_tier` ORDER BY actor_email",
        "config":      f"SELECT key, value FROM `{PROJECT}.{DATASET}.quota_config` WHERE key LIKE 'tier.%' OR key LIKE 'quota.%' OR key LIKE 'license.%' ORDER BY key",
        "recent":      f"""SELECT * FROM `{PROJECT}.{DATASET}.v_daily_usage_per_user`
                           WHERE d >= DATE_SUB(DATE(CURRENT_TIMESTAMP(), 'America/Los_Angeles'), INTERVAL 6 DAY)
                           ORDER BY d DESC, actor_email, feature""",
    }
    def run(kv):
        k, sql = kv
        try:
            return k, [_json_safe(dict(r)) for r in _bq.query(sql).result()]
        except Exception as e:
            log.warning(f"quota_overview {k} failed: {e}")
            return k, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries)) as pool:
        out = dict(pool.map(run, queries.items()))
    # Also expose "today" in CA time so frontend knows what "today" means
    import datetime as _dt
    from zoneinfo import ZoneInfo
    today_ca = _dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    return JSONResponse(content={"today_ca": today_ca, **out},
                        headers={"Cache-Control": "no-store"})


@router.post("/api/quota/tier")
def quota_set_tier(email: str, tier: str, by: str = "manual", notes: str = "") -> dict[str, Any]:
    """Assign or update an actor's tier."""
    if tier not in {"standard", "plus"}:
        raise HTTPException(400, "tier must be 'standard' or 'plus'")
    if "'" in email or "'" in notes:
        raise HTTPException(400, "no single quotes in email/notes")
    _bq.query(f"""
        MERGE `{PROJECT}.{DATASET}.user_tier` t
        USING (SELECT '{email}' email, '{tier}' tier) s
        ON t.actor_email = s.email
        WHEN MATCHED THEN UPDATE SET tier = s.tier, assigned_at = CURRENT_TIMESTAMP(),
                                     assigned_by = '{by}', notes = '{notes}'
        WHEN NOT MATCHED THEN INSERT (actor_email, tier, assigned_at, assigned_by, notes)
          VALUES (s.email, s.tier, CURRENT_TIMESTAMP(), '{by}', '{notes}')
    """).result()
    return {"email": email, "tier": tier, "ok": True}
