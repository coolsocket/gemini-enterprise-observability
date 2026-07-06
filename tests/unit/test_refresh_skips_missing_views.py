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

"""RED test: /api/refresh must not spam ERROR logs for views that don't
exist yet on a fresh deploy.

Reported (user, responsive-lens-421108):

  ERROR:ge-obs:refresh failed: s_session_files — 404 Not found: Table
   responsive-lens-421108:ge_observability.v_session_files was not found

Root cause: `refresh_now()` iterates every entry in the VIEWS constant
and tries `CREATE OR REPLACE TABLE s_X AS SELECT * FROM v_X`. On fresh
deploys, some `v_X` views weren't created (because their source
log-sink tables don't exist yet — see the graceful-skip logic in
apply_views.py). So refresh unavoidably fails on those 6, and each
failure is logged at ERROR level, which reads like the system is broken
even though it's an expected transient state.

Fix: refresh should pre-check which v_* views actually exist (via
INFORMATION_SCHEMA.VIEWS), skip missing ones with an INFO log, and
categorize results as `ok` / `skipped` / `failed` — the last only for
truly unexpected errors (permission, SQL syntax, etc.).
"""
from pathlib import Path
import re

MAIN_PY = Path(__file__).resolve().parents[2] / "apps/api/main.py"


def _extract_function(source: str, name: str) -> str:
    """Extract a top-level function definition body (until the next top-level
    def/decorator)."""
    m = re.search(
        rf"^def {name}\([^)]*\)[^:]*:.*?(?=\n(?:def |@app\.))",
        source,
        re.DOTALL | re.MULTILINE,
    )
    return m.group(0) if m else ""


def test_refresh_pre_checks_view_existence() -> None:
    """The refresh recipe must query INFORMATION_SCHEMA.VIEWS (or an
    equivalent existence check) BEFORE trying to `CREATE OR REPLACE TABLE
    s_X AS SELECT * FROM v_X`. Otherwise every missing view surfaces as
    an ERROR-level log on fresh deploys."""
    source = MAIN_PY.read_text()
    body = _extract_function(source, "refresh_now")
    assert body, "refresh_now() not found in main.py"
    # Look for INFORMATION_SCHEMA existence check
    has_precheck = re.search(
        r"INFORMATION_SCHEMA\.\s*(VIEWS|TABLES)",
        body,
        re.IGNORECASE,
    ) is not None
    assert has_precheck, (
        "refresh_now() doesn't pre-check view existence via "
        "INFORMATION_SCHEMA.VIEWS. Add a query like:\n"
        "  SELECT table_name FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.VIEWS`\n"
        "and filter VIEWS by that set before iterating. Missing views should be "
        "returned as `skipped` (not `ok:false`) and logged at INFO/WARNING, "
        "not ERROR."
    )


def test_refresh_does_not_log_missing_view_as_error() -> None:
    """Refresh must not use `log.error(...)` on the code path handling a
    missing source view. Downgrade to `log.info` or `log.warning` — an
    unbuilt view on a fresh deploy is a known-transient state, not an
    operational alarm."""
    source = MAIN_PY.read_text()
    body = _extract_function(source, "refresh_now")
    # Look for the specific bad pattern: `log.error("refresh failed:` (the exact
    # phrasing that surfaced for missing-view case). `log.error("seat refresh
    # failed …")` is fine — seat refresh failure IS a real ERROR-worthy event.
    bad = re.search(r'log\.error\s*\(\s*["\']refresh failed', body)
    assert not bad, (
        "refresh_now() still uses `log.error(\"refresh failed …\", …)`. "
        "Change to `log.warning(...)` when the underlying view is missing "
        "(expected on fresh deploys), and reserve `log.error(...)` for "
        "unexpected errors like permission denied or SQL syntax bugs."
    )
