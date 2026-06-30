"""GE Observability — FastAPI backend.

Routes
  GET /api/healthz       liveness
  GET /api/meta          project + dataset + view labels
  GET /api/views         list of views (alias of meta.views)
  GET /api/v/{view}      rows from one view
  GET /api/summary       precomputed KPIs
  GET /                  React SPA (served from ../web/dist)
  GET /{any}             SPA fallback for client-side routes
"""
from __future__ import annotations

import datetime as _dt
import decimal
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ge-obs")

PROJECT = os.environ.get("BQ_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
DATASET = os.environ.get("BQ_DATASET", "ge_observability")
if not PROJECT:
    raise RuntimeError("BQ_PROJECT (or GOOGLE_CLOUD_PROJECT) env var required")

VIEWS: dict[str, dict[str, str]] = {
    "v_user_persona":             {"label": "用户画像",           "desc": "POWER_USER / ACTIVE_CONSUMER / TRIAL / BUILDER / EXPLORER / LURKER / AUTOMATION / SIMULATED"},
    "v_conversations":            {"label": "原始对话",           "desc": "仅 prompt 端 — 用于核对原始日志"},
    "v_conversations_with_response": {"label": "完整对话",         "desc": "prompt + 模型回答（按 engine + 时间窗模糊配对）"},
    "v_choices":                  {"label": "模型回答(chunks)",   "desc": "gen_ai.choice 表里的流式 chunk（原始）"},
    "v_choices_agg":              {"label": "模型回答(聚合)",     "desc": "按 trace_id 聚合的完整响应 + 最终 finish_reason"},
    "v_admin_activity":           {"label": "管理操作时间线",     "desc": "Path 3 Admin Activity 时间线"},
    "v_builders":                 {"label": "Builder 排行榜",     "desc": "Create / Delete / Net 统计"},
    "v_engine_adoption":          {"label": "Engine 采纳度",      "desc": "每 engine 的 unique users / chat / sessions"},
    "v_zero_use_seats":           {"label": "0 使用 seats",       "desc": "近 14 天没动作的用户"},
    "v_dau":                      {"label": "DAU 趋势",           "desc": "每日活跃用户与事件量"},
    "v_data_access":              {"label": "Data Access 时间线", "desc": "每笔数据面读取（按真实 method 标注）"},
    "v_data_access_summary":      {"label": "谁查了什么",         "desc": "actor × engine 按 chat/session/feedback 分桶"},
    "v_user_usage":               {"label": "用户 × Engine",      "desc": "每用户在每个 engine 上的活动量"},
    "v_session_files":            {"label": "文件活动会话",        "desc": "用户与 session files 的交互（list/download）"},
    "v_agent_usage":              {"label": "Agent 调用统计",      "desc": "每个子 agent 接到的 chat traces / chunks"},
}

# Views that have an `origin` column — supports ?origin= filter
VIEWS_WITH_ORIGIN: set[str] = {
    "v_user_persona", "v_conversations", "v_conversations_with_response",
    "v_admin_activity", "v_builders", "v_data_access",
    "v_data_access_summary", "v_user_usage", "v_session_files",
}

# Snapshot table name (s_*) corresponds to each view (v_*)
def snapshot_name(view: str) -> str:
    return "s_" + view[2:] if view.startswith("v_") else view

app = FastAPI(title="GE Observability", version="2.0")
_bq = bigquery.Client(project=PROJECT)
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


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


_VALID_ORIGINS = {"HUMAN", "AUTOMATION", "UNKNOWN", "SIMULATED"}

# Views that have an `engine_id_raw` column — supports ?engine_id= filter
VIEWS_WITH_ENGINE: set[str] = {
    "v_conversations", "v_conversations_with_response",
    "v_admin_activity", "v_data_access", "v_data_access_summary",
    "v_user_usage", "v_engine_adoption", "v_session_files", "v_agent_usage",
}


def _rows(view: str, limit: int = 1000, origin: str | None = None,
          engine_id: str | None = None, live: bool = False) -> list[dict[str, Any]]:
    if view not in VIEWS:
        raise HTTPException(status_code=404, detail=f"Unknown view: {view}")
    where_clauses = []
    if origin:
        if origin not in _VALID_ORIGINS:
            raise HTTPException(status_code=400, detail=f"origin must be one of {_VALID_ORIGINS}")
        if view not in VIEWS_WITH_ORIGIN:
            raise HTTPException(status_code=400, detail=f"view {view} doesn't have an origin column")
        where_clauses.append(f"origin = '{origin}'")
    if engine_id:
        if view not in VIEWS_WITH_ENGINE:
            raise HTTPException(status_code=400, detail=f"view {view} doesn't have an engine_id column")
        # Some views use `engine_id`, others `engine_id_raw` (aliased at view creation time)
        engine_id_cols = {"v_data_access_summary", "v_user_usage", "v_engine_adoption"}
        col = "engine_id" if view in engine_id_cols else "engine_id_raw"
        # SQL escape
        if not engine_id.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail="invalid engine_id")
        where_clauses.append(f"{col} = '{engine_id}'")
    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    # Default: read from snapshot table (fast); ?live=true bypasses to view (fresh).
    src = view if live else snapshot_name(view)
    sql = f"SELECT * FROM `{PROJECT}.{DATASET}.{src}`{where} LIMIT {limit}"
    log.info("query: %s", sql)
    return [_json_safe(dict(r)) for r in _bq.query(sql).result()]


