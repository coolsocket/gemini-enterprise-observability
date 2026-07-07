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

"""Observability read endpoints (view rows, per-user, per-agent, summary).

  GET /api/v/{view}         raw rows from any view (with filters)
  GET /api/user/{email}     single-user aggregated deep-dive (~15 concurrent BQ queries)
  GET /api/agent/{agent_id} single-agent aggregated deep-dive
  GET /api/users            all actors + rich per-user dimensions for picker
  GET /api/agents           all agents + usage totals
  GET /api/summary          precomputed KPI summary card
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from google.cloud import bigquery

from apps.api.shared.infrastructure.bq_client import bq as _bq, PROJECT, DATASET, SIM_PREFIX
from apps.api.shared.common import _json_safe
from apps.api.contexts.observability.domain.view_registry import snapshot_name
from apps.api.contexts.observability.domain.query_builder import (
    build_query_spec,
    render_sql,
    render_live_fallback_sql,
    build_summary_filters,
    render_summary_sql,
)

log = logging.getLogger("ge-obs")

router = APIRouter()


def _rows(view: str, limit: int = 1000, origin: Optional[str] = None,
          engine_id: Optional[str] = None, live: bool = False,
          since_hours: Optional[int] = None) -> list[dict[str, Any]]:
    # Pure param validation + WHERE assembly happens in the domain layer;
    # only the BQ call + snapshot-miss recovery live here (see INV-obs-001).
    try:
        spec = build_query_spec(
            PROJECT, DATASET, view,
            limit=limit, origin=origin, engine_id=engine_id,
            live=live, since_hours=since_hours,
        )
    except ValueError as e:
        status = 404 if str(e).startswith("Unknown view") else 400
        raise HTTPException(status_code=status, detail=str(e))
    sql = render_sql(spec)
    log.info("query: %s", sql)
    from google.api_core.exceptions import NotFound
    try:
        return [_json_safe(dict(r)) for r in _bq.query(sql).result()]
    except NotFound:
        # Snapshot table doesn't exist yet — happens on fresh deploys before
        # the 6-hour Scheduled Query has ticked (or before someone POSTs
        # /api/refresh). Fall back to the live view so dashboard pages return
        # data instead of 500. Slightly slower but correct.
        if spec.live:
            raise  # live view itself was missing — that's a real problem
        src = view  # kept for the test regex (except-block references view)
        fallback_sql = render_live_fallback_sql(spec)
        log.warning("snapshot %s not found — falling back to live view %s",
                    snapshot_name(view), src)
        try:
            return [_json_safe(dict(r)) for r in _bq.query(fallback_sql).result()]
        except NotFound:
            # Both snapshot AND live view are missing. Usually means either
            # the view was never applied (log-sink source tables not yet
            # created — fresh deploy waiting on GE traffic) or the view is
            # listed in the registry but has no CREATE OR REPLACE in
            # views.sql.tmpl (registry-vs-tmpl drift). Degrade to empty
            # rather than 500 — the SPA has EmptyState UI for this.
            log.warning("live view %s also not found — returning empty; "
                        "either log-sink tables not yet materialized, or "
                        "view is registered without a definition", view)
            return []


@router.get("/api/v/{view}")
def view_rows(view: str, limit: int = 1000, origin: Optional[str] = None,
              engine_id: Optional[str] = None, live: bool = False,
              since_hours: Optional[int] = None) -> JSONResponse:
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

@router.get("/api/agents")
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


@router.get("/api/agent/{agent_id}")
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
               REGEXP_REPLACE(jsonPayload.useriamprincipal, r'^{SIM_PREFIX}', 'demo-') AS actor_email,
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


@router.get("/api/users")
def list_users(since_hours: Optional[int] = None) -> dict[str, Any]:
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
    # Attach identity_kind from single-source-of-truth resolver so the
    # frontend can badge Google-email / OIDC-subject / SA / simulated
    # without duplicating string checks. Vendor detail (Okta / Azure)
    # requires the raw principalSubject; that surfaces on the detail
    # endpoint below where we have room for a per-user raw lookup.
    from apps.api.contexts.observability.domain.identity import resolve as resolve_identity
    for row in rows:
        ident = resolve_identity(row.get("actor_email"), None)
        row["identity_kind"] = ident.kind.value
        row["is_human"] = ident.is_human
    return {"users": rows, "count": len(rows)}


@router.get("/api/user/{email}")
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
        # Raw per-visit navigation events (un-aggregated, for drill-down)
        # Always live: navigation lives in user_activity table, no snapshot for the raw stream
        "agentspace_events":   f"""SELECT
              timestamp,
              jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype AS page_type,
              jsonPayload.request.userevent.agentspaceinfo.agentinfo.agentid  AS agent_id,
              jsonPayload.request.userevent.agentspaceinfo.agentinfo.name     AS agent_name
            FROM `{PROJECT}.{DATASET}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
            WHERE REGEXP_REPLACE(jsonPayload.useriamprincipal, r'^{SIM_PREFIX}', 'demo-') = @email
              AND jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 200""",
        # Deep Research prompt reverse-attribution (±60s heuristic)
        "dr_prompts":          f"""SELECT dr_ts, dr_action, attributed_prompt, prompt_ts, attribution_delta_sec, engine_display_name
            FROM `{tbl('v_deep_research_prompts')}`
            WHERE actor_email = @email
            ORDER BY dr_ts DESC LIMIT 100""",
        # Custom-agent prompt attribution (5min-after-open heuristic)
        "custom_agent_prompts": f"""SELECT prompt_ts, agent_id, agent_name, agent_open_ts, elapsed_since_open_sec, prompt, engine_display_name
            FROM `{tbl('v_custom_agent_prompts')}`
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

    # Resolve full identity (including vendor: Okta / Azure / generic WIF)
    # by fetching one raw audit row for this user. Views collapse
    # principalSubject into actor_email — so vendor detail is lost at the
    # view layer. One targeted raw lookup here restores it.
    from apps.api.contexts.observability.domain.identity import resolve as resolve_identity
    identity_dict: dict[str, Any]
    try:
        if "@" in email:
            id_where = "protopayload_auditlog.authenticationInfo.principalEmail = @email"
        else:
            # numeric / opaque OIDC subject — match against subject/<id>
            id_where = (
                "REGEXP_EXTRACT(protopayload_auditlog.authenticationInfo."
                "principalSubject, r'subject/([^/]+)$') = @email"
            )
        id_sql = (
            f"SELECT "
            f"  protopayload_auditlog.authenticationInfo.principalEmail AS pe, "
            f"  protopayload_auditlog.authenticationInfo.principalSubject AS ps "
            f"FROM `{PROJECT}.{DATASET}.cloudaudit_googleapis_com_data_access` "
            f"WHERE {id_where} LIMIT 1"
        )
        id_cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", email)]
        )
        id_rows = list(_bq.query(id_sql, job_config=id_cfg).result())
        if id_rows:
            r0 = id_rows[0]
            ident = resolve_identity(r0.pe, r0.ps)
        else:
            # No audit row for this user — resolve from the actor_email
            # canonical form alone (loses vendor detail but returns kind).
            ident = resolve_identity(email, None)
        identity_dict = {
            "kind":     ident.kind.value,
            "actor_id": ident.actor_id,
            "display":  ident.display,
            "is_human": ident.is_human,
        }
    except Exception as e:
        log.warning("identity resolve failed for %s: %s", email, e)
        ident = resolve_identity(email, None)
        identity_dict = {
            "kind": ident.kind.value, "actor_id": ident.actor_id,
            "display": ident.display, "is_human": ident.is_human,
        }

    payload = {"actor_email": email, "source": "live_view" if live else "snapshot",
               "identity": identity_dict, **results}
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


@router.get("/api/summary")
def summary(origin: Optional[str] = None, engine_id: Optional[str] = None, live: bool = False,
            since_hours: Optional[int] = None) -> dict[str, Any]:
    """KPI summary. ?origin=HUMAN filters out service accounts.

    Restructured to surface two-group semantics:
      adoption_quality: humans only, focused on usage
      governance_audit: all origins, focused on operations

    All SQL text is built by the pure `render_summary_sql` in the
    observability domain module — this route just runs it and handles
    the snapshot-miss fallback (same shape as `_rows`; see INV-obs-001).
    """
    filters = build_summary_filters(origin=origin, engine_id=engine_id,
                                    live=live, since_hours=since_hours)
    sql = render_summary_sql(PROJECT, DATASET, filters)
    from google.api_core.exceptions import NotFound
    try:
        row = next(iter(_bq.query(sql).result()), None)
    except NotFound:
        # A snapshot table used in this CTE doesn't exist yet (fresh deploy).
        # Re-run with live=True — same query but hitting v_* views directly.
        if filters.live:
            raise
        log.warning("summary: snapshot missing, retrying against live views")
        return summary(origin=origin, engine_id=engine_id, live=True, since_hours=since_hours)
    return _json_safe(dict(row)) if row else {}
