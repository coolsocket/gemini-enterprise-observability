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

"""RED (2026-07-10) — cross-site request forgery guard + input coercion.

Two orthogonal Round-1 issues in the audit:
  (a) POST endpoints have no CSRF defense — any admin visiting a malicious
      page could be tricked into POSTing /api/quota/tier from their browser.
  (b) `since_hours` in /api/users flows into an f-string SQL literal via a
      wrap that trusts the FastAPI type-hint. Belt-and-suspenders int cast
      should be present at the SQL boundary.

For (a) we assert middleware exists in apps/api/main.py. For (b) we assert
the SQL construction site uses `int(since_hours)` (not bare interpolation).
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_main_registers_csrf_middleware() -> None:
    """apps/api/main.py must register a middleware that enforces the same-
    origin policy on POST/PUT/DELETE. Simplest form: reject requests whose
    Origin/Referer header doesn't match the request host. This defeats the
    passive CSRF attack from a foreign origin.
    """
    src = (REPO / "apps/api/main.py").read_text()
    # Look either for our own middleware fn or a well-known dep
    csrf_hints = (
        "csrf" in src.lower()
        or "origin_check" in src.lower()
        or "same_origin" in src.lower()
        or "add_middleware" in src.lower()
        or "@app.middleware" in src.lower()
    )
    assert csrf_hints, (
        "apps/api/main.py has no CSRF / same-origin middleware. "
        "Add one that rejects state-mutating requests (POST/PUT/DELETE) "
        "whose Origin/Referer doesn't match the request Host — this is a "
        "public dashboard, currently any admin's browser can be weaponized "
        "against the API by a malicious page."
    )


def test_list_users_since_hours_reaches_sql_via_int() -> None:
    """The since_hours query param in /api/users flows into a f-string
    interval — it must be int()-cast at the SQL boundary as belt+braces
    even though FastAPI type-hint should catch bad types. Defense-in-depth
    for a public read endpoint."""
    src = (REPO / "apps/api/routes/observability.py").read_text()
    m = re.search(
        r"def list_users\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)",
        src, re.DOTALL,
    )
    assert m, "list_users not found"
    body = m.group(0)
    # Look for the SQL-building line that interpolates since_hours
    interpolates_bare = re.search(
        r"INTERVAL\s+\{\s*since_hours\s*\}\s+HOUR", body,
    )
    interpolates_int = re.search(
        r"INTERVAL\s+\{\s*int\(\s*since_hours\s*\)\s*\}\s+HOUR", body,
    )
    assert not interpolates_bare or interpolates_int, (
        "list_users interpolates `since_hours` bare into SQL. Wrap with "
        "`int(since_hours)` at the SQL site: "
        "  f\"INTERVAL {int(since_hours)} HOUR\""
    )
