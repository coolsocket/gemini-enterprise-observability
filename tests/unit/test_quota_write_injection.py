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

"""RED for INV-quota-002 (2026-07-10) — quota mutation endpoints must
use ScalarQueryParameter binding, NEVER f-string interpolation.

Discovered during full-codebase audit: `quota_set_tier` interpolates
`email`, `tier`, `by`, `notes` directly into the MERGE SQL, and the
single-quote guard (`if "'" in email or "'" in notes`) does NOT stop
common injection payloads (e.g. semicolon, backslash, comment marker,
or a well-formed value that closes the statement).

These tests assert the source code shape, not runtime behavior — we
can't execute BQ from unit tests. If ScalarQueryParameter is present
and no f-string SQL includes the user-supplied names, we're safe.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def _read_quota_route() -> str:
    return (REPO / "apps/api/routes/quota.py").read_text()


def _strip_docstrings_and_comments(src: str) -> str:
    """Remove triple-quoted docstrings and `#` comments so a regex can
    reason about *executable* substrings only."""
    # Triple-double and triple-single quoted blocks (any content, including
    # newlines) — matches docstrings and multi-line string literals alike.
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    src = re.sub(r"'''[\s\S]*?'''", '', src)
    # Line comments (from # to end of line)
    src = re.sub(r'#.*', '', src)
    return src


def test_quota_set_tier_uses_parameter_binding_not_fstring() -> None:
    """quota_set_tier's MERGE must bind email/tier/by/notes as
    ScalarQueryParameter and MUST NOT reference them inside an
    f-string SQL literal.

    Only inspect executable code — docstrings that mention the old
    pattern for historical context don't count.
    """
    raw = _read_quota_route()
    # Grab the function span from the raw source (docstring included),
    # then strip docstrings before pattern-matching for the vulnerability.
    m = re.search(
        r"def quota_set_tier\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)",
        raw, re.DOTALL,
    )
    assert m, "quota_set_tier not found"
    body = _strip_docstrings_and_comments(m.group(0))

    # The function body must reference ScalarQueryParameter for the user inputs.
    assert "ScalarQueryParameter" in body, (
        "quota_set_tier must bind user-supplied fields via "
        "bigquery.ScalarQueryParameter (INV-quota-002). Current code "
        "concatenates them into an f-string SQL literal, which is a real "
        "injection vector (single-quote guard is insufficient)."
    )

    # Find the SQL literal passed to _bq.query and assert it does NOT
    # contain the user field names inside {email}, {tier}, {by}, {notes}
    # f-string substitutions.
    bad_patterns = [r"\{email\}", r"\{tier\}", r"\{by\}", r"\{notes\}"]
    for pat in bad_patterns:
        assert not re.search(pat, body), (
            f"quota_set_tier body still contains an f-string substitution "
            f"for a user-controlled field: {pat}. Move to "
            f"ScalarQueryParameter (INV-quota-002)."
        )


def test_quota_config_set_stays_parameterized() -> None:
    """Regression: quota_config_set is the reference correct impl;
    make sure a future refactor doesn't degrade it."""
    src = _read_quota_route()
    m = re.search(
        r"def quota_config_set\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)",
        src, re.DOTALL,
    )
    assert m, "quota_config_set not found"
    body = m.group(0)
    assert "ScalarQueryParameter" in body, (
        "quota_config_set previously used ScalarQueryParameter — do not "
        "regress (INV-quota-002)."
    )
    for pat in [r"\{key\}", r"\{value\}", r"\{by\}"]:
        assert not re.search(pat, body), (
            f"quota_config_set now interpolates {pat} — regressed from the "
            f"parameterized reference impl (INV-quota-002)."
        )
