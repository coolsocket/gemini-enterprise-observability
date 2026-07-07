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

"""RED regressions for missing-view handling — user report 2026-07-07 that
the reporter's dashboard threw 500 on `GET /api/v/v_agent_usage`:

  WARNING:ge-obs:snapshot s_agent_usage not found — falling back to live
  view v_agent_usage
  ...
  google.api_core.exceptions.NotFound: 404 Not found: Table
  responsive-lens-421108:ge_observability.v_agent_usage was not found

Two orthogonal defects surface together:

A) `_rows` fallback branch (`observability.py::_rows` line 79) catches
   NotFound on the SNAPSHOT query but NOT on the live-view query it
   falls back to. If both are missing (view was never defined, or
   log-sink tables absent), 500 escapes to the user.

B) The view registry (`view_registry.py::VIEWS`) still lists
   v_agent_usage and v_session_files, but views.sql.tmpl has never
   contained CREATE OR REPLACE VIEW for either. The registry can
   silently drift from the SQL layer — inverse of issue #2.2's
   tftpl-vs-tmpl drift.

Fixes tested here:
  1. Any /api/v/<view> — even if view is in registry but view is
     genuinely missing in BQ — must NOT 500. Return `{rows:[], count:0,
     …, "note": "view not yet available"}` so the frontend's EmptyState
     panel renders cleanly.
  2. Every entry in VIEWS registry MUST have a corresponding
     CREATE OR REPLACE VIEW in views.sql.tmpl (parallel to INV-003).
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
VIEWS_TMPL = ROOT / "infra/sql_templates/views.sql.tmpl"
OBS_ROUTES = ROOT / "apps/api/routes/observability.py"
VIEW_REGISTRY = ROOT / "apps/api/contexts/observability/domain/view_registry.py"


def _defined_views_in_tmpl() -> set[str]:
    return set(re.findall(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.(v_[a-z_]+)`",
        VIEWS_TMPL.read_text(),
        re.IGNORECASE,
    ))


def _registered_view_names() -> set[str]:
    """Extract keys of the VIEWS dict from view_registry.py by regex — avoids
    the import path fragility of running pytest from repo root."""
    src = VIEW_REGISTRY.read_text()
    # Take the block between `VIEWS: dict... = {` and the closing `}` (naive
    # but sufficient — dict literal has no nested `{...}` at column 0).
    m = re.search(r"VIEWS[^=]*=\s*\{(.*?)^\}", src, re.DOTALL | re.MULTILINE)
    assert m, "could not locate VIEWS dict in view_registry.py"
    body = m.group(1)
    return set(re.findall(r'^\s*"(v_[a-z_]+)"\s*:', body, re.MULTILINE))


def test_registry_subset_of_views_sql_tmpl() -> None:
    """Every view in the runtime registry MUST have a definition. Otherwise
    the API happily accepts requests for that view name and passes them
    down to BQ, which 404s them, and depending on the code path either
    returns 500 or degrades. Both are worse than a static failure at
    dev time. Inverse of INV-003 (tftpl ⊆ tmpl); together they lock
    all three files in sync: registry ⇄ tmpl ⇄ tftpl."""
    defined = _defined_views_in_tmpl()
    registered = _registered_view_names()
    assert registered, "regex didn't find any v_* entries — extractor broken"
    orphan = registered - defined
    assert not orphan, (
        f"Registry lists view(s) never defined in views.sql.tmpl: "
        f"{sorted(orphan)}. Either (a) add the view definition to "
        f"views.sql.tmpl, or (b) remove the entry from VIEWS "
        f"(and the corresponding VIEWS_WITH_ORIGIN / VIEWS_WITH_ENGINE "
        f"/ VIEW_TIME_COL entries, and any frontend page that requests it)."
    )


def test_rows_fallback_catches_notfound_on_live_view() -> None:
    """`_rows` fallback branch must catch NotFound on the live-view retry
    too, not just on the snapshot query. Otherwise: snapshot missing →
    fallback → live view also missing → 500 to the user.

    Assertion: the fallback code path (after `snapshot not found — falling
    back to live view`) is wrapped in its own try/except NotFound."""
    src = OBS_ROUTES.read_text()
    # Extract the _rows function body
    m = re.search(r"def _rows\([^)]*\)[^:]*:.*?(?=\n(?:@router|def |# ==))", src, re.DOTALL)
    assert m, "could not locate _rows() in observability.py"
    body = m.group(0)

    # Find the fallback query line: `_bq.query(fallback_sql).result()`
    assert "fallback_sql" in body, "test premise broken — no fallback_sql in _rows"

    # The line that calls `_bq.query(fallback_sql).result()` must be inside
    # a try/except NotFound. Cheap heuristic: an "except NotFound" (2nd
    # occurrence) or a "try:" clause preceding the fallback line at a
    # deeper indent than the snapshot try. Loosest check: count `except
    # NotFound` occurrences — must be ≥ 2 (one for snapshot, one for live).
    except_count = len(re.findall(r"except\s+NotFound", body))
    assert except_count >= 2, (
        f"_rows() catches NotFound only {except_count}x — should be ≥2 "
        f"(one for the snapshot query, one for the live-view fallback). "
        f"Without the second catch, a genuinely missing view (never "
        f"defined, or log-sink tables absent) 500s the user.\n"
        f"Fix: wrap the fallback `_bq.query(fallback_sql).result()` in "
        f"try/except NotFound → return [] with a WARNING log."
    )
