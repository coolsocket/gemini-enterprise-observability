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

"""RED regression: audit-log views blind to OIDC / Workforce Identity
Federation users (verified against responsive-lens-421108, 2026-07-07).

Sampled 1000 rows from cloudaudit_googleapis_com_data_access:
  principalEmail   populated:    3 (0.3%)
  principalEmail   NULL:       997 (99.7%)  ← OIDC users
  principalSubject populated:  ALL 997 of the NULLs, shape:
     principal://iam.googleapis.com/locations/global/workforcePools/
     vivo-gemini-enterprise/subject/72202797

Every audit-log view (v_admin_activity, v_data_access,
v_deep_research_prompts) reads only `authenticationInfo.principalEmail`
and drops rows where it's NULL. Result: 997/1000 rows silently
disappear. 73 distinct OIDC actors invisible to the dashboard.

Also matches the numeric OIDC principals in `user_activity`
(`useriamprincipal = "72202797"`) so extracting subject/<n> gives the
SAME actor_email in both branches — JOINs across Path 2 (user_activity)
and Path 3 (audit) start working.

Fix invariant: every read of `authenticationInfo.principalEmail` MUST
be COALESCEd with `REGEXP_EXTRACT(principalSubject, r'subject/([^/]+)$')`.
Every `WHERE principalEmail IS NOT NULL` MUST use the COALESCEd
expression too — otherwise the WHERE drops OIDC rows even after the
SELECT includes them.
"""
from pathlib import Path
import re

VIEWS_TMPL = Path(__file__).resolve().parents[2] / "infra/sql_templates/views.sql.tmpl"

# The exact subject-extraction snippet we expect. Kept flexible on
# whitespace but strict on the regex literal — that's the load-bearing bit.
_SUBJECT_EXTRACT = re.compile(
    r"REGEXP_EXTRACT\s*\(\s*[^,]*principalSubject\s*,\s*r'subject/\(\[\^/\]\+\)\$'\s*\)",
    re.IGNORECASE,
)


def test_every_principalemail_read_is_coalesced_with_principalsubject() -> None:
    """Every line that reads `.authenticationInfo.principalEmail` for
    projection (i.e. in a SELECT list, not a WHERE) MUST be inside a
    COALESCE(...) that also considers principalSubject. Otherwise OIDC
    users' rows contribute NULL actor_email and get filtered out by
    downstream WHERE/GROUP BY."""
    src = VIEWS_TMPL.read_text()
    violations = []
    for i, line in enumerate(src.splitlines(), start=1):
        if "authenticationInfo.principalEmail" not in line:
            continue
        # WHERE clauses are handled by a separate test — skip here.
        if re.match(r"\s*WHERE\b", line, re.IGNORECASE):
            continue
        # If the line uses COALESCE + principalSubject, it's compliant.
        stripped = line.strip()
        if "COALESCE" in stripped and "principalSubject" in stripped:
            continue
        # Also allow multi-line COALESCE — check ±3 lines for the pair.
        window = "\n".join(src.splitlines()[max(0, i - 4): i + 3])
        if "COALESCE" in window and "principalSubject" in window and _SUBJECT_EXTRACT.search(window):
            continue
        violations.append(f"line {i}: {stripped[:100]}")
    assert not violations, (
        f"{len(violations)} SELECT-side read(s) of principalEmail not COALESCEd "
        f"with principalSubject:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nOIDC / Workforce Identity Federation users have principalEmail = "
        "NULL but principalSubject = "
        "`principal://iam.googleapis.com/...workforcePools/POOL/subject/SUBJ_ID`.\n"
        "Replace with:\n"
        "  COALESCE(\n"
        "    protopayload_auditlog.authenticationInfo.principalEmail,\n"
        "    REGEXP_EXTRACT(\n"
        "      protopayload_auditlog.authenticationInfo.principalSubject,\n"
        "      r'subject/([^/]+)$'\n"
        "    )\n"
        "  )\n"
        "Verified on responsive-lens-421108: recovers 997/1000 rows, 73 distinct actors."
    )


def test_where_principalemail_filters_use_coalesced_expr() -> None:
    """`WHERE principalEmail IS NOT NULL` filters silently drop OIDC users.
    They must filter on the same COALESCEd expression the SELECT uses —
    or drop the filter entirely if the downstream GROUP BY / JOIN handles
    NULLs correctly."""
    src = VIEWS_TMPL.read_text()
    bad = []
    for i, line in enumerate(src.splitlines(), start=1):
        if re.search(
            r"WHERE\s+protopayload_auditlog\.authenticationInfo\.principalEmail\s+IS\s+NOT\s+NULL",
            line, re.IGNORECASE,
        ):
            bad.append(f"line {i}: {line.strip()[:100]}")
    assert not bad, (
        f"{len(bad)} WHERE clause(s) still filter on raw principalEmail:\n"
        + "\n".join(f"  {v}" for v in bad)
        + "\n\nThese drop OIDC users even if the SELECT expression is fixed. "
        "Replace with `WHERE <coalesced-expression> IS NOT NULL` — or delete "
        "the filter if the aggregation handles NULLs."
    )


def test_offline_simulation_matches_expected_recovery() -> None:
    """Simulate the fix on the 1000-row sample saved from responsive-lens.
    Ensures the specific regex we ship matches the real production shape.

    (Skip if sample file absent — this test is a belt-and-suspenders check
    that runs when we've recently sampled real data.)"""
    import json
    sample_path = Path("/tmp/ge-samples/audit_data_access.json")
    if not sample_path.exists():
        import pytest
        pytest.skip("no sample data at /tmp/ge-samples/audit_data_access.json")
    d = json.loads(sample_path.read_text())
    rows = d.get("rows", [])
    if not rows:
        import pytest
        pytest.skip("sample file empty")
    subj_re = re.compile(r"subject/([^/]+)$")
    recovered = 0
    for r in rows:
        f = r["f"]
        p_email = f[1].get("v")
        p_subj = f[2].get("v")
        if p_email is None and p_subj:
            if subj_re.search(p_subj):
                recovered += 1
    # We saw 997/1000 on responsive-lens sample. Require ≥ 80% recovery
    # of NULL-principalEmail rows to guard the regex from silent drift.
    null_count = sum(1 for r in rows if r["f"][1].get("v") is None)
    if null_count > 0:
        ratio = recovered / null_count
        assert ratio >= 0.80, (
            f"Sample recovery only {recovered}/{null_count} ({ratio:.0%}) — "
            f"regex `subject/([^/]+)$` may not match this tenant's shape. "
            f"Inspect a few rows of /tmp/ge-samples/audit_data_access.json "
            f"and adjust."
        )
