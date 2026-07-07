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

"""Issue #2 item 3 — /api/user/{email} live flag inconsistency.

The endpoint accepts `?live=true` and MOST queries honor it via the
tbl() lambda. But two entries (dr_prompts, custom_agent_prompts) hard-
code `{PROJECT}.{DATASET}.v_*` — always live, regardless of the flag.
That means:
  - ?live=false (default): 15 snapshot reads + 2 live reads. Snapshot
    users get inconsistent freshness across panels.
  - ?live=true: works by coincidence.
  - Cost surprise: even the default "snapshot" case hits BQ live views
    for these two panels, defeating the whole point of snapshotting.

Also, `session_files` queries `v_session_files` — a view that has
never been defined in views.sql.tmpl. Every call fails silently and
returns [].
"""
from pathlib import Path

OBS = Path(__file__).resolve().parents[2] / "apps/api/routes/observability.py"


def _user_deep_dive_body() -> str:
    """Return the source of the user_deep_dive function, so we can check
    the flag is honored inside it (without false-positive-matching other
    endpoints that legitimately query the live view — e.g. /api/agent/{id})."""
    src = OBS.read_text()
    import re
    m = re.search(
        r"def user_deep_dive\([^)]*\)[^:]*:.*?(?=^\S|\Z)",
        src, re.DOTALL | re.MULTILINE,
    )
    assert m, "user_deep_dive function not found in observability.py"
    return m.group(0)


def test_dr_prompts_uses_tbl_helper() -> None:
    """Inside user_deep_dive, dr_prompts must use tbl() so `live=false`
    reads s_deep_research_prompts instead of hammering the live view."""
    body = _user_deep_dive_body()
    assert "v_deep_research_prompts" not in body or "tbl('v_deep_research_prompts')" in body, (
        "user_deep_dive's dr_prompts query hardcodes v_deep_research_prompts. "
        "Route it through the tbl() lambda so ?live=false reads the snapshot."
    )
    assert "{PROJECT}.{DATASET}.v_deep_research_prompts" not in body, (
        "user_deep_dive still has a hardcoded FROM `{PROJECT}.{DATASET}."
        "v_deep_research_prompts` — replace with `{tbl('v_deep_research_prompts')}`."
    )


def test_custom_agent_prompts_uses_tbl_helper() -> None:
    body = _user_deep_dive_body()
    assert "{PROJECT}.{DATASET}.v_custom_agent_prompts" not in body, (
        "user_deep_dive still has a hardcoded FROM `{PROJECT}.{DATASET}."
        "v_custom_agent_prompts` — replace with `{tbl('v_custom_agent_prompts')}`."
    )


def test_no_session_files_dead_reference() -> None:
    """v_session_files is not defined anywhere. Referencing it always
    yields NotFound → silent []. Remove the dead entry."""
    src = OBS.read_text()
    assert "v_session_files" not in src, (
        "user_deep_dive references v_session_files, which is not defined "
        "in views.sql.tmpl. The query always fails and returns []. "
        "Delete the entry (and its response-shape consumer if any)."
    )
