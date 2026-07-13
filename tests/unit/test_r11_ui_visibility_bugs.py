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

"""RED for R11 (2026-07-13) — three UI visibility complaints from
user review of vivo:

  R11a · Same user appears twice in Data Access (one row per engine
         context). v_data_access_summary GROUPs BY (actor, engine_id,
         engine_display_name). User with both engine calls AND admin-
         level DevTools calls gets split. Fix client-side: aggregate
         to one row per actor with an "engines" column.

  R11b · Time range button doesn't visibly change anything. Actually
         works (API responds to since_hours) but no persistent chip
         shows the current range. Add a chip in the Header near
         RangeToggle showing "当前: 7d" etc.

  R11c · Conversations empty on vivo. Not a code bug — vivo tenant's
         gen_ai / user_activity logs don't populate prompt fields
         (request.query = null on all 19 StreamAssist calls; the
         actual prompt content lives in gen_ai_user_message with no
         user identity link). Update the EmptyState hint to explain
         THIS specific vivo case, not just "P&R logging off".
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


def test_data_access_dedups_by_actor() -> None:
    """DataAccess.tsx should aggregate summary rows by actor_email
    client-side (or via a new backend endpoint) so a single user with
    activity in multiple engine contexts shows as ONE row."""
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    # Require a NAMED aggregation — the dedup work must be explicit and
    # obviously about per-actor collapsing. Reject accidental matches
    # (like the daily aggregator that uses reduce for a different purpose).
    has_named_agg = (
        "byActor" in src
        or "aggregateByActor" in src
        or "dedupByActor" in src
        or "collapseByActor" in src
        or "groupByActor" in src
        or "summaryByActor" in src
    )
    assert has_named_agg, (
        "DataAccess.tsx doesn't aggregate summary rows by actor_email. "
        "User 11136993 currently shows twice on vivo (one row for their "
        "engine calls, one for admin-level DevToolsConfigService calls). "
        "Add a client-side per-actor collapse — sum the counts, join "
        "the engine names, use one of the named forms: byActor / "
        "aggregateByActor / summaryByActor / etc."
    )


def test_header_shows_current_range_chip() -> None:
    """Header.tsx should display the currently selected range as a
    visible chip alongside RangeToggle, so users see feedback after
    clicking. Currently only the internal RangeToggle knows the state."""
    src = (REPO / "apps/web/src/components/Header.tsx").read_text()
    # Look for an always-visible label of the current range that isn't
    # just the button's own highlighted state.
    has_visible_label = (
        re.search(r"(当前|now|active|current).*range", src, re.IGNORECASE)
        or re.search(r"range\s*[:：]", src)
        or re.search(r"最近\s*\{", src)
    )
    assert has_visible_label, (
        "Header.tsx doesn't render the active range as a persistent "
        "label (only the RangeToggle button highlights). Add a chip "
        "like `📅 最近 {range}` visible in the header so users see "
        "immediate feedback after clicking."
    )


def test_conversations_empty_hint_explains_vivo_schema() -> None:
    """The Conversations.tsx empty-state hint should mention the two
    concrete vivo causes: (a) StreamAssist request.query is null so
    prompts aren't captured on the audit side; (b) actual prompt
    content is in a separate table (gen_ai_user_message) without user
    linkage. Not just generic "P&R logging off"."""
    src = (REPO / "apps/web/src/pages/Conversations.tsx").read_text()
    mentions_schema = (
        "gen_ai_user_message" in src
        or "request.query" in src
        or "OIDC" in src
        or "WIF" in src
        or "身份" in src   # explains identity issue
        or "prompt 内容" in src
        or "查不到" in src
    )
    assert mentions_schema, (
        "Conversations.tsx empty-state hint doesn't mention the actual "
        "vivo failure mode (request.query = null on the audit side; "
        "prompt text lives in gen_ai_user_message without user linkage). "
        "Add a specific explanation so the reporter isn't left guessing "
        "'why is this empty when there's clearly traffic on the tenant'."
    )
