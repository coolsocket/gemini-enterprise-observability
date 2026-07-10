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

"""RED for Batch B (2026-07-10) — 3 UX items from reporter's list:

  B1 · Deep Dive header emojis are opaque
     💬🔬📓🧩🔎📎 — no tooltip; users don't know what each metric is.
     Fix: add `title=` attribute so hover shows the label.

  B2 · Historical-data visibility ("怎么确认历史数据有没有拉到")
     No frontend indicator of the data window. Settings shows
     `last_refresh` but not "data covers 30 days" — operators can't
     tell if `make backfill` was run.
     Fix: /api/refresh/status returns data_earliest + data_latest;
     Settings page displays "data window: X days (2026-06-25 → 2026-07-10)".

  B3 · Range button has no visible effect
     Range button DOES work at the API layer (verified live: v_dau 24h=1,
     7d=3, 30d=8 rows). But nowhere on the page prominently shows the
     current range, so users don't realise their click changed anything.
     Fix: add a "range: last Xd" chip somewhere always-visible (Header),
     tied to useRange().
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_b1_deep_dive_emoji_have_tooltips() -> None:
    """Every FeaturePill/Metric with `icon="🔬"` etc MUST have a `title=`
    attribute for hover discoverability."""
    src = (REPO / "apps/web/src/pages/UserDeepDive.tsx").read_text()
    # Regex-parsing TSX with nested braces + template literals is fragile.
    # Cheap sufficient check: FeaturePill signature accepts a `label` prop,
    # AND at least one usage site passes `label=`.
    sig_has_label = re.search(r"function\s+FeaturePill\([^)]*label", src) is not None
    label_call_count = len(re.findall(r"<FeaturePill[^>]*\blabel=", src))
    calls_pass_label = label_call_count >= 3
    assert sig_has_label and calls_pass_label, (
        f"FeaturePill either doesn't accept a `label` prop (sig_has_label={sig_has_label}) "
        f"or usage sites don't pass one (label= count={label_call_count}, need ≥3). "
        "Add `label` prop that becomes a hover tooltip so operators can hover "
        "an emoji to see what it counts (💬=chat, 🔬=deep research, etc)."
    )


def test_b2_refresh_status_exposes_data_window() -> None:
    """/api/refresh/status must include `data_earliest` and `data_latest`
    fields so the frontend can show 'data covers X days' — operators
    then know at a glance whether backfill has run."""
    src = (REPO / "apps/api/routes/refresh.py").read_text()
    m = re.search(r"def refresh_status.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "refresh_status not found"
    body = m.group(0)
    assert '"data_earliest"' in body or "'data_earliest'" in body, (
        "refresh_status response missing `data_earliest` field. Query "
        "MIN(timestamp) across sink target tables + include in response "
        "so /settings page can show data window."
    )
    assert '"data_latest"' in body or "'data_latest'" in body, (
        "refresh_status response missing `data_latest`. Same reasoning."
    )


def test_b2_settings_page_shows_data_window() -> None:
    """Settings.tsx should render the data window (earliest → latest)
    prominently — otherwise operators can't tell backfill worked."""
    src = (REPO / "apps/web/src/pages/Settings.tsx").read_text()
    assert (
        "data_earliest" in src
        or "data_window" in src
        or "覆盖" in src  # 中文 label
        or "covers" in src.lower()
    ), (
        "Settings.tsx doesn't display data-window info from "
        "/api/refresh/status. Show 'data covers X days (Y → Z)' near "
        "the existing last_refresh line."
    )


def test_b3_header_or_body_shows_active_range() -> None:
    """When useRange() is non-null, some visible chip MUST display the
    current range (`last 7d`, `last 30d`) so users know the button did
    something. Currently the button state is hidden in the popup."""
    header = (REPO / "apps/web/src/components/Header.tsx").read_text()
    range_ctx = (REPO / "apps/web/src/timerange.tsx").read_text()
    # Either Header renders the active range OR a new component elsewhere.
    header_shows = (
        "useRange" in header and (
            "range" in header and ("last" in header.lower() or "近" in header)
        )
    )
    assert header_shows, (
        "Header (or some always-visible component) doesn't render the "
        "active range value. Users click the button and can't tell "
        "anything changed. Add a small chip like `📅 last 7d` next to "
        "the existing origin filter chip in Header.tsx."
    )
