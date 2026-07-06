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

"""Snapshot + license refresh endpoints.

  GET  /api/refresh/status   last refresh metadata per snapshot
  POST /api/refresh          re-materialize all snapshot tables + seats
  POST /api/refresh/seats    manually re-pull licenseConfigs

Also exposes `_start_seat_refresh_loop` — the FastAPI startup coroutine
that kicks the background auto-refresh (`main.py` wires it up via
`app.add_event_handler("startup", refresh._start_seat_refresh_loop)`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException
from google.cloud import bigquery

from apps.api.shared.infrastructure.bq_client import bq as _bq, PROJECT, DATASET
from apps.api.shared.common import (
    LICENSE_REFRESH_INTERVAL_SEC,
    VIEWS,
    snapshot_name,
    _json_safe,
)
from apps.api.contexts.quota.domain.license_parse import parse_license_configs

log = logging.getLogger("ge-obs")

router = APIRouter()


@router.get("/api/refresh/status")
def refresh_status() -> dict[str, Any]:
    """Last refresh metadata per snapshot."""
    sql = f"""
    SELECT snapshot_name, source_view, refreshed_at, row_count, refresh_seconds, triggered_by
    FROM `{PROJECT}.{DATASET}.snapshot_meta`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY snapshot_name ORDER BY refreshed_at DESC) = 1
    ORDER BY refreshed_at DESC
    """
    rows = [_json_safe(dict(r)) for r in _bq.query(sql).result()]
    most_recent = max((r["refreshed_at"] for r in rows), default=None)
    return {
        "snapshots": rows,
        "last_refresh": most_recent,
        "snapshot_count": len(rows),
    }


def _fetch_and_persist_license_configs() -> dict[str, Any]:
    """Pull live licenseConfigs from Discovery Engine and MERGE into quota_config.

    Uses ADC (same identity as BigQuery), so no shell-out to gcloud. Returns
    a summary dict; raises on unrecoverable errors so the caller can log.

    The aggregation logic lives in the quota domain
    (`contexts/quota/domain/license_parse.py`) — this function is now just
    the I/O shell: HTTP fetch + MERGE persistence.
    """
    import google.auth
    import google.auth.transport.requests
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    token = creds.token
    url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT}/locations/global/licenseConfigs"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("x-goog-user-project", PROJECT)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode() or "{}")
    configs = data.get("licenseConfigs", []) or []
    parsed = parse_license_configs(configs)
    if parsed["config_count"] == 0:
        # Preserve legacy response shape: `note` present, no MERGE call.
        return {"total_seats": 0, "config_count": 0, "by_tier": {},
                "note": parsed.get("note", "no licenseConfigs returned")}

    # Persist via MERGE (update-or-insert)
    def _merge(k: str, v: str) -> None:
        _bq.query(
            f"""
            MERGE `{PROJECT}.{DATASET}.quota_config` t
            USING (SELECT '{k}' k, @v v) s
            ON t.key = s.k
            WHEN MATCHED THEN UPDATE SET value = s.v, updated_at = CURRENT_TIMESTAMP(),
                                          updated_by = 'license-api'
            WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
              VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'license-api')
            """,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("v", "STRING", v)]
            ),
        ).result()
    _merge("license.total_seats", str(parsed["total_seats"]))
    _merge("license.config_count", str(parsed["config_count"]))
    _merge("license.raw", parsed["raw_json"])
    for tier, cnt in parsed["by_tier"].items():
        _merge(f"license.seats.{tier}", str(cnt))
    return {"total_seats": parsed["total_seats"],
            "config_count": parsed["config_count"],
            "by_tier": parsed["by_tier"]}


@router.post("/api/refresh/seats")
def refresh_seats() -> dict[str, Any]:
    """Manually re-pull licenseConfigs and persist to quota_config."""
    try:
        return {"ok": True, **_fetch_and_persist_license_configs()}
    except Exception as e:
        log.error("seat refresh failed: %s", e)
        raise HTTPException(500, f"seat refresh failed: {e}")


@router.post("/api/refresh")
def refresh_now(triggered_by: str = "manual") -> dict[str, Any]:
    """Re-materialize all snapshot tables. Returns per-table timing.

    On fresh deploys, some v_* views won't exist yet (source log-sink
    tables haven't materialized). Pre-check INFORMATION_SCHEMA.VIEWS so
    we can skip missing views quietly instead of logging every one as
    an ERROR (they're expected transient state, not operational alarms).
    """
    import time
    # Pre-check: which v_* views actually exist right now?
    existing_views = {
        r.table_name
        for r in _bq.query(
            f"SELECT table_name FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.VIEWS`"
        ).result()
    }
    results = []
    for view_name in VIEWS:
        snap = snapshot_name(view_name)
        if view_name not in existing_views:
            log.info("refresh skipped: %s (view %s not built yet — likely "
                     "waiting for log-sink source table)", snap, view_name)
            results.append({"snapshot": snap, "ok": False, "skipped": True,
                            "reason": f"view {view_name} does not exist"})
            continue
        start = time.time()
        try:
            _bq.query(
                f"CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.{snap}` AS "
                f"SELECT * FROM `{PROJECT}.{DATASET}.{view_name}`"
            ).result()
            dur = time.time() - start
            cnt_job = _bq.query(f"SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{snap}`").result()
            row_count = next(iter(cnt_job)).c
            _bq.query(
                f"INSERT INTO `{PROJECT}.{DATASET}.snapshot_meta` "
                f"(snapshot_name, source_view, refreshed_at, row_count, refresh_seconds, triggered_by) "
                f"VALUES ('{snap}', '{view_name}', CURRENT_TIMESTAMP(), {row_count}, {dur:.3f}, '{triggered_by}')"
            ).result()
            results.append({"snapshot": snap, "row_count": row_count, "seconds": round(dur, 2), "ok": True})
        except Exception as e:
            # Real unexpected error (SQL syntax, permission, quota, …).
            # Missing-view case is caught by the pre-check above and logged
            # at INFO — this branch keeps ERROR for genuine problems.
            log.error("refresh unexpected failure: %s — %s", snap, e)
            results.append({"snapshot": snap, "ok": False, "error": str(e)[:200]})
    # Also refresh live licenseConfigs so seat panel stays current.
    seats: dict[str, Any]
    try:
        seats = {"ok": True, **_fetch_and_persist_license_configs()}
    except Exception as e:
        log.error("seat refresh failed inside /api/refresh: %s", e)
        seats = {"ok": False, "error": str(e)[:200]}
    return {"refreshed": results, "ok_count": sum(1 for r in results if r["ok"]), "seats": seats}


# ============================================================
# Background: auto-refresh licenseConfigs on startup + every N hours.
# Snapshots are refreshed by BQ Scheduled Query; seats aren't (BQ SQL can't
# call REST). This asyncio loop bridges the gap while the API process runs.
#
# Registered from main.py via `app.add_event_handler("startup", ...)` —
# `@router.on_event(...)` doesn't fire for included routers.
# ============================================================
async def _start_seat_refresh_loop() -> None:
    if LICENSE_REFRESH_INTERVAL_SEC <= 0:
        log.info("seat auto-refresh disabled (LICENSE_REFRESH_INTERVAL_SEC=0)")
        return

    async def _loop() -> None:
        # Small initial delay so the process is fully ready before first hit
        await asyncio.sleep(5)
        while True:
            try:
                summary = await asyncio.to_thread(_fetch_and_persist_license_configs)
                log.info("seat auto-refresh ok: %s", summary)
            except Exception as e:
                log.warning("seat auto-refresh failed: %s", e)
            await asyncio.sleep(LICENSE_REFRESH_INTERVAL_SEC)

    asyncio.create_task(_loop())