@app.get("/api/engines")
def list_engines() -> dict[str, Any]:
    """List all known engines (from engine_metadata table) for the engine selector."""
    rows = list(_bq.query(
        f"SELECT engine_id, display_name, solution_type FROM `{PROJECT}.{DATASET}.engine_metadata` ORDER BY display_name"
    ).result())
    return {"engines": [{"id": r.engine_id, "name": r.display_name, "type": r.solution_type} for r in rows]}


@app.get("/api/resources/alive")
def alive_resources() -> dict[str, Any]:
    rows = list(_bq.query(
        f"SELECT resource_type, COUNT(*) c FROM `{PROJECT}.{DATASET}.resources_alive` GROUP BY resource_type"
    ).result())
    return {r.resource_type: r.c for r in rows}


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "project": PROJECT, "dataset": DATASET}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "dataset": DATASET,
        "sink_name": "ge-observability-unified",
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }


@app.get("/api/views")
def list_views() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "dataset": DATASET,
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }


@app.get("/api/v/{view}")
def view_rows(view: str, limit: int = 1000, origin: str | None = None,
              engine_id: str | None = None, live: bool = False) -> JSONResponse:
    rows = _rows(view, limit=limit, origin=origin, engine_id=engine_id, live=live)
    return JSONResponse(
        content={"view": view, "rows": rows, "count": len(rows),
                 "origin": origin, "engine_id": engine_id,
                 "source": "live_view" if live else "snapshot"},
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# Snapshot refresh endpoints
# ============================================================

@app.get("/api/refresh/status")
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


@app.post("/api/refresh")
def refresh_now(triggered_by: str = "manual") -> dict[str, Any]:
    """Re-materialize all snapshot tables. Returns per-table timing."""
    import time
    results = []
    for view_name in VIEWS:
        snap = snapshot_name(view_name)
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
            log.error("refresh failed: %s — %s", snap, e)
            results.append({"snapshot": snap, "ok": False, "error": str(e)[:200]})
    return {"refreshed": results, "ok_count": sum(1 for r in results if r["ok"])}


# ============================================================
# Quota config endpoints
# ============================================================

@app.get("/api/quota/config")
def quota_config_get() -> dict[str, Any]:
    rows = list(_bq.query(
        f"SELECT key, value, updated_at, updated_by FROM `{PROJECT}.{DATASET}.quota_config`"
    ).result())
    return {r.key: {"value": r.value, "updated_at": r.updated_at.isoformat() if r.updated_at else None, "updated_by": r.updated_by} for r in rows}


@app.post("/api/quota/config")
def quota_config_set(key: str, value: str, by: str = "manual") -> dict[str, Any]:
    allowed = {"purchased_seats", "claimed_window_days"}
    if key not in allowed:
        raise HTTPException(400, f"key must be one of {allowed}")
    # MERGE
    _bq.query(
        f"MERGE `{PROJECT}.{DATASET}.quota_config` t "
        f"USING (SELECT '{key}' k, '{value}' v) s "
        f"ON t.key = s.k "
        f"WHEN MATCHED THEN UPDATE SET value=s.v, updated_at=CURRENT_TIMESTAMP(), updated_by='{by}' "
        f"WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by) "
        f"VALUES (s.k, s.v, CURRENT_TIMESTAMP(), '{by}')"
    ).result()
    return {"key": key, "value": value, "ok": True}


@app.get("/api/summary")
def summary(origin: str | None = None, engine_id: str | None = None, live: bool = False) -> dict[str, Any]:
    """KPI summary. ?origin=HUMAN filters out service accounts.

    Restructured to surface two-group semantics:
      adoption_quality: humans only, focused on usage
      governance_audit: all origins, focused on operations
    """
    origin_filter = ""
    if origin in _VALID_ORIGINS:
        origin_filter = f" AND origin = '{origin}'"
    engine_filter_summary = ""  # for v_data_access_summary uses engine_id col
    engine_filter_conv = ""     # for v_conversations uses engine_id_raw col
    if engine_id and engine_id.replace("-", "").replace("_", "").isalnum():
        engine_filter_summary = f" AND engine_id = '{engine_id}'"
        engine_filter_conv = f" AND engine_id_raw = '{engine_id}'"

    # Default to snapshots for speed; ?live=true hits views
    p = "v_user_persona" if live else "s_user_persona"
    b = "v_builders" if live else "s_builders"
    da = "v_data_access_summary" if live else "s_data_access_summary"
    ea = "v_engine_adoption" if live else "s_engine_adoption"
    cv = "v_conversations" if live else "s_conversations"

    sql = f"""
    WITH
      humans AS (
        SELECT persona, chat_turns_total, chat_turns_7d
        FROM `{PROJECT}.{DATASET}.{p}`
        WHERE origin IN ('HUMAN', 'SIMULATED')
      ),
      a AS (SELECT SUM(total_admin_actions) c FROM `{PROJECT}.{DATASET}.{b}`
            WHERE TRUE {origin_filter}),
      d AS (SELECT SUM(chat_turns) chat,
                   SUM(total_data_access) total
            FROM `{PROJECT}.{DATASET}.{da}`
            WHERE TRUE {origin_filter} {engine_filter_summary}),
      e AS (SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{ea}`),
      adm AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_activity`),
      dac AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_data_access`),
      ua  AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`),
      conv AS (SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{cv}`
               WHERE TRUE {origin_filter} {engine_filter_conv})
    SELECT
      -- 采纳与质量（HUMAN + SIMULATED — 真人 + 模拟人）
      (SELECT COUNT(*) FROM humans) AS human_users,
      (SELECT COUNT(*) FROM humans WHERE persona = 'POWER_USER') AS power_users,
      (SELECT COUNT(*) FROM humans WHERE persona = 'ACTIVE_CONSUMER') AS active_consumers,
      (SELECT COUNT(*) FROM humans WHERE persona = 'TRIAL') AS trial_users,
      (SELECT COUNT(*) FROM humans WHERE persona = 'BUILDER') AS human_builders,
      (SELECT COUNT(*) FROM humans WHERE persona = 'EXPLORER') AS explorers,
      (SELECT COUNT(*) FROM humans WHERE persona = 'LURKER') AS lurkers,
      (SELECT SUM(chat_turns_7d) FROM humans) AS human_chat_turns_7d,
      conv.c AS conversations_captured,
      -- 治理与审计
      a.c AS admin_actions,
      d.chat AS chat_turns_total,
      d.total AS data_access_calls,
      e.c AS engines_tracked,
      -- 数据新鲜度
      adm.ts AS last_admin_event,
      dac.ts AS last_data_access_event,
      ua.ts  AS last_user_activity_event
    FROM a, d, e, adm, dac, ua, conv
    """
    row = next(iter(_bq.query(sql).result()), None)
    return _json_safe(dict(row)) if row else {}


# --- React SPA (built static)
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIST / "index.html")


if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="spa-assets")


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/") or path.startswith("assets/"):
        raise HTTPException(status_code=404)
    target = WEB_DIST / path
    if target.is_file():
        return FileResponse(target)
    return FileResponse(WEB_DIST / "index.html")
