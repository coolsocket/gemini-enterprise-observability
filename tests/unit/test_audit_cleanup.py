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

"""Regressions surfaced during the 2026-07-07 self-audit.

Two independent issues that adversarial fuzzing / static drift check
turned up after the OIDC/identity fix chain:

  1. Frontend .tsx pages still reference view names that were removed
     from view_registry.py in commit 4e06da8 (v_session_files,
     v_agent_usage). Backend now returns [] gracefully — but the SPA
     wastes two BQ round-trips per Files.tsx / Engines.tsx render and
     shows always-empty panels. Delete the dead calls.

  2. /api/summary?since_hours=<huge-number> causes HTTP 500 because
     BQ's TIMESTAMP_SUB overflows. Cap or 400.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_no_frontend_references_to_removed_views() -> None:
    """Inverse of INV-obs-drift: frontend must not request v_* names that
    were deliberately removed from view_registry.py. Backend degrades
    gracefully (INV-obs-004 wired via _rows 2nd-NotFound catch), but
    always-empty panels are worse UX than no panel."""
    REMOVED = {"v_session_files", "v_agent_usage"}
    offenders: list[str] = []
    for tsx in (REPO / "apps/web/src").rglob("*.tsx"):
        text = tsx.read_text()
        for view in REMOVED:
            if view in text:
                offenders.append(f"{tsx.relative_to(REPO)}: references {view}")
    assert not offenders, (
        f"{len(offenders)} frontend references to deleted views:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nEither add the view back (with a real definition in "
        "views.sql.tmpl + registry entry), or delete the panel from "
        "the .tsx file. Currently every render fires 2 dead BQ queries "
        "per page load and shows always-empty panels."
    )


def test_summary_endpoint_caps_since_hours() -> None:
    """`?since_hours=<huge>` shouldn't 500 — the endpoint MUST either
    reject via 400 or silently cap to a sane maximum (e.g. 8760h = 1 year)
    before the value reaches BQ. TIMESTAMP_SUB overflow on the SQL layer
    surfaces as opaque 500 to the operator."""
    src = (REPO / "apps/api/routes/observability.py").read_text()
    m = re.search(r"def summary\([^)]*\)[^:]*:.*?(?=\n@router|\Z)", src, re.DOTALL)
    assert m, "summary route not found"
    body = m.group(0)
    # Look for either an explicit cap (min(since_hours, N)), an assert
    # / raise HTTPException(400, ...) on since_hours, or a bounded
    # constant like MAX_SINCE_HOURS.
    has_cap = (
        re.search(r"min\(\s*since_hours", body)
        or re.search(r"since_hours\s*>\s*\d+", body)
        or "MAX_SINCE_HOURS" in body
    )
    assert has_cap, (
        "summary() has no upper-bound guard on since_hours. Pass a "
        "value like 999999999 and BQ 500s on TIMESTAMP_SUB overflow. "
        "Fix: cap `since_hours = min(since_hours, 8760)` (1 year) at "
        "the top of the function, or raise HTTPException(400) if it's "
        "out of range."
    )
