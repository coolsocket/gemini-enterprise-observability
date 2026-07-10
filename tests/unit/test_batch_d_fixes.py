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

"""RED for Batch D (2026-07-10) — reporter's Data Access item #2:

  Reporter: "Data Access · daily + agent/image/video 明细"

  The page already has notebooklm + a2a + chat + deep_research columns
  in the actor×engine summary. What's missing:

  D1 · No day-by-day breakdown. The summary aggregates the whole range;
       there's no "on 2026-07-08 we did N chat + M deep_research" table.
       Fix: add a "每日 × feature" panel driven by v_daily_usage_per_user.

  D2 · No per-agent breakdown. NotebookLM ops are lumped together,
       custom agents blend into A2A. Add a "Per-agent 明细" panel driven
       by v_agent_directory.

  D3 · image_gen / video_gen: GE doesn't emit customer audit logs for
       these (see prior commit 2026-07-06). Instead of silently missing,
       surface a small inline banner explaining why.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_d1_data_access_has_daily_panel() -> None:
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    # Look for a query against v_daily_usage_per_user OR a new endpoint
    # /api/data-access/daily, and a rendered date column.
    has_daily_query = (
        "v_daily_usage_per_user" in src
        or "/api/data-access/daily" in src
        or "dataAccessDaily" in src
    )
    assert has_daily_query, (
        "DataAccess.tsx doesn't fetch daily-breakdown data. Add either a "
        "call to api.view('v_daily_usage_per_user') or a dedicated "
        "api.dataAccessDaily() helper, and render a 'day × feature' table."
    )
    # A section titled 每日 / daily / 日
    assert re.search(r"每日|Daily|按日", src), (
        "DataAccess.tsx renders daily data but there's no 'per-day' panel "
        "heading. Add a <Panel title='每日 × feature'> or similar."
    )


def test_d2_data_access_has_per_agent_panel() -> None:
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    has_agent_ref = (
        "v_agent_directory" in src
        or "AgentDirectory" in src
        or "agentDirectory" in src
        or "/api/agents" in src
    )
    assert has_agent_ref, (
        "DataAccess.tsx doesn't show per-agent breakdown. Add a query "
        "against v_agent_directory / /api/agents and render an "
        "'agent × invocations' table."
    )


def test_d3_data_access_documents_missing_image_video() -> None:
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    # A short blurb somewhere on the page explaining image_gen/video_gen.
    has_disclaimer = (
        ("image_gen" in src or "图像" in src or "image" in src.lower())
        and ("video" in src.lower() or "视频" in src)
        and ("audit log" in src.lower() or "不" in src or "not" in src.lower())
    )
    assert has_disclaimer, (
        "DataAccess.tsx should surface a small note that image_gen / "
        "video_gen aren't recoverable — GE runs those inside Google "
        "infra without customer audit logs. Silent omission means the "
        "operator thinks we forgot to render them."
    )
