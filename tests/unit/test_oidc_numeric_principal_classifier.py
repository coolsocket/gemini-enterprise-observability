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

"""RED regression for OIDC numeric principals (issue reported 2026-07-07).

Reporter's `jsonPayload.useriamprincipal` values are bare numeric strings
like "11135014" — no `@`, no `principal://` prefix, no domain. This is
the OIDC subject claim raw, common when GE is fronted by Workforce
Identity Federation with a custom attribute mapping.

Current origin CASE in views.sql.tmpl has ONLY these WHEN clauses:
  {{SIM_PATTERN}}       → SIMULATED
  %gserviceaccount.com  → AUTOMATION
  principal://%         → HUMAN
  %@%                   → HUMAN
  IS NULL / ''          → UNKNOWN
  ELSE                  → inconsistent (sometimes HUMAN, sometimes UNKNOWN)

None of these match "11135014". In 9 of 11 CASE blocks the ELSE is
'UNKNOWN', so OIDC users vanish from /api/summary?origin=HUMAN, seat
counts, and every human-filtered chart.

Fix: add `WHEN REGEXP_CONTAINS(actor_email, r'^[0-9]+$') THEN 'HUMAN'`
to every origin CASE. Standardize ELSE to 'UNKNOWN' at the same time
so a future unrecognized shape doesn't silently pass as HUMAN.
"""
from pathlib import Path
import re

VIEWS = Path(__file__).resolve().parents[2] / "infra/sql_templates/views.sql.tmpl"


def _origin_case_blocks(text: str) -> list[str]:
    """Every CASE ... END AS origin block (there are 11 today, inline).

    Naive non-greedy `CASE.*?END AS origin` swallows intermediate persona /
    other CASE blocks. Instead: find each `END AS origin` and walk back
    to the nearest preceding `CASE` on its own indented line."""
    blocks = []
    for m in re.finditer(r"\bEND\s+AS\s+origin\b", text, re.IGNORECASE):
        end = m.end()
        # Look back for the closest preceding "CASE\n" — CASE on its own line
        # (with only whitespace before), since inline CASE inside SELECT lists
        # would be a different pattern.
        prefix = text[:end]
        starts = [i.start() for i in re.finditer(r"(?m)^\s*CASE\s*$", prefix)]
        if not starts:
            continue
        blocks.append(text[starts[-1]:end])
    return blocks


def test_at_least_one_origin_case_block_exists() -> None:
    """Sanity: the regex actually finds the CASE blocks. Test infrastructure
    check — if this fails, later assertions are silently vacuous."""
    blocks = _origin_case_blocks(VIEWS.read_text())
    assert len(blocks) >= 5, (
        f"Expected several origin CASE blocks in views.sql.tmpl, found "
        f"{len(blocks)}. Regex broken — later assertions are meaningless."
    )


def test_every_origin_case_recognizes_numeric_oidc_subject() -> None:
    """Every origin CASE MUST classify pure numeric principals (OIDC subject
    IDs like '11135014') as HUMAN. Otherwise reporter's tenant renders all
    real users as UNKNOWN in the dashboard."""
    blocks = _origin_case_blocks(VIEWS.read_text())
    missing = []
    for i, block in enumerate(blocks):
        # Two markers must co-exist in the SAME WHEN clause: REGEXP_CONTAINS
        # (any first arg — may itself contain commas/parens for REGEXP_REPLACE
        # wrappers) AND the numeric anchor `r'^[0-9]+$'` or `r'^\d+$'`, both
        # followed eventually by `THEN 'HUMAN'`.
        has_numeric_rule = any(
            "REGEXP_CONTAINS" in line
            and re.search(r"r'\^(\[0-9\]\+|\\d\+)\$'", line)
            and "THEN 'HUMAN'" in line
            for line in block.splitlines()
        )
        if not has_numeric_rule:
            first_line = block.splitlines()[0].strip()
            missing.append(f"block #{i}: {first_line[:80]}")
    assert not missing, (
        f"{len(missing)} origin CASE block(s) missing the OIDC-numeric rule:\n"
        + "\n".join(f"  {m}" for m in missing)
        + "\nAdd `WHEN REGEXP_CONTAINS(<actor_email_expr>, r'^[0-9]+$') THEN 'HUMAN' "
        "  -- OIDC subject ID (numeric)` to every CASE.\n"
        "  Reporter's tenant uses OIDC — principals are bare '11135014' etc.\n"
        "  Without this rule they classify as UNKNOWN and vanish from human-"
        "filtered aggregates."
    )


def test_origin_case_else_branches_consistent() -> None:
    """While we're touching every CASE, unify the ELSE branch to 'UNKNOWN'
    so future unrecognized shapes are visible (not silently pass as HUMAN)."""
    blocks = _origin_case_blocks(VIEWS.read_text())
    else_variants: dict[str, int] = {}
    for block in blocks:
        m = re.search(r"ELSE\s+'([A-Z_]+)'", block)
        if m:
            else_variants[m.group(1)] = else_variants.get(m.group(1), 0) + 1
    assert set(else_variants.keys()) <= {"UNKNOWN"}, (
        f"origin CASE ELSE branches are inconsistent across views: "
        f"{else_variants}. Standardize to `ELSE 'UNKNOWN'` so a new "
        f"unrecognized principal shape is visible in the dashboard "
        f"(instead of being silently promoted to HUMAN and skewing "
        f"seat counts)."
    )
