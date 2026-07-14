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

"""Pure builder · OIDC/WIF-shaped Cloud Logging entries.

Simulates a customer like vivo (OIDC/WIF tenant, numeric subject IDs,
gen_ai_user_message stripped of user identity). Emits entry dicts that
match the shape our sink filter routes to sink-target BQ tables, so
backfill.py can pick them up on next run and the frontend can render
them.

Pure module. I/O (POST to logging.googleapis.com/v2/entries:write) is
done by a sibling CLI (`seed_oidc_logs.py`) that imports this builder.

Design fidelity — matches actual vivo schema quirks discovered
2026-07-13:
  * user_activity: useriamprincipal is a NUMERIC STRING like "10000001"
    (WIF subject); StreamAssist calls have request.query = null
    (the prompt lives in gen_ai_user_message instead).
  * gen_ai.user.message: NO useriamprincipal field. content.role +
    content.parts[].text ARE populated with real prompt/response text.
  * cloudaudit.data_access: authenticationInfo.principalEmail is
    also the numeric string.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any


_PROMPT_SAMPLES = [
    "什么是 memory 的 auto-dream 和 auto-renew 机制",
    "生成一个季度总结报告的大纲",
    "帮我把这份 PDF 摘要成 5 条要点",
    "vivo 手机相机夜景模式的算法演进",
    "请用 markdown 表格对比 iPhone 和 vivo",
    "帮我写一段面试自我介绍",
    "如何提高团队 code review 效率",
    "解释 transformer 的 attention 机制",
]
_RESPONSE_SAMPLES = [
    "根据你的问题,以下是关键点:\n\n1. Auto-dream 是...",
    "季度总结报告建议包含以下模块:...",
    "文档摘要:\n\n• 要点 1...",
    "vivo 夜景模式经历了三代演进:...",
]
_METHOD_MIX = [
    ("StreamAssist", 0.35),  # 35% chat
    ("Search",       0.30),  # 30% search
    ("WriteUserEvent", 0.25),
    ("UploadSessionFile", 0.10),
]
_ENGINE_ID = "vivo-sim-oidc-app_2000000000000"
_ENGINE_LOCATION = "projects/725379044852/locations/global/collections/default_collection/engines/" + _ENGINE_ID


def _make_principal(index: int) -> str:
    """Numeric OIDC subject like vivo's '11113722'. Deterministic
    from index so the same seed produces the same principal set."""
    return str(10_000_000 + index)


def _pick(items: list, seed_key: str, index: int):
    """Deterministic pick from a list based on (seed, index) hash."""
    h = int(hashlib.md5(f"{seed_key}:{index}".encode()).hexdigest()[:8], 16)
    return items[h % len(items)]


def _iso(ts: dt.datetime) -> str:
    return ts.replace(tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def build_oidc_entries(
    principal_count: int = 50,
    days_span: int = 20,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Generate OIDC-shape log entries spread across `days_span` days.

    Args:
      principal_count: how many distinct numeric principals to simulate.
      days_span: how far back the earliest entry goes (uniform distribution).
      seed: deterministic seed so repeat calls produce identical entries.

    Returns:
      List of Cloud Logging entry dicts ready to POST to entries.write.
      Each entry has logName / severity / timestamp / resource /
      jsonPayload (or protoPayload for cloudaudit).
    """
    now = dt.datetime(2026, 7, 14, 0, 0, 0)  # deterministic reference — caller can shift
    entries: list[dict[str, Any]] = []

    for i in range(principal_count):
        principal = _make_principal(i)
        # Each principal produces ~5 activity + 3 gen_ai + 2 audit entries,
        # spread across the days_span window.
        for j in range(5):
            method = _pick([m for m, _ in _METHOD_MIX], f"method:{seed}", i * 5 + j)
            ts = now - dt.timedelta(
                days=(hash((seed, i, j)) % max(1, days_span)),
                hours=(hash((seed, i, j, "h")) % 24),
            )
            # StreamAssist entries on vivo have request.query = null
            # (prompt lives in gen_ai instead).
            payload_query: Any = None
            payload_response: Any = None
            if method == "StreamAssist":
                payload_response = _pick(_RESPONSE_SAMPLES, f"resp:{seed}", i * 5 + j)
            entries.append({
                "logName": "projects/my-website-417013/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity",
                "severity": "INFO",
                "timestamp": _iso(ts),
                # Cloud Logging entries.write only accepts a limited
                # resource.type set — `global` is safe. The BQ sink still
                # routes by logName, so the resource shape doesn't affect
                # downstream views.
                "resource": {"type": "global"},
                "jsonPayload": {
                    "useriamprincipal": principal,
                    "logmetadata": {
                        "timestamp": _iso(ts),
                        "methodname": method,
                        "name": _ENGINE_LOCATION + "/assistants/default_assistant",
                        "servicename": "google.cloud.discoveryengine.v1main.AssistantService",
                        "servicelabel": "GEMINI_ENTERPRISE",
                    },
                    "request": {
                        "name": _ENGINE_LOCATION,
                        "query": payload_query,  # null for vivo shape
                    },
                    "response": {
                        "assisttoken": f"tok-{principal}-{j}",
                    },
                    "servicetextreply": payload_response,
                },
            })

        # gen_ai_user_message · NO useriamprincipal · real prompt text
        for k in range(3):
            ts = now - dt.timedelta(
                days=(hash((seed, i, k, "g")) % max(1, days_span)),
            )
            role = "user" if k % 2 == 0 else "model"
            text = (_pick(_PROMPT_SAMPLES, f"p:{seed}", i * 3 + k) if role == "user"
                    else _pick(_RESPONSE_SAMPLES, f"r:{seed}", i * 3 + k))
            entries.append({
                "logName": "projects/my-website-417013/logs/discoveryengine.googleapis.com%2Fgen_ai.user.message",
                "severity": "INFO",
                "timestamp": _iso(ts),
                "resource": {"type": "global"},
                "trace": f"projects/my-website-417013/traces/trace-{principal}-{k}",
                # NB: NO useriamprincipal / no principal at all — mirrors vivo
                "jsonPayload": {
                    "content": {
                        "role": role,
                        "parts": [{"text": text}],
                    },
                },
                "labels": {"gen_ai_system": "gemini", "event_name": "user_message"},
            })

        # cloudaudit data_access entries CANNOT be written via
        # entries.write (Cloud Logging enforces "only Google Cloud
        # Platform services can write audit logs"). Real customers
        # get these auto-generated by GCP, which is exactly the
        # point being simulated. We fake the data-access side by
        # attributing user_activity entries per principal (above);
        # v_data_access_summary derives its numbers from the audit
        # table which stays empty in this sim — that's fine, R11c
        # already documents that some panels depend on server-side
        # audit logs we can't fake.
        pass

    return entries
