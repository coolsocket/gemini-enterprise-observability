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
    "v_agentspace_navigation":          {"label": "Agentspace 入口浏览",  "desc": "用户打开了哪个 special agent / NotebookLM / Deep Research 页面"},
    "v_agentspace_navigation_summary":  {"label": "Agentspace 入口汇总",  "desc": "按用户 pivot：home / gallery / deep-research / notebook-lm / custom agent 访问次数"},
    "v_agent_directory":                {"label": "Agent 目录",          "desc": "每个 agent 一行：built-in (Deep Research / NotebookLM / A2A) + custom"},
    "v_deep_research_prompts":          {"label": "Deep Research prompts", "desc": "AsyncAssist 事件反推的 prompt (±60s 时间窗)"},
    "v_custom_agent_prompts":           {"label": "Custom agent prompts",  "desc": "agent 页打开后 5min 内的 StreamAssist 归到该 agent"},
    "v_daily_usage_per_user":           {"label": "每日使用量",             "desc": "per (user × 加州day × feature) 计数"},
    "v_quota_utilization":              {"label": "配额使用率",             "desc": "今日每用户各 feature 使用 vs tier 上限"},
    "v_quota_totals":                   {"label": "配额总览",               "desc": "全平台各 feature 已用/总配额/超额人数"},
}

# Views that have an `origin` column — supports ?origin= filter
VIEWS_WITH_ORIGIN: set[str] = {
    "v_user_persona", "v_conversations", "v_conversations_with_response",
    "v_admin_activity", "v_builders", "v_data_access",
    "v_data_access_summary", "v_user_usage", "v_session_files",
    "v_agentspace_navigation", "v_agentspace_navigation_summary",
    "v_deep_research_prompts", "v_custom_agent_prompts",
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
    "v_agentspace_navigation",
}


# Per-view time column for since_hours filter (None = no time filter possible)
VIEW_TIME_COL: dict[str, str | None] = {
    "v_admin_activity":              "timestamp",
    "v_builders":                    "last_admin_action",
    "v_data_access":                 "timestamp",
    "v_data_access_summary":         "last_access",
    "v_conversations":               "timestamp",
    "v_conversations_with_response": "timestamp",
    "v_choices":                     "timestamp",
    "v_choices_agg":                 None,  # aggregated, no representative ts
    "v_user_persona":                "last_seen",
    "v_user_usage":                  "last_seen",
    "v_engine_adoption":             None,
    "v_zero_use_seats":              None,
    "v_dau":                         "d",  # DATE not TIMESTAMP
    "v_session_files":               "last_op",
    "v_agent_usage":                 None,
    "v_agentspace_navigation":       "last_visit",
    "v_agentspace_navigation_summary": "last_visit",
    "v_agent_directory":             "last_activity",
    "v_deep_research_prompts":       "dr_ts",
    "v_custom_agent_prompts":        "prompt_ts",
}


