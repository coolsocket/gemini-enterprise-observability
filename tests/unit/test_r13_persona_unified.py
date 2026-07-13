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

"""RED for R13 (2026-07-13) — full outer join view of Persona.

Batch E (2971c54) added two sibling panels but never merged them.
User pushback (2026-07-13): "全量方案 你没真做, 卡点在哪".

Answered: nothing technical is blocking — vivo userLicenses.
userPrincipal AND v_user_persona.user are both numeric OIDC subject
strings, they join cleanly. Live probe on vivo:
  173 matched  ·  6 log-only  ·  150 seat-only  →  union 329.

R13 delivers the merge:
  * New pure merger in the observability domain
    (`persona_join_licenses`) — pure fn, take two lists, return the
    union with a `cohort` label on each row.
  * New route /api/persona/unified — fetches both sources concurrently
    and returns the merged shape + cohort counts.
  * Persona.tsx grows a third panel using the unified endpoint,
    with cohort filter chips so an operator can zoom to any bucket.
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


# -------- domain merger --------

def test_persona_join_domain_module_exists() -> None:
    """Pure merger lives in the observability context (uses
    v_user_persona shape) — not routes/refresh, because that's I/O."""
    path = REPO / "apps/api/contexts/observability/domain/persona_join.py"
    assert path.exists(), (
        "Missing apps/api/contexts/observability/domain/persona_join.py "
        "— pure fn that takes (persona_rows, licensed_rows) and returns "
        "the union with a `cohort` label per row."
    )
    src = path.read_text()
    for banned in ("google.cloud", "fastapi", "urllib.request", "requests"):
        assert banned not in src, (
            f"persona_join.py should be pure — no {banned}."
        )
    assert "def persona_join_licenses" in src, (
        "persona_join.py must export a `persona_join_licenses(persona, "
        "licenses)` function."
    )


def test_persona_join_produces_three_cohorts() -> None:
    """Given a fixture with one matched, one licensed-only, one log-
    only, the merger must emit 3 rows tagged with the three cohorts."""
    from apps.api.contexts.observability.domain.persona_join import persona_join_licenses
    persona = [
        {"user": "111", "persona": "ACTIVE_CONSUMER", "chat_turns_total": 12, "last_seen": "2026-07-13"},
        {"user": "222", "persona": "LURKER", "chat_turns_total": 0, "last_seen": None},
        # user 333 not in persona (log-only doesn't exist here; we cover
        # the reverse: someone appears in persona but not licenses).
        {"user": "999", "persona": "TRIAL", "chat_turns_total": 2, "last_seen": "2026-07-12"},
    ]
    licenses = [
        {"user_principal": "111", "state": "ASSIGNED", "last_login_time": "2026-07-13T00:00:00Z"},
        {"user_principal": "222", "state": "ASSIGNED", "last_login_time": None},
        {"user_principal": "333", "state": "ASSIGNED", "last_login_time": "2026-07-10T00:00:00Z"},
    ]
    out = persona_join_licenses(persona, licenses)
    users = out["users"]
    counts = out["counts"]
    # Union should be 4 (111, 222, 333, 999)
    assert len(users) == 4, f"expected 4 union rows, got {len(users)}"
    # By-cohort counts
    assert counts["matched"] == 2       # 111, 222
    assert counts["licensed_only"] == 1 # 333 (has license, no persona)
    assert counts["log_only"] == 1      # 999 (persona but no license)
    assert counts["total"] == 4
    # Each row has a cohort label
    for row in users:
        assert row.get("cohort") in {"matched", "licensed_only", "log_only"}


def test_persona_join_row_shape() -> None:
    """Every unified row must have both persona-side and license-side
    fields (nullable when the row is only in one source)."""
    from apps.api.contexts.observability.domain.persona_join import persona_join_licenses
    persona = [{"user": "111", "persona": "POWER_USER", "chat_turns_total": 30}]
    licenses = [{"user_principal": "222", "state": "ASSIGNED", "last_login_time": None}]
    out = persona_join_licenses(persona, licenses)
    for row in out["users"]:
        for k in ("user_principal", "cohort", "license_state",
                  "persona", "chat_turns_total", "last_login_time"):
            assert k in row, f"unified row missing key: {k}\n  row={row!r}"


# -------- route + wire --------

def test_route_persona_unified_exists() -> None:
    """GET /api/persona/unified must exist in one of the route files."""
    for name in ("refresh.py", "observability.py"):
        src = (REPO / "apps/api/routes" / name).read_text()
        if re.search(r'@router\.get\(\s*["\']/api/persona/unified["\']', src):
            return
    raise AssertionError(
        "No @router.get for /api/persona/unified found in refresh.py or "
        "observability.py — add the route that fans out to both "
        "_fetch_user_licenses + v_user_persona and calls "
        "persona_join_licenses to produce the unified shape."
    )


def test_frontend_persona_page_uses_unified() -> None:
    """Persona.tsx should fetch the unified endpoint and render at
    least one cohort-labeled panel."""
    src = (REPO / "apps/web/src/pages/Persona.tsx").read_text()
    fetches = (
        "/api/persona/unified" in src
        or "personaUnified" in src
        or "unifiedPersona" in src
    )
    assert fetches, (
        "Persona.tsx doesn't fetch the new /api/persona/unified — "
        "add a useQuery + render a panel showing all 329 vivo rows "
        "with cohort chips (matched / licensed_only / log_only)."
    )
    # And the cohort labels should appear so the user sees the bucketing
    for label in ("matched", "licensed_only", "log_only"):
        assert label in src or f'"{label}"' in src, (
            f"Persona.tsx doesn't reference cohort '{label}' — the "
            f"cohort chips must be discoverable."
        )
