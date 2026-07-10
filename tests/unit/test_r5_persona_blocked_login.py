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

"""RED for R5 (2026-07-10) — Persona page must surface people who
TRIED to log into GE but had no license.

Discovery Engine's userLicenses API returns three states:
  ASSIGNED                     — has a license
  NO_LICENSE                   — no license, no login attempt recorded
  NO_LICENSE_ATTEMPTED_LOGIN   — tried to log in, DE blocked them

On live vivo (2026-07-10) the distribution is 322 / 2 / 83. The 83
NO_LICENSE_ATTEMPTED_LOGIN principals are demand signal — someone
navigated to GE, hit the wall, and never got in. That's more urgent
for an admin than "user has seat but hasn't logged in yet".

R5a · Parser must expose `blocked_count` (NO_LICENSE_ATTEMPTED_LOGIN).
R5b · Persona.tsx must reference the state string so admins can
      filter/sort/highlight the blocked cohort separately from the
      "assigned-but-unseen" cohort.
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_parser_exposes_blocked_count() -> None:
    """`parse_user_licenses` output should include `blocked_count` (users
    with state == NO_LICENSE_ATTEMPTED_LOGIN). Currently only
    `assigned_count` and `unseen_count` are surfaced — the 83 blocked
    are invisible to the frontend without extra scanning."""
    from apps.api.contexts.quota.domain.user_license_parse import parse_user_licenses
    fixture = [
        {"userPrincipal": "1001", "licenseAssignmentState": "ASSIGNED",
         "lastLoginTime": "2026-07-01T00:00:00Z"},
        {"userPrincipal": "1002", "licenseAssignmentState": "ASSIGNED"},  # unseen
        {"userPrincipal": "1003", "licenseAssignmentState": "NO_LICENSE_ATTEMPTED_LOGIN",
         "lastLoginTime": "2026-07-02T00:00:00Z"},
        {"userPrincipal": "1004", "licenseAssignmentState": "NO_LICENSE_ATTEMPTED_LOGIN",
         "lastLoginTime": "2026-07-03T00:00:00Z"},
        {"userPrincipal": "1005", "licenseAssignmentState": "NO_LICENSE"},
    ]
    out = parse_user_licenses(fixture)
    assert "blocked_count" in out, (
        "parse_user_licenses missing `blocked_count` (# rows in state "
        "NO_LICENSE_ATTEMPTED_LOGIN). Add it so the Persona UI can render "
        "the 'wanted to use but got blocked' cohort as its own panel."
    )
    assert out["blocked_count"] == 2, (
        f"blocked_count should count NO_LICENSE_ATTEMPTED_LOGIN rows only; "
        f"got {out.get('blocked_count')} for fixture with 2 such rows."
    )


def test_persona_page_surfaces_blocked_cohort() -> None:
    """Persona.tsx must reference the NO_LICENSE_ATTEMPTED_LOGIN state
    so admins can see the blocked users distinctly. Either a filter,
    a separate panel, or a labeled chip counts."""
    src = (REPO / "apps/web/src/pages/Persona.tsx").read_text()
    assert "NO_LICENSE_ATTEMPTED_LOGIN" in src or "blocked_count" in src, (
        "Persona.tsx doesn't reference NO_LICENSE_ATTEMPTED_LOGIN or "
        "blocked_count. Add a filter/panel that highlights these — they "
        "are 'demand signal' (tried to use GE, got walled), more urgent "
        "than the 'unseen' cohort we already surface."
    )
