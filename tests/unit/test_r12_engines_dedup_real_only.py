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

"""RED for R12 (2026-07-13) — Data Access "engines" column should count
REAL engines only, not the pseudo "(admin API)" bucket.

User pushback after R11: '这里怎么变成两个engines了啊, 比如11113722.
他们应该只有一个app才对'. Confirmed: 11113722 has one real engine
(vivo-GE-plus-app, 5253 ops) + 67 admin calls without an engine tag.
R11's summaryByActor was adding "(admin API)" into the engines Set,
inflating the display count.

Fix: the `engines` Set should hold ONLY non-null engine_display_name
values. The column renderer picks:
  * 0 real engines  → "(admin API)"    (all activity was admin-level)
  * 1 real engine   → that engine name  (any co-existing admin calls
                                          are just this user's ops)
  * N real engines  → "N engines"       (with tooltip)
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


def test_summary_by_actor_excludes_admin_from_engine_set() -> None:
    """The `engines` Set MUST NOT contain "(admin API)" — it's a
    display label for null engines, not an engine name."""
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    # Locate the summaryByActor useMemo body.
    m = re.search(
        r"summaryByActor\s*=\s*useMemo[\s\S]*?\}\s*,\s*\[",
        src,
    )
    assert m, "summaryByActor useMemo not found"
    body = m.group(0)
    # The bug shape includes both direct .add("(admin API)") AND
    # .add(field ?? "(admin API)"). Either shape means null engine
    # falls into the Set as the "(admin API)" placeholder and inflates
    # the count. The correct pattern is `if (engine) set.add(engine)`.
    has_admin_fallback_add = (
        re.search(r"\.add\([^)]*\?\?\s*['\"]\(admin API\)['\"]", body)
        or re.search(r"\.add\(\s*['\"]\(admin API\)['\"]\s*\)", body)
    )
    assert not has_admin_fallback_add, (
        "summaryByActor.engines Set is receiving '(admin API)' as a "
        "fallback for null engine_display_name. Users with 1 real "
        "engine + admin-only calls (e.g. 11113722) then display as "
        "'2 engines'. Only push non-null engine names; the render "
        "layer picks the label based on Set size (0 → '(admin API)', "
        "1 → the engine name, N → 'N engines')."
    )
