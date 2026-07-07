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

"""Static regression: IdentityResolver is actually consumed by the
observability routes (list_users + user_deep_dive). Without this,
the frontend can never render identity_kind badges — the field would
just not appear in responses."""
from pathlib import Path
import re

OBS = Path(__file__).resolve().parents[2] / "apps/api/routes/observability.py"


def test_list_users_attaches_identity_kind() -> None:
    src = OBS.read_text()
    m = re.search(r"def list_users\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "list_users function not found in observability.py"
    body = m.group(0)
    assert "identity_kind" in body, (
        "list_users response entries don't include `identity_kind`. "
        "Frontend can't differentiate Google email / OIDC / SA / simulated "
        "in the picker without this field. Import "
        "`from ...domain.identity import resolve as resolve_identity` "
        "and attach `row['identity_kind'] = resolve_identity(row['actor_email']).kind.value`."
    )
    assert "resolve" in body and "identity" in body, (
        "list_users doesn't call the IdentityResolver — the string "
        "`identity_kind` was found but no resolver invocation. Wire the "
        "actual call, not a hard-coded field."
    )


def test_user_deep_dive_attaches_full_identity() -> None:
    src = OBS.read_text()
    m = re.search(r"def user_deep_dive\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL)
    assert m, "user_deep_dive function not found"
    body = m.group(0)
    # Payload must include an `identity` key populated from resolver
    assert '"identity"' in body or "'identity'" in body, (
        "user_deep_dive response doesn't include an `identity` field. "
        "Add one populated from `resolve_identity(principalEmail, "
        "principalSubject)` so frontend detail page can show vendor "
        "badge (Okta / Microsoft / Google / etc.)."
    )
    # Vendor detection requires reading principalSubject from raw audit —
    # otherwise the view-collapsed actor_email loses vendor info.
    assert "principalSubject" in body, (
        "user_deep_dive doesn't read principalSubject from raw audit. "
        "Without that, IdentityResolver can only tell HUMAN/SA/OIDC_SUBJECT "
        "— not the vendor (Okta / Azure / generic WIF). Add a targeted "
        "raw-audit lookup that returns (principalEmail, principalSubject) "
        "for this user, then pass BOTH to the resolver."
    )