def _rows(view: str, limit: int = 1000, origin: str | None = None,
          engine_id: str | None = None, live: bool = False,
          since_hours: int | None = None) -> list[dict[str, Any]]:
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
    if since_hours and since_hours > 0:
        tcol = VIEW_TIME_COL.get(view)
        if tcol:
            # DATE columns need DATE cutoff; TIMESTAMP columns need TIMESTAMP cutoff
            if tcol == "d":
                where_clauses.append(f"{tcol} >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(since_hours // 24)} DAY)")
            else:
                where_clauses.append(f"{tcol} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(since_hours)} HOUR)")
    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    # Default: read from snapshot table (fast); ?live=true bypasses to view (fresh).
    # If since_hours is set, force live so we're not filtered by stale snapshot age.
    if since_hours:
        live = True
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
              engine_id: str | None = None, live: bool = False,
              since_hours: int | None = None) -> JSONResponse:
    rows = _rows(view, limit=limit, origin=origin, engine_id=engine_id,
                 live=live, since_hours=since_hours)
    return JSONResponse(
        content={"view": view, "rows": rows, "count": len(rows),
                 "origin": origin, "engine_id": engine_id,
                 "since_hours": since_hours,
                 "source": "live_view" if (live or since_hours) else "snapshot"},
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# /api/user — single-user deep dive (aggregated across all views)
# ============================================================

@app.get("/api/agents")
def list_agents() -> dict[str, Any]:
    """All known agents, with usage totals + top user."""
    sql = f"SELECT * FROM `{PROJECT}.{DATASET}.{snapshot_name('v_agent_directory')}` ORDER BY total DESC"
    try:
        rows = [_json_safe(dict(r)) for r in _bq.query(sql).result()]
    except Exception:
        # snapshot may not exist yet; fall back to live view
        rows = [_json_safe(dict(r)) for r in _bq.query(
            f"SELECT * FROM `{PROJECT}.{DATASET}.v_agent_directory` ORDER BY total DESC"
        ).result()]
    return {"agents": rows, "count": len(rows)}


@app.get("/api/agent/{agent_id}")
def agent_deep_dive(agent_id: str) -> JSONResponse:
    """All users + events for a given agent."""
    import concurrent.futures

    def with_param(sql: str):
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("aid", "STRING", agent_id)]
            )
            return [_json_safe(dict(r)) for r in _bq.query(sql, job_config=job_config).result()]
        except Exception as e:
            log.warning(f"agent_deep_dive {agent_id}: {e}")
            return []

    # Different aggregation strategy per agent kind.
    # Built-in: aggregate from data_access_summary's typed buckets.
    # Custom:   aggregate from v_agentspace_navigation by agent_id.
    # All built-in agents pull events from v_data_access (which has action/full_method derived)
    if agent_id == "deep_research":
        per_user_sql = f"""
        SELECT actor_email, origin, deep_research_calls AS calls, last_access AS last_seen
        FROM `{PROJECT}.{DATASET}.v_data_access_summary`
        WHERE deep_research_calls > 0 ORDER BY deep_research_calls DESC
        """
        events_sql = f"""
        SELECT timestamp, action, full_method, engine_id_raw, actor_email
        FROM `{PROJECT}.{DATASET}.v_data_access`
        WHERE full_method LIKE '%AsyncAssist%' OR full_method LIKE '%ReadAsyncAssist%'
        ORDER BY timestamp DESC LIMIT 200
        """
    elif agent_id == "notebooklm":
        per_user_sql = f"""
        SELECT actor_email, origin,
               notebooklm_notebook_ops + notebooklm_content_ops + notebooklm_audio_ops AS calls,
               last_access AS last_seen
        FROM `{PROJECT}.{DATASET}.v_data_access_summary`
        WHERE notebooklm_notebook_ops + notebooklm_content_ops + notebooklm_audio_ops > 0
        ORDER BY calls DESC
        """
        events_sql = f"""
        SELECT timestamp, action, full_method, engine_id_raw, actor_email
        FROM `{PROJECT}.{DATASET}.v_data_access`
        WHERE full_method LIKE '%notebooklm.%'
        ORDER BY timestamp DESC LIMIT 200
        """
    elif agent_id == "a2a_protocol":
        per_user_sql = f"""
        SELECT actor_email, origin, a2a_invocations AS calls, last_access AS last_seen
        FROM `{PROJECT}.{DATASET}.v_data_access_summary`
        WHERE a2a_invocations > 0 ORDER BY a2a_invocations DESC
        """
        events_sql = f"""
        SELECT timestamp, action, full_method, engine_id_raw, actor_email
        FROM `{PROJECT}.{DATASET}.v_data_access`
        WHERE full_method LIKE '%assistants.agents.a2a.v1.%'
        ORDER BY timestamp DESC LIMIT 200
        """
    else:
        # Custom agent — from agentspace_navigation + raw user_activity events
        per_user_sql = f"""
        SELECT actor_email, origin, visits AS calls, last_visit AS last_seen
        FROM `{PROJECT}.{DATASET}.v_agentspace_navigation`
        WHERE page_type = 'agent' AND agent_id = @aid
        ORDER BY visits DESC
        """
        events_sql = f"""
        SELECT timestamp,
               'OpenAgent' AS action,
               REGEXP_REPLACE(jsonPayload.useriamprincipal, r'^vivo-sim-', 'demo-') AS actor_email,
               jsonPayload.request.userevent.agentspaceinfo.agentinfo.agentid AS agent_id
        FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
        WHERE jsonPayload.request.userevent.agentspaceinfo.agentinfo.agentid = @aid
        ORDER BY timestamp DESC LIMIT 200
        """

    users = with_param(per_user_sql)
    events = with_param(events_sql)

    # Pull reverse-attributed prompts (Deep Research uses different view; custom agent has its own)
    if agent_id == "deep_research":
        prompts = [_json_safe(dict(r)) for r in _bq.query(
            f"""SELECT dr_ts AS event_ts, dr_action, actor_email, attributed_prompt AS prompt,
                       attribution_delta_sec, engine_display_name
                FROM `{PROJECT}.{DATASET}.v_deep_research_prompts`
                WHERE attributed_prompt IS NOT NULL
                ORDER BY dr_ts DESC LIMIT 100"""
        ).result()]
    elif agent_id in ("notebooklm", "a2a_protocol"):
        prompts = []  # NotebookLM/A2A don't emit prompt-adjacent StreamAssist
    else:
        # Custom agent
        prompts = with_param(f"""
            SELECT prompt_ts AS event_ts, actor_email, prompt, elapsed_since_open_sec, engine_display_name, agent_open_ts
            FROM `{PROJECT}.{DATASET}.v_custom_agent_prompts`
            WHERE agent_id = @aid
            ORDER BY prompt_ts DESC LIMIT 100
        """)

    # Pull the directory row for the agent header
    dir_row = with_param(f"SELECT * FROM `{PROJECT}.{DATASET}.v_agent_directory` WHERE agent_id = @aid LIMIT 1")

    return JSONResponse(content={
        "agent_id": agent_id,
        "directory": dir_row[0] if dir_row else None,
        "users": users,
        "events": events,
        "prompts": prompts,
    }, headers={"Cache-Control": "no-store"})


