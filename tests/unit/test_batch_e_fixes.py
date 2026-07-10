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

"""RED for Batch E (2026-07-10) — reporter's Persona item #1:

  Reporter: "用户画像 · 全量用户从订阅接口 + 日志"

  v_user_persona is derived from event logs — it only shows users who
  actually DID something. Reporter wants ALL licensed users, including
  those who bought a seat but never opened the product.

  Discovery Engine v1alpha exposes per-user assignments at
    /v1alpha/projects/{P}/locations/global/userStores/{S}/userLicenses
  Live-verified on responsive-lens-421108 — returns rows with
  userPrincipal, licenseAssignmentState, licenseConfig, createTime,
  updateTime, lastLoginTime.

  E1 · Add a fetch+parse in the quota context (like license_parse but
       for per-user assignments). Pure fn returning MERGE-ready rows.

  E2 · Wire a GET /api/persona/licensed-users endpoint. Return
       {users, count, note?}. On 403/404 or empty tenant, return
       {users: [], count: 0, note: "..."} — must not 500.

  E3 · Persona.tsx surfaces the licensed roster. At minimum a new
       Panel titled with "seat" or "licens" that lists them.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_e1_user_license_parser_exists_and_is_pure() -> None:
    """A new parser lives in the quota context, next to license_parse.py.
    Must be a pure function (no I/O)."""
    path = REPO / "apps/api/contexts/quota/domain/user_license_parse.py"
    assert path.exists(), (
        "Missing apps/api/contexts/quota/domain/user_license_parse.py. "
        "Add a pure `parse_user_licenses(rows)` fn analogous to "
        "parse_license_configs — no HTTP, no BQ."
    )
    src = path.read_text()
    assert "def parse_user_licenses" in src, (
        "user_license_parse.py must export a `parse_user_licenses` function."
    )
    # Purity: no imports of google.cloud / requests / urllib.request
    for banned in ("import requests", "urllib.request", "google.cloud"):
        assert banned not in src, (
            f"user_license_parse.py should be a pure parser — no {banned}. "
            "I/O belongs in routes/refresh.py."
        )


def test_e1_parser_shape() -> None:
    """Parser output includes assigned/unseen counts + per-user rows.
    Tests the shape against a fixture derived from the real API."""
    from apps.api.contexts.quota.domain.user_license_parse import parse_user_licenses
    fixture = [
        {"userPrincipal": "1001", "licenseAssignmentState": "ASSIGNED",
         "licenseConfig": "projects/x/locations/global/licenseConfigs/abc",
         "createTime": "2026-06-12T01:51:34Z",
         "lastLoginTime": "2026-07-09T16:20:23Z"},
        {"userPrincipal": "1002", "licenseAssignmentState": "ASSIGNED",
         "licenseConfig": "projects/x/locations/global/licenseConfigs/abc",
         "createTime": "2026-06-12T01:51:34Z"},  # never logged in
        {"userPrincipal": "1003", "licenseAssignmentState": "UNASSIGNED",
         "licenseConfig": "projects/x/locations/global/licenseConfigs/abc"},
    ]
    parsed = parse_user_licenses(fixture)
    assert parsed["count"] == 3
    assert parsed["assigned_count"] == 2
    assert parsed["unseen_count"] == 1, (
        "unseen = assigned but no lastLoginTime; expected 1 in fixture"
    )
    assert len(parsed["users"]) == 3
    # Each user has stable keys
    for u in parsed["users"]:
        for k in ("user_principal", "state", "license_config",
                  "create_time", "last_login_time"):
            assert k in u, f"user row missing key: {k}"


def test_e2_route_licensed_users_exists() -> None:
    src = (REPO / "apps/api/routes/refresh.py").read_text()
    has_route = re.search(
        r"@router\.(get|post)\(\s*[\"']/api/persona/licensed-users[\"']",
        src,
    )
    assert has_route, (
        "Missing route: GET /api/persona/licensed-users. Wire the fetch + "
        "parse_user_licenses + return {users, count, note?}. Handle 403/404 "
        "gracefully so sandbox tenants without DE setup don't 500."
    )


def test_e3_persona_page_shows_licensed_roster() -> None:
    src = (REPO / "apps/web/src/pages/Persona.tsx").read_text()
    # Fetches the licensed-users endpoint
    fetches = (
        "licensed-users" in src
        or "licensedUsers" in src
        or "personaLicensedUsers" in src
    )
    assert fetches, (
        "Persona.tsx doesn't fetch the licensed roster. Add a useQuery "
        "against api.personaLicensedUsers() and render its result."
    )
    # And there's a visible section for it
    assert re.search(r"(seat|licens|订阅|订阅接口|全量|购买)", src, re.IGNORECASE), (
        "Persona.tsx renders licensed data but no panel heading references "
        "'seat' / 'license' / '订阅' — add a <Panel> so it's discoverable."
    )
