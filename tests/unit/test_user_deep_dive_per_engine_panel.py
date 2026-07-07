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

"""RED regression: UserDeepDive doesn't render per-engine breakdown.

User request (2026-07-07): "用户 deep dive 这里，也要能够按照不同的项目排序呀".

Backend `/api/user/{email}` already returns `data_access_summary` as
one row per engine (engine_id_raw, engine_display_name, chat_turns,
deep_research_calls, notebooklm_*, session_files, total_data_access,
last_access, …). Verified on responsive-lens-421108 mirror:

  actor 11126728:
    engine_id=(NULL)                       chat=0  dr=0  total=495
    engine_id=vivo-ge-plus-app_1781...     chat=18 dr=9  total=446

But UserDeepDive.tsx only .reduce()s these rows into totals — never
renders them as a sortable table. Multi-engine tenants can't see
per-project usage breakdown.

Fix: add a Panel that renders `data_access_summary` as a sortable
per-engine table.
"""
from pathlib import Path
import re

PAGE = Path(__file__).resolve().parents[2] / "apps/web/src/pages/UserDeepDive.tsx"


def test_user_deep_dive_renders_per_engine_table() -> None:
    """UserDeepDive.tsx MUST render `data_access_summary` as a per-engine
    breakdown panel — not just aggregate it. Accepts either fluent
    `.filter().sort().map(...)` shape or a pattern where the filtered
    rows are stored to a variable that is `.map`ped later."""
    src = PAGE.read_text()
    # 1. must reference data_access_summary somewhere for RENDERING
    #    (existence of a filter → map chain, possibly via intermediate).
    #    Accept: any `data_access_summary` followed within 2500 chars by a
    #    `.map(` — same function scope is generous but sufficient.
    has_render_path = False
    for m in re.finditer(r"data_access_summary\b", src):
        if re.search(r"\.map\s*\(", src[m.end(): m.end() + 2500]):
            has_render_path = True
            break
    assert has_render_path, (
        "UserDeepDive references data_access_summary but no `.map(` follows "
        "within the same function scope. It's being aggregated only, never "
        "rendered as per-engine rows.\nAdd a Panel that iterates the "
        "per-engine data — see EngineSortKey type in the same file for the "
        "sortable-columns pattern."
    )

    # 2. must have a Panel that titles the per-engine section — this is
    #    the load-bearing UX signal that multi-engine tenants can see
    #    the breakdown at all.
    assert re.search(r'Panel[^>]*title=[^>]*(?:项目|Engine|engine|按.*Engine)', src), (
        "No Panel found whose title indicates a per-engine breakdown. "
        "Even if map() exists, users won't recognize the section as "
        "engine-broken-down. Title the Panel with '按项目（Engine）' or "
        "similar."
    )


def test_per_engine_panel_is_sortable() -> None:
    """If the panel exists, users MUST be able to change the sort column.
    Look for a sort-state hook (useState) whose values include engine-
    breakdown sort keys (chat/dr/nb/total)."""
    src = PAGE.read_text()
    if not re.search(r"data_access_summary[^)]*\.map\(", src):
        import pytest
        pytest.skip("per-engine map not present yet (see other test)")
    # Look for sort state managing engine columns
    has_engine_sort = re.search(
        r"(useState|SortKey)[^;]*(engine|per_engine|byEngine|engineSort)",
        src, re.IGNORECASE,
    ) is not None
    assert has_engine_sort, (
        "The per-engine panel has no sortable-column state. Add "
        "`const [engineSort, setEngineSort] = useState<...>(...)` with "
        "options like 'total' / 'chat' / 'dr' / 'nb', and clickable "
        "column headers that setEngineSort(...)."
    )
