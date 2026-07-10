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

"""Pure SQL builders for the observability read-side endpoints.

Extracted from routes/observability.py `_rows()` and `summary()`
(2026-07-06, Phase 3 of the TDDD split). No BigQuery client, no
logging, no framework imports — all inputs come in as primitives,
all outputs are strings / dataclasses. Callers wrap the returned SQL
with `_bq.query(...)`.

Rules:
  * Bad input → ValueError. Route layer maps to HTTPException(400/404).
  * PROJECT + DATASET are passed in per call (no globals).
  * snapshot vs. live source is a caller decision, but `build_query_spec`
    forces `live=True` when `since_hours` is set (the snapshot's stale
    row-level timestamps make a time filter meaningless there).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from pydantic import BaseModel

from apps.api.contexts.observability.domain.view_registry import (
    VIEWS,
    VIEWS_WITH_ORIGIN,
    VIEWS_WITH_ENGINE,
    VIEW_TIME_COL,
    snapshot_name,
)


# Duplicated (deliberately) from shared/common — keeps this module free
# of any imports back into the app layer. Single source is the set below.
_VALID_ORIGINS = {"HUMAN", "AUTOMATION", "UNKNOWN", "SIMULATED"}

# Views whose engine column is named `engine_id` (not the default
# `engine_id_raw`). Aliased at view-creation time — see views.sql.tmpl.
_ENGINE_ID_COLS = {"v_data_access_summary", "v_user_usage", "v_engine_adoption"}


@dataclass(frozen=True)
class QuerySpec:
    """Parsed & validated request → all the pieces needed to build SQL.

    Immutable so callers can safely `replace(spec, live=True)` to build
    a fallback query without mutating the original.
    """
    project: str
    dataset: str
    view: str
    limit: int
    origin: Optional[str]
    engine_id: Optional[str]
    live: bool  # True if request asked for live OR since_hours forced it
    where_clauses: tuple[str, ...]


def build_query_spec(
    project: str,
    dataset: str,
    view: str,
    limit: int = 1000,
    origin: Optional[str] = None,
    engine_id: Optional[str] = None,
    live: bool = False,
    since_hours: Optional[int] = None,
) -> QuerySpec:
    """Validate request params and assemble WHERE clauses.

    Raises ValueError with a caller-friendly message when input is bad.
    The route layer turns those into HTTPException(400/404) — we don't
    know here whether the caller is HTTP, a CLI, or a test.
    """
    if view not in VIEWS:
        # NB: kept the "Unknown view" wording so route callers can pass
        # str(e) straight through as the HTTPException detail.
        raise ValueError(f"Unknown view: {view}")

    where_clauses: list[str] = []

    if origin:
        if origin not in _VALID_ORIGINS:
            raise ValueError(f"origin must be one of {_VALID_ORIGINS}")
        if view not in VIEWS_WITH_ORIGIN:
            raise ValueError(f"view {view} doesn't have an origin column")
        where_clauses.append(f"origin = '{origin}'")

    if engine_id:
        if view not in VIEWS_WITH_ENGINE:
            raise ValueError(f"view {view} doesn't have an engine_id column")
        col = "engine_id" if view in _ENGINE_ID_COLS else "engine_id_raw"
        # Reject anything that isn't alphanumeric + `-` + `_` — the raw
        # value is interpolated into SQL so we can't rely on parameter binding.
        if not engine_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid engine_id")
        where_clauses.append(f"{col} = '{engine_id}'")

    if since_hours and since_hours > 0:
        tcol = VIEW_TIME_COL.get(view)
        if tcol:
            if tcol == "d":  # DATE column, not TIMESTAMP
                where_clauses.append(
                    f"{tcol} >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(since_hours // 24)} DAY)"
                )
            else:
                where_clauses.append(
                    f"{tcol} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(since_hours)} HOUR)"
                )
        # Snapshot rows carry stale timestamps — a time filter against
        # the snapshot would be meaningless. Force live.
        live = True

    return QuerySpec(
        project=project,
        dataset=dataset,
        view=view,
        limit=int(limit),
        origin=origin,
        engine_id=engine_id,
        live=live,
        where_clauses=tuple(where_clauses),
    )


def render_sql(spec: QuerySpec) -> str:
    """Render the SELECT for a QuerySpec.

    Kept trivial on purpose — all the interesting decisions are in
    build_query_spec(). Callers use `replace(spec, live=True)` +
    another render_sql() call to build the snapshot-miss fallback.
    """
    src = spec.view if spec.live else snapshot_name(spec.view)
    where = (" WHERE " + " AND ".join(spec.where_clauses)) if spec.where_clauses else ""
    return f"SELECT * FROM `{spec.project}.{spec.dataset}.{src}`{where} LIMIT {spec.limit}"


def render_live_fallback_sql(spec: QuerySpec) -> str:
    """Shortcut for the NotFound-on-snapshot recovery path. See INV-obs-001."""
    return render_sql(replace(spec, live=True))


# ============================================================
# /api/summary — KPI card. Pure builder for the big CTE query.
# ============================================================

@dataclass(frozen=True)
class SummaryFilters:
    """Rendered fragments that feed the summary CTE.

    Each `_filter` field is either an empty string or a `" AND <predicate>"`
    fragment ready to concatenate inside a WHERE. This is a rendering
    detail — kept out of routes/observability.py so the SQL text lives
    in one place.
    """
    origin_filter: str
    engine_filter_summary: str        # for v_data_access_summary (engine_id col)
    engine_filter_conv: str           # for v_conversations (engine_id_raw col)
    time_filter_da: str               # v_data_access_summary (last_access)
    time_filter_conv: str             # v_conversations (timestamp)
    time_filter_b: str                # v_builders (last_admin_action)
    time_filter_p: str                # v_user_persona (last_seen)
    live: bool                        # since_hours forces this True


def build_summary_filters(
    origin: Optional[str] = None,
    engine_id: Optional[str] = None,
    live: bool = False,
    since_hours: Optional[int] = None,
) -> SummaryFilters:
    """Assemble the WHERE fragments used by render_summary_sql.

    Unlike `build_query_spec`, invalid `origin` / `engine_id` here are
    silently dropped rather than raised — that matches the pre-Phase-3
    behavior of `summary()` (which only applied the filter when the
    value was recognized as valid, letting anything else through as
    "no filter").
    """
    origin_filter = ""
    if origin in _VALID_ORIGINS:
        origin_filter = f" AND origin = '{origin}'"

    engine_filter_summary = ""
    engine_filter_conv = ""
    if engine_id and engine_id.replace("-", "").replace("_", "").isalnum():
        engine_filter_summary = f" AND engine_id = '{engine_id}'"
        engine_filter_conv = f" AND engine_id_raw = '{engine_id}'"

    time_filter_da = ""
    time_filter_conv = ""
    time_filter_b = ""
    time_filter_p = ""
    if since_hours and since_hours > 0:
        sh = int(since_hours)
        time_filter_da   = f" AND last_access >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_conv = f" AND timestamp   >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_b    = f" AND last_admin_action >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        time_filter_p    = f" AND last_seen   >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {sh} HOUR)"
        # since_hours forces live view (snapshot has stale timestamps for the filter)
        live = True

    return SummaryFilters(
        origin_filter=origin_filter,
        engine_filter_summary=engine_filter_summary,
        engine_filter_conv=engine_filter_conv,
        time_filter_da=time_filter_da,
        time_filter_conv=time_filter_conv,
        time_filter_b=time_filter_b,
        time_filter_p=time_filter_p,
        live=live,
    )


def render_summary_sql(project: str, dataset: str, f: SummaryFilters) -> str:
    """Render the /api/summary KPI CTE.

    Snapshot vs. live is a single decision applied to every source table;
    the caller (routes/observability.py::summary) is responsible for
    catching NotFound + re-running with `live=True` — that lives in the
    app layer because it involves recursion into the FastAPI endpoint.
    """
    p  = "v_user_persona"          if f.live else "s_user_persona"
    b  = "v_builders"              if f.live else "s_builders"
    da = "v_data_access_summary"   if f.live else "s_data_access_summary"
    ea = "v_engine_adoption"       if f.live else "s_engine_adoption"
    cv = "v_conversations"         if f.live else "s_conversations"

    return f"""
    WITH
      humans AS (
        SELECT persona, chat_turns_total, chat_turns_7d
        FROM `{project}.{dataset}.{p}`
        WHERE origin IN ('HUMAN', 'SIMULATED') {f.time_filter_p}
      ),
      a AS (SELECT SUM(total_admin_actions) c FROM `{project}.{dataset}.{b}`
            WHERE TRUE {f.origin_filter} {f.time_filter_b}),
      d AS (SELECT SUM(chat_turns) chat,
                   SUM(total_data_access) total
            FROM `{project}.{dataset}.{da}`
            WHERE TRUE {f.origin_filter} {f.engine_filter_summary} {f.time_filter_da}),
      e AS (SELECT COUNT(*) c FROM `{project}.{dataset}.{ea}`),
      adm AS (SELECT MAX(timestamp) ts FROM `{project}.{dataset}.cloudaudit_googleapis_com_activity`),
      dac AS (SELECT MAX(timestamp) ts FROM `{project}.{dataset}.cloudaudit_googleapis_com_data_access`),
      ua  AS (SELECT MAX(timestamp) ts FROM `{project}.{dataset}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`),
      conv AS (SELECT COUNT(*) c FROM `{project}.{dataset}.{cv}`
               WHERE TRUE {f.origin_filter} {f.engine_filter_conv} {f.time_filter_conv})
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


class SummaryResponse(BaseModel):
    """Shape returned by /api/summary. Mirrors the 16 columns projected
    by render_summary_sql. Nullable ints default to 0 when the snapshot
    is empty (fresh deploy); timestamps default to None so the frontend
    can render '—' rather than an epoch date.

    Grouped by intent for readability — the SELECT list in
    render_summary_sql uses the same order so drift is obvious.
    """
    model_config = {"extra": "forbid"}
    # adoption + quality
    human_users:            int = 0
    power_users:            int = 0
    active_consumers:       int = 0
    trial_users:            int = 0
    human_builders:         int = 0
    explorers:              int = 0
    lurkers:                int = 0
    human_chat_turns_7d:    int = 0
    conversations_captured: int = 0
    # governance + audit
    admin_actions:          int = 0
    chat_turns_total:       int = 0
    data_access_calls:      int = 0
    engines_tracked:        int = 0
    # data freshness — ISO-8601 timestamps or None
    last_admin_event:         Optional[str] = None
    last_data_access_event:   Optional[str] = None
    last_user_activity_event: Optional[str] = None
