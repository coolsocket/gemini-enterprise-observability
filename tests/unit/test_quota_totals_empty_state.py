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

"""RED for the "empty totals panel" bug (2026-07-10).

Symptom (user report): on vivo (18003) the Quota page's "今日全平台使用
vs 总配额" panel body is blank. Reason: the tenant's `quota_config`
table has no `tier.*_daily` keys. v_quota_totals's tier_limits CTE
turns up empty, per_feature_capacity join produces zero rows, and the
grid renders no cards.

Bug: the panel silently shows nothing instead of explaining why.
Operators reading the dashboard have no way to tell "0 rows because
truly nothing configured" from "0 rows because a bug ate the query".

Fix: when totals[] is empty (irrespective of window), render an
EmptyState under the grid with a hint pointing at the tier config
table further down the page. Both windowDays=1 and windowDays=7/30
should hit the same fallback.
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


def test_quota_page_renders_empty_state_when_totals_empty() -> None:
    src = (REPO / "apps/web/src/pages/Quota.tsx").read_text()
    # Locate the totals Panel body — from "Per-feature totals grid" comment
    # through the closing tag.
    m = re.search(
        r"\{/\*\s*Per-feature totals grid\s*\*/\}[\s\S]*?</Panel>",
        src,
    )
    assert m, "totals Panel block not found in Quota.tsx"
    body = m.group(0)

    # Must guard on d.totals.length === 0 (or equivalent) and show
    # an EmptyState so the panel body is never silently blank.
    references_empty = (
        re.search(r"totals\.length\s*===\s*0", body) is not None
        or re.search(r"totals\.length\s*<\s*1", body) is not None
        or re.search(r"!\s*d\.totals\.length", body) is not None
    )
    assert references_empty, (
        "Quota page totals Panel doesn't branch on `d.totals.length === 0`. "
        "When the tenant has no tier.*_daily keys in quota_config the panel "
        "renders empty; add an EmptyState + hint pointing at the tier "
        "config table below."
    )
    assert "EmptyState" in body, (
        "The empty-totals branch should use <EmptyState /> (imported "
        "from ../components/Card) so the visual matches other empty "
        "panels on the site."
    )
    # A hint mentioning tier/config so the user knows what to do
    assert re.search(r"tier|配置|quota_config", body, re.IGNORECASE), (
        "EmptyState hint should reference the tier config table so the "
        "operator knows how to unblock this — e.g. \"下方 Tier 阈值配置\"."
    )