@app.get("/api/users")
def list_users(since_hours: int | None = None) -> dict[str, Any]:
    """All actors who've shown up anywhere, with rich per-user dimensions for picker."""
    time_filter = ""
    if since_hours and since_hours > 0:
        time_filter = f"WHERE last_access >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(since_hours)} HOUR)"
    sql = f"""
    WITH base AS (
      SELECT
        actor_email,
        ANY_VALUE(origin) AS origin,
        SUM(chat_turns) AS chat_turns,
        SUM(deep_research_calls) AS deep_research_calls,
        SUM(notebooklm_notebook_ops + notebooklm_content_ops + notebooklm_audio_ops) AS notebooklm_ops,
        SUM(a2a_invocations) AS a2a_invocations,
        SUM(programmatic_searches) AS programmatic_searches,
        SUM(session_files) AS session_files,
        SUM(total_data_access) AS total_data_access,
        COUNT(DISTINCT IF(engine_id IS NOT NULL, engine_id, NULL)) AS engines_touched,
        MAX(last_access) AS last_access
      FROM `{PROJECT}.{DATASET}.v_data_access_summary`
      {time_filter}
      GROUP BY actor_email
    )
    SELECT
      b.actor_email,
      b.origin,
      p.persona,
      b.chat_turns,
      b.deep_research_calls,
      b.notebooklm_ops,
      b.a2a_invocations,
      b.programmatic_searches,
      b.session_files,
      IFNULL(nav.custom_agent_visits, 0) AS custom_agent_visits,
      IFNULL(nav.distinct_custom_agents, 0) AS distinct_custom_agents,
      b.engines_touched,
      b.total_data_access,
      b.last_access
    FROM base b
    LEFT JOIN `{PROJECT}.{DATASET}.v_user_persona` p ON b.actor_email = p.user
    LEFT JOIN `{PROJECT}.{DATASET}.v_agentspace_navigation_summary` nav ON b.actor_email = nav.actor_email
    ORDER BY b.total_data_access DESC
    """
    rows = [_json_safe(dict(r)) for r in _bq.query(sql).result()]
    return {"users": rows, "count": len(rows)}


