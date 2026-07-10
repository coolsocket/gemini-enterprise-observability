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

"""RED for Batch C (2026-07-10) — reporter's Quota item #3:

  C1 · notebooklm feature missing from Quota page.
       `v_daily_usage_per_user` emits a 'notebooklm' bucket, but the frontend
       hardcodes FEATURE_ORDER=['chat','deep_research','agent_create']
       so it never renders. Also no tier.*.notebooklm_daily default in
       bootstrap — the /api/quota/overview totals block skips it.

  C2 · Quota totals only show "today". Reporter wanted "今日 vs 总配额
       + 7d/30d 切换". Add ?window_days=N to /api/quota/overview and a
       segmented control to Quota.tsx.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_c1_quota_page_lists_notebooklm() -> None:
    src = (REPO / "apps/web/src/pages/Quota.tsx").read_text()
    order_line = re.search(r"FEATURE_ORDER\s*=\s*\[[^\]]*\]", src)
    assert order_line, "FEATURE_ORDER not found in Quota.tsx"
    assert '"notebooklm"' in order_line.group(0), (
        "Quota page's FEATURE_ORDER doesn't include 'notebooklm'. "
        "v_daily_usage_per_user counts notebooklm actions but the totals "
        "grid + tier config table skip that column."
    )
    assert 'notebooklm:' in src.lower() or '"notebooklm"' in src, (
        "FEATURE_META missing an entry for notebooklm — add {label,icon,color,hint}."
    )


def test_c1_bootstrap_seeds_notebooklm_tier_defaults() -> None:
    src = (REPO / "infra/contexts/deploy/application/bootstrap.py").read_text()
    assert "tier.standard.notebooklm_daily" in src, (
        "Bootstrap doesn't seed a tier.standard.notebooklm_daily default. "
        "Without it v_quota_utilization has no daily_limit for the feature "
        "and it's dropped from the JOIN."
    )
    assert "tier.plus.notebooklm_daily" in src, (
        "Bootstrap doesn't seed a tier.plus.notebooklm_daily default."
    )


def test_c2_quota_overview_accepts_window_param() -> None:
    src = (REPO / "apps/api/routes/quota.py").read_text()
    # Loosely: signature must accept a window_days param (or the equivalent).
    assert re.search(r"quota_overview\([^)]*window_days", src), (
        "GET /api/quota/overview must accept `window_days: int = 1` so the "
        "frontend can toggle 1d / 7d / 30d totals. Currently the endpoint "
        "is fixed at 'today' via v_quota_totals."
    )
    # And the response must include a totals_window field or similar so the
    # frontend knows which window it got.
    assert "window_days" in src, (
        "quota_overview response should echo `window_days` so the frontend "
        "can show 'showing last 7d' next to the totals."
    )


def test_c2_quota_page_has_window_selector() -> None:
    src = (REPO / "apps/web/src/pages/Quota.tsx").read_text()
    # Look for a segmented control with 1 / 7 / 30 day options.
    assert re.search(r"windowDays|window_days|setWindow", src), (
        "Quota.tsx doesn't expose a window selector (state var like "
        "`windowDays`). Add a 1d/7d/30d segmented control that re-queries "
        "with the selected window."
    )
    # State must accept 1/7/30 (segmented control values) — accept either
    # a literal `[1, 7, 30]` array or explicit "7d"/"30d" labels.
    has_state_values = re.search(r"\[\s*1\s*,\s*7\s*,\s*30\s*\]", src) is not None
    has_literals = re.search(r"\b7\s*(d|days|天)\b", src) is not None and \
                   re.search(r"\b30\s*(d|days|天)\b", src) is not None
    assert has_state_values or has_literals, (
        "Quota.tsx window selector needs to enumerate 1/7/30 either as an "
        "array `[1, 7, 30]` (mapped into buttons) or with literal 7d/30d "
        "labels somewhere in the file."
    )
