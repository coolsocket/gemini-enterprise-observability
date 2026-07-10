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

"""RED for R5-revert (2026-07-10) — user asked to hide the
NO_LICENSE_ATTEMPTED_LOGIN cohort entirely: "NO_LICENSE_ATTEMPTED_LOGIN
的用户全部不要显示，删掉就好".

The prior R5 commit surfaced them as a distinct "想用但被挡" filter +
red-highlight chip on Persona. The user reviewed the live vivo view
and decided they add noise more than signal. Filter them out at the
parser (so the frontend never sees them), and strip the UI additions.

Invariants asserted here:
  * parse_user_licenses.users MUST NOT contain any row whose
    licenseAssignmentState == NO_LICENSE_ATTEMPTED_LOGIN
  * count MUST reflect the filtered length, not the raw input length
    (so `count` == `assigned_count + NO_LICENSE-only rows`, which for
    vivo's fixture drops from 407 → 324)
  * blocked_count MAY still be reported for observability, but
    Persona.tsx MUST NOT reference the state string or blocked_count
    anywhere in its render tree
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_parser_filters_out_blocked_rows() -> None:
    from apps.api.contexts.quota.domain.user_license_parse import parse_user_licenses
    fixture = [
        {"userPrincipal": "1001", "licenseAssignmentState": "ASSIGNED",
         "lastLoginTime": "2026-07-01T00:00:00Z"},
        {"userPrincipal": "1002", "licenseAssignmentState": "ASSIGNED"},
        {"userPrincipal": "1003", "licenseAssignmentState": "NO_LICENSE_ATTEMPTED_LOGIN",
         "lastLoginTime": "2026-07-02T00:00:00Z"},
        {"userPrincipal": "1004", "licenseAssignmentState": "NO_LICENSE_ATTEMPTED_LOGIN",
         "lastLoginTime": "2026-07-03T00:00:00Z"},
        {"userPrincipal": "1005", "licenseAssignmentState": "NO_LICENSE"},
    ]
    out = parse_user_licenses(fixture)

    # No blocked rows leak into the users list.
    for u in out["users"]:
        assert u["state"] != "NO_LICENSE_ATTEMPTED_LOGIN", (
            f"NO_LICENSE_ATTEMPTED_LOGIN row leaked into parser output: "
            f"{u!r}. These should be filtered upstream — per user request "
            f"2026-07-10 they add noise, not signal."
        )
    # count reflects the filtered list (3 remaining: 2 ASSIGNED + 1 NO_LICENSE),
    # NOT the raw fixture length of 5.
    assert out["count"] == 3, (
        f"count should reflect filtered length; got {out['count']} for a "
        f"fixture where 2 of 5 rows were blocked (should drop to 3)."
    )
    # assigned_count unchanged
    assert out["assigned_count"] == 2


def test_persona_page_no_blocked_references() -> None:
    """Persona.tsx should NOT mention NO_LICENSE_ATTEMPTED_LOGIN or
    blocked_count anywhere — the user rejected surfacing that cohort."""
    src = (REPO / "apps/web/src/pages/Persona.tsx").read_text()
    assert "NO_LICENSE_ATTEMPTED_LOGIN" not in src, (
        "Persona.tsx still references NO_LICENSE_ATTEMPTED_LOGIN — the "
        "R5 UI additions must be reverted (filter chip, red highlight, "
        "warn banner, panel title, sort priority)."
    )
    assert "blocked_count" not in src, (
        "Persona.tsx still references blocked_count — drop the count "
        "reference from the panel title so it stays clean."
    )
    assert "想用但被挡" not in src, (
        "Persona.tsx still has the '想用但被挡' UI copy — remove all "
        "traces of the blocked cohort."
    )