@app.get("/api/user/{email}")
def user_deep_dive(email: str, live: bool = False) -> JSONResponse:
    """Aggregated single-user view across 9 sources, queried concurrently."""
    import concurrent.futures
    tbl = lambda v: f"{PROJECT}.{DATASET}." + (v if live else snapshot_name(v))
    queries = {
        "persona":             f"SELECT * FROM `{tbl('v_user_persona')}` WHERE user = @email LIMIT 1",
        "data_access_summary": f"SELECT * FROM `{tbl('v_data_access_summary')}` WHERE actor_email = @email ORDER BY total_data_access DESC",
        "agentspace_summary":  f"SELECT * FROM `{tbl('v_agentspace_navigation_summary')}` WHERE actor_email = @email LIMIT 1",
        "agentspace_detail":   f"SELECT * FROM `{tbl('v_agentspace_navigation')}` WHERE actor_email = @email ORDER BY visits DESC LIMIT 50",
        "conversations":       f"SELECT timestamp, prompt, response_text, engine_display_name, join_status FROM `{tbl('v_conversations_with_response')}` WHERE actor_email = @email ORDER BY timestamp DESC LIMIT 50",
        "builder":             f"SELECT * FROM `{tbl('v_builders')}` WHERE actor_email = @email LIMIT 1",
        "admin_events":        f"SELECT timestamp, action, service, resource_type, resource_id FROM `{tbl('v_admin_activity')}` WHERE actor_email = @email ORDER BY timestamp DESC LIMIT 50",
        # data_access_events excludes autocomplete noise (AdvancedCompleteQuery is fired on every keystroke)
        "data_access_events":  f"SELECT timestamp, action, service, engine_id_raw, datastore_id, full_method FROM `{tbl('v_data_access')}` WHERE actor_email = @email AND full_method NOT LIKE '%CompletionService.%' ORDER BY timestamp DESC LIMIT 200",
        # Per-feature event arrays for drill-down (always non-empty when the corresponding metric > 0)
        "dr_events":           f"SELECT timestamp, action, full_method FROM `{tbl('v_data_access')}` WHERE actor_email = @email AND (full_method LIKE '%AsyncAssist%' OR full_method LIKE '%ReadAsyncAssist%') ORDER BY timestamp DESC LIMIT 100",
        "notebooklm_events":   f"SELECT timestamp, action, full_method FROM `{tbl('v_data_access')}` WHERE actor_email = @email AND full_method LIKE '%notebooklm.%' ORDER BY timestamp DESC LIMIT 100",
        "a2a_events":          f"SELECT timestamp, action, full_method FROM `{tbl('v_data_access')}` WHERE actor_email = @email AND full_method LIKE '%assistants.agents.a2a.v1.%' ORDER BY timestamp DESC LIMIT 100",
        "chat_events":         f"SELECT timestamp, action, full_method FROM `{tbl('v_data_access')}` WHERE actor_email = @email AND (full_method LIKE '%AssistantService.StreamAssist' OR full_method LIKE '%AssistantService.Assist') ORDER BY timestamp DESC LIMIT 100",
        "session_files":       f"SELECT * FROM `{tbl('v_session_files')}` WHERE actor_email = @email ORDER BY last_op DESC LIMIT 30",
        # Raw per-visit navigation events (un-aggregated, for drill-down)
        # Always live: navigation lives in user_activity table, no snapshot for the raw stream
        "agentspace_events":   f"""SELECT
              timestamp,
              jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype AS page_type,
              jsonPayload.request.userevent.agentspaceinfo.agentinfo.agentid  AS agent_id,
              jsonPayload.request.userevent.agentspaceinfo.agentinfo.name     AS agent_name
            FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
            WHERE REGEXP_REPLACE(jsonPayload.useriamprincipal, r'^vivo-sim-', 'demo-') = @email
              AND jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 200""",
        # Deep Research prompt reverse-attribution (±60s heuristic)
        "dr_prompts":          f"""SELECT dr_ts, dr_action, attributed_prompt, prompt_ts, attribution_delta_sec, engine_display_name
            FROM `{PROJECT}.{DATASET}.v_deep_research_prompts`
            WHERE actor_email = @email
            ORDER BY dr_ts DESC LIMIT 100""",
        # Custom-agent prompt attribution (5min-after-open heuristic)
        "custom_agent_prompts": f"""SELECT prompt_ts, agent_id, agent_name, agent_open_ts, elapsed_since_open_sec, prompt, engine_display_name
            FROM `{PROJECT}.{DATASET}.v_custom_agent_prompts`
            WHERE actor_email = @email
            ORDER BY prompt_ts DESC LIMIT 100""",
    }

    def run_one(key_sql):
        key, sql = key_sql
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", email)]
        )
        try:
            return key, [_json_safe(dict(r)) for r in _bq.query(sql, job_config=job_config).result()]
        except Exception as e:
            log.warning(f"user_deep_dive: {key} failed: {e}")
            return key, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries)) as pool:
        results = dict(pool.map(run_one, queries.items()))

    payload = {"actor_email": email, "source": "live_view" if live else "snapshot", **results}
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


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
    # Allow any key that starts with 'tier.' / 'quota.' / legacy purchased_seats / claimed_window_days
    if not (key.startswith("tier.") or key.startswith("quota.")
            or key in {"purchased_seats", "claimed_window_days"}):
        raise HTTPException(400, "key must start with 'tier.' / 'quota.' or be a legacy key")
    _bq.query(
        f"MERGE `{PROJECT}.{DATASET}.quota_config` t "
        f"USING (SELECT '{key}' k, '{value}' v) s "
        f"ON t.key = s.k "
        f"WHEN MATCHED THEN UPDATE SET value=s.v, updated_at=CURRENT_TIMESTAMP(), updated_by='{by}' "
        f"WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by) "
        f"VALUES (s.k, s.v, CURRENT_TIMESTAMP(), '{by}')"
    ).result()
    return {"key": key, "value": value, "ok": True}


