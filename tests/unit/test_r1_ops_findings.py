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

"""R1 challenge findings (2026-07-08) — ops / deploy / cost angles."""
from pathlib import Path
import re

REFRESH = Path(__file__).resolve().parents[2] / "apps/api/routes/refresh.py"


def test_refresh_status_handles_missing_snapshot_meta() -> None:
    """On a fresh deploy where terraform hasn't created snapshot_meta yet
    (or where a user manually dropped it), GET /api/refresh/status MUST
    return an empty payload with a hint — not 500."""
    src = REFRESH.read_text()
    m = re.search(r"def refresh_status.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "refresh_status function not found"
    body = m.group(0)
    assert "NotFound" in body or "except" in body, (
        "refresh_status has no exception handling — 500s on any BQ error "
        "including the missing-snapshot_meta case on a fresh deploy. "
        "Catch NotFound and return `{snapshots:[], last_refresh: null, "
        "snapshot_count: 0, note: 'snapshot_meta not created yet — run "
        "make bootstrap or tf apply'}`"
    )


def test_refresh_now_writes_snapshot_meta_via_params_not_fstring() -> None:
    """`triggered_by` is a user-controllable query param. Currently
    interpolated into an INSERT string via f-string — SQL-injectable
    (unlikely to be exploited given internal use but bad hygiene).
    Fix: use bigquery.QueryJobConfig with query_parameters."""
    src = REFRESH.read_text()
    m = re.search(r"def refresh_now.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "refresh_now function not found"
    body = m.group(0)
    # Look for INSERT INTO snapshot_meta anywhere in the function that
    # also contains a raw `'{triggered_by}'` f-string interpolation.
    has_snapshot_insert = "INSERT INTO" in body and "snapshot_meta" in body
    has_direct_interp = has_snapshot_insert and "'{triggered_by}'" in body
    assert not has_direct_interp, (
        "refresh_now INSERT INTO snapshot_meta directly f-string-interpolates "
        "`triggered_by` param (user-controllable). SQL-injectable.\n"
        "Fix: `bigquery.QueryJobConfig(query_parameters=[...])` + `@triggered_by` "
        "placeholder in SQL."
    )


def test_refresh_now_parallelizes_view_processing() -> None:
    """21 views × 3 queries serial ≈ 60s+ blocks uvicorn's HTTP response
    (default keep-alive is short). Fan out via ThreadPoolExecutor
    like user_deep_dive does — cuts wall time to max-single-view."""
    src = REFRESH.read_text()
    m = re.search(r"def refresh_now.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "refresh_now function not found"
    body = m.group(0)
    # Either ThreadPoolExecutor or asyncio.gather is fine — both parallelize.
    has_parallel = (
        "ThreadPoolExecutor" in body
        or "asyncio.gather" in body
        or "pool.map" in body
    )
    assert has_parallel, (
        "refresh_now processes 21 views serially in a `for` loop. Each iteration "
        "does 3 BQ queries (CREATE OR REPLACE TABLE, COUNT(*), INSERT), so total "
        "wall time ~ 21 × 3 × ~1s ≈ 60s+. That exceeds most reverse-proxy "
        "timeouts and every user's patience.\n"
        "Fix: wrap the per-view work in a helper + ThreadPoolExecutor "
        "(max_workers=~10). See user_deep_dive() in observability.py for the "
        "pattern."
    )
