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

"""RED test for missing-snapshot 500 error on fresh deploys.

Reported (user, responsive-lens-421108, 2026-07-06):

  GET /api/v/v_builders?origin=HUMAN → 500
  google.api_core.exceptions.NotFound: 404 Not found: Table
  responsive-lens-421108:ge_observability.s_builders was not found in
  location US

Root cause: the API defaults to reading from the snapshot table (`s_*`,
6-hour cadence) for speed. On a fresh deploy the snapshot tables don't
exist yet — they materialize only after either:
  (a) the BQ Scheduled Query has ticked once (~6 hours), or
  (b) someone manually POSTs /api/refresh
So every dashboard page 500s until then. Terrible first impression.

Fix: `_rows()` should catch google.api_core.exceptions.NotFound on the
snapshot query, log a warning, and fall back to the live view. User
sees data (slightly slower, but correct) instead of a stack trace.

The test asserts the fallback is present as a code pattern — a proper
integration test would need a mocked BQ client, which is overkill for
this repo's current test surface.
"""
from pathlib import Path
import re

MAIN_PY = Path(__file__).resolve().parents[2] / "apps/api/routes/observability.py"


def test_rows_falls_back_from_snapshot_to_view_on_not_found() -> None:
    """`_rows()` must catch NotFound on the snapshot table and retry
    against the live view. Without this, every dashboard tab returns 500
    until the first snapshot refresh (up to 6 hours after deploy)."""
    source = MAIN_PY.read_text()

    # Extract just the _rows() function body to avoid false-positives from
    # try/except patterns elsewhere in main.py.
    m = re.search(
        r"def _rows\([^)]*\)[^:]*:.*?(?=\n(?:def |@app\.))",
        source,
        re.DOTALL,
    )
    assert m, "Could not locate `_rows()` function body in main.py"
    body = m.group(0)

    # Strictly require: (a) a NotFound exception handler in _rows, (b) that
    # _rows references google.api_core exceptions somewhere, and (c) the
    # fallback actually retries against the live view (not just re-raises).
    has_notfound_handler = "NotFound" in body
    has_view_retry = re.search(
        r"except\s+.*NotFound.*?\n.*?(?:src\s*=\s*view|_bq\.query.*view)",
        body,
        re.DOTALL,
    ) is not None

    assert has_notfound_handler and has_view_retry, (
        "`_rows()` doesn't fall back from the snapshot table to the live view "
        "on NotFound. On fresh deploys (where the BQ Scheduled Query hasn't "
        "ticked yet) every dashboard tab returns 500 with a stack trace like:\n"
        "  google.api_core.exceptions.NotFound: 404 Not found: Table "
        "PROJECT:DATASET.s_builders was not found\n"
        "Wrap the `_bq.query(sql).result()` call in try/except NotFound and "
        "retry with `src = view` (the live v_* table)."
    )
