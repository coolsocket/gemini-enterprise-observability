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
    """Last refresh metadata per snapshot. Degrades gracefully to empty +
    hint when snapshot_meta table doesn't exist (fresh deploy, terraform
    hasn't run yet, or admin dropped the table)."""
    from google.api_core.exceptions import NotFound
    sql = f"""
    SELECT snapshot_name, source_view, refreshed_at, row_count, refresh_seconds, triggered_by
    FROM `{PROJECT}.{DATASET}.snapshot_meta`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY snapshot_name ORDER BY refreshed_at DESC) = 1
    ORDER BY refreshed_at DESC
    """
    try:
        rows = [_json_safe(dict(r)) for r in _bq.query(sql).result()]
    except NotFound:
        return {
            "snapshots": [], "last_refresh": None, "snapshot_count": 0,
            "data_earliest": None, "data_latest": None, "data_days": 0,
            "note": (
                f"snapshot_meta table not present in {PROJECT}.{DATASET}. "
                "Run `make bootstrap` (or `terraform apply`) to create it, "
                "then POST /api/refresh to populate."
            ),
        }
    most_recent = max((r["refreshed_at"] for r in rows), default=None)

    # Data window signal — operator can tell at a glance whether
    # `make backfill` has been run: earliest timestamp across the two
    # highest-volume sink tables (audit + user_activity). If earliest
    # is close to snapshot_meta's oldest triggered_by=hotfix row →
    # sink-only coverage. If much older → backfill ran.
    data_earliest = None
    data_latest = None
    try:
        window_sql = f"""
        SELECT MIN(ts) mn, MAX(ts) mx FROM (
          SELECT MIN(timestamp) ts
            FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_data_access`
          UNION ALL
          SELECT MIN(timestamp)
            FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
          UNION ALL
          SELECT MAX(timestamp)
            FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_data_access`
          UNION ALL
          SELECT MAX(timestamp)
            FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
        )
        """
        window_row = next(iter(_bq.query(window_sql).result()), None)
        if window_row and window_row.mn is not None:
            data_earliest = window_row.mn.isoformat()
            data_latest = window_row.mx.isoformat() if window_row.mx else None
    except NotFound:
        pass  # sink tables absent — first-time deploy before any traffic

    data_days = None
    if data_earliest and data_latest:
        from datetime import datetime as _dt
        try:
            span = (_dt.fromisoformat(data_latest) - _dt.fromisoformat(data_earliest))
            data_days = round(span.total_seconds() / 86400, 1)
        except Exception:
            pass

    return {
        "snapshots": rows,
        "last_refresh": most_recent,
        "snapshot_count": len(rows),
        "data_earliest": data_earliest,
        "data_latest": data_latest,
        "data_days": data_days,
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

    # Persist via MERGE (update-or-insert). Parameterize BOTH k and v —
    # k comes from GE license API response (Google-owned so low practical
    # risk, but defensive is one extra ScalarQueryParameter).
    def _merge(k: str, v: str) -> None:
        """MERGE a single quota_config key. Update semantics:
        WHEN MATCHED → overwrite (this is authoritative license data,
        NOT admin-editable tier defaults which use WHEN NOT MATCHED)."""
        _bq.query(
            f"""
            MERGE `{PROJECT}.{DATASET}.quota_config` t
            USING (SELECT @k k, @v v) s
            ON t.key = s.k
            WHEN MATCHED THEN UPDATE SET value = s.v, updated_at = CURRENT_TIMESTAMP(),
                                          updated_by = 'license-api'
            WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
              VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'license-api')
            """,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("k", "STRING", k),
                    bigquery.ScalarQueryParameter("v", "STRING", v),
                ]
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


def _refresh_one_view(view_name: str, triggered_by: str) -> dict[str, Any]:
    """Refresh a single s_* snapshot from its v_* view. Parameterises
    triggered_by (previously an f-string interpolation — user-controllable
    param, R1 challenge finding 2026-07-08). Returns per-snapshot summary."""
    import time
    snap = snapshot_name(view_name)
    start = time.time()
    try:
        _bq.query(
            f"CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.{snap}` AS "
            f"SELECT * FROM `{PROJECT}.{DATASET}.{view_name}`"
        ).result()
        dur = time.time() - start
        cnt_job = _bq.query(
            f"SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{snap}`"
        ).result()
        row_count = next(iter(cnt_job)).c
        # Parameterized INSERT — triggered_by is user input, must not be
        # concatenated. snap / view_name are internal constants (fine).
        _bq.query(
            f"INSERT INTO `{PROJECT}.{DATASET}.snapshot_meta` "
            f"(snapshot_name, source_view, refreshed_at, row_count, "
            f"refresh_seconds, triggered_by) "
            f"VALUES ('{snap}', '{view_name}', CURRENT_TIMESTAMP(), "
            f"{row_count}, {dur:.3f}, @triggered_by)",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("triggered_by", "STRING", triggered_by),
                ]
            ),
        ).result()
        return {"snapshot": snap, "row_count": row_count,
                "seconds": round(dur, 2), "ok": True}
    except Exception as e:
        log.error("refresh unexpected failure: %s — %s", snap, e)
        return {"snapshot": snap, "ok": False, "error": str(e)[:200]}


@router.post("/api/refresh")
def refresh_now(triggered_by: str = "manual") -> dict[str, Any]:
    """Re-materialize all snapshot tables in parallel. Returns per-table timing.

    On fresh deploys, some v_* views won't exist yet (source log-sink
    tables haven't materialized). Pre-check INFORMATION_SCHEMA.VIEWS so
    we can skip missing views quietly instead of logging every one as
    an ERROR (they're expected transient state, not operational alarms).

    Fans out via ThreadPoolExecutor — cuts wall time from ~60s serial
    (21 views × 3 queries × ~1s) to max-single-view. Otherwise the
    HTTP response times out before all views finish and the caller sees
    500 despite work still completing in background.
    """
    import concurrent.futures
    # Pre-check: which v_* views actually exist right now?
    existing_views = {
        r.table_name
        for r in _bq.query(
            f"SELECT table_name FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.VIEWS`"
        ).result()
    }
    results: list[dict[str, Any]] = []
    to_refresh: list[str] = []
    for view_name in VIEWS:
        snap = snapshot_name(view_name)
        if view_name not in existing_views:
            log.info("refresh skipped: %s (view %s not built yet — likely "
                     "waiting for log-sink source table)", snap, view_name)
            results.append({"snapshot": snap, "ok": False, "skipped": True,
                            "reason": f"view {view_name} does not exist"})
            continue
        to_refresh.append(view_name)

    # Parallel fan-out. BQ handles concurrent CREATE OR REPLACE fine —
    # bounded workers to keep slot usage sane on shared reservations.
    if to_refresh:
        from apps.api.shared.infrastructure.bq_client import MAX_WORKERS_PER_ROUTE
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS_PER_ROUTE, len(to_refresh))
        ) as pool:
            for r in pool.map(lambda v: _refresh_one_view(v, triggered_by), to_refresh):
                results.append(r)

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
    """FastAPI lifespan hook. Kicks a background task that re-pulls
    licenseConfigs every LICENSE_REFRESH_INTERVAL_SEC (24h default).
    Set the env var to 0 to disable — POST /api/refresh/seats still
    triggers on-demand. Returns immediately; the loop runs forever
    inside `_loop()` via asyncio.create_task."""
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
