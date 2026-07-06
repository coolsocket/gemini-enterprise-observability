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
Every route module imports the view catalogue + `_json_safe` from here
instead of reaching back into main.py. Keeping this module import-free
(other than stdlib + our bq_client) means it can be reused from tests
and future contexts without pulling FastAPI along for the ride.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import os
from typing import Any


# License refresh cadence for the seat-count auto-refresh loop (24h default).
# Set to 0 to disable the background loop entirely (still exposed via
# POST /api/refresh/seats).
LICENSE_REFRESH_INTERVAL_SEC = int(os.environ.get("LICENSE_REFRESH_INTERVAL_SEC", str(24 * 3600)))


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

# Views that have an `engine_id_raw` column — supports ?engine_id= filter
VIEWS_WITH_ENGINE: set[str] = {
    "v_conversations", "v_conversations_with_response",
    "v_admin_activity", "v_data_access", "v_data_access_summary",
    "v_user_usage", "v_engine_adoption", "v_session_files", "v_agent_usage",
    "v_agentspace_navigation",
}

# Per-view time column for since_hours filter (None = no time filter possible)
VIEW_TIME_COL: dict[str, "str | None"] = {
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


_VALID_ORIGINS = {"HUMAN", "AUTOMATION", "UNKNOWN", "SIMULATED"}


def snapshot_name(view: str) -> str:
    """Snapshot table name (s_*) corresponding to each view (v_*)."""
    return "s_" + view[2:] if view.startswith("v_") else view


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