# ============================================================
# Quota dashboard endpoints
# ============================================================

@app.get("/api/quota/overview")
def quota_overview() -> JSONResponse:
    """Everything the /quota page needs in one round trip."""
    import concurrent.futures
    queries = {
        "totals":      f"SELECT * FROM `{PROJECT}.{DATASET}.v_quota_totals`",
        "utilization": f"SELECT * FROM `{PROJECT}.{DATASET}.v_quota_utilization` ORDER BY utilization DESC LIMIT 500",
        "tiers":       f"SELECT actor_email, tier, notes, assigned_at, assigned_by FROM `{PROJECT}.{DATASET}.user_tier` ORDER BY actor_email",
        "config":      f"SELECT key, value FROM `{PROJECT}.{DATASET}.quota_config` WHERE key LIKE 'tier.%' OR key LIKE 'quota.%' ORDER BY key",
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


@app.post("/api/quota/tier")
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


@app.get("/api/summary")
def summary(origin: str | None = None, engine_id: str | None = None, live: bool = False,
            since_hours: int | None = None) -> dict[str, Any]:
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

    # Time-range filters (per-view, since column varies)
    time_filter_da = ""     # v_data_access_summary uses last_access
    time_filter_conv = ""   # v_conversations uses timestamp
    time_filter_b = ""      # v_builders uses last_admin_action
    time_filter_p = ""      # v_user_persona uses last_seen
    if since_hours and since_hours > 0:
        sh = int(since_hours)
        time_filter_da   = f" AND last_access >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_conv = f" AND timestamp   >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_b    = f" AND last_admin_action >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_p    = f" AND last_seen   >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        # since_hours forces live view (snapshot has stale timestamps for the filter)
        live = True

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
        WHERE origin IN ('HUMAN', 'SIMULATED') {time_filter_p}
      ),
      a AS (SELECT SUM(total_admin_actions) c FROM `{PROJECT}.{DATASET}.{b}`
            WHERE TRUE {origin_filter} {time_filter_b}),
      d AS (SELECT SUM(chat_turns) chat,
                   SUM(total_data_access) total
            FROM `{PROJECT}.{DATASET}.{da}`
            WHERE TRUE {origin_filter} {engine_filter_summary} {time_filter_da}),
      e AS (SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{ea}`),
      adm AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_activity`),
      dac AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_data_access`),
      ua  AS (SELECT MAX(timestamp) ts FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`),
      conv AS (SELECT COUNT(*) c FROM `{PROJECT}.{DATASET}.{cv}`
               WHERE TRUE {origin_filter} {engine_filter_conv} {time_filter_conv})
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
