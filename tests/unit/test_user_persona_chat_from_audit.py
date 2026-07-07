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

"""RED regression: v_user_persona chat metric ignores Path 3 (audit).

Verified on the ge_demo_readonly mirror of responsive-lens-421108
(2026-07-07):
  actor=11126728 has chat_turns=18 + deep_research=9 in v_data_access_
  summary (Path 3 audit), but v_user_persona.chat_turns_total = 0,
  persona = LURKER.

Root cause: v_user_persona's `chat` CTE selects chat_turns from
v_user_usage, which counts StreamAssist events from Path 2
(user_activity). Path 2 is only populated when the engine's
"Prompt & Response Logging" toggle is ON in GE Admin Console.
Tenants using OIDC/WIF without P&R logging have Path 2 empty for
chat — all their real chat activity lives in Path 3 audit logs.

Fix: v_user_persona MUST also count chat activity from Path 3. The
simplest way is to reference v_data_access_summary (which already
aggregates chat_turns per actor from audit) in the persona
computation, GREATEST-ing across both paths so we don't undercount
when P&R is on AND we still see activity when P&R is off.
"""
from pathlib import Path
import re

VIEWS = Path(__file__).resolve().parents[2] / "infra/sql_templates/views.sql.tmpl"


def _v_user_persona_block() -> str:
    """Return the v_user_persona view definition as text — from
    `CREATE OR REPLACE VIEW ...v_user_persona` to the next
    `CREATE OR REPLACE VIEW` (or EOF)."""
    src = VIEWS.read_text()
    m = re.search(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.v_user_persona`"
        r".*?(?=CREATE\s+OR\s+REPLACE\s+VIEW\b|\Z)",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m, "could not find v_user_persona definition in views.sql.tmpl"
    return m.group(0)


def test_v_user_persona_references_audit_chat_source() -> None:
    """v_user_persona MUST reference v_data_access_summary (Path 3 chat
    counts) INSIDE THE CHAT COMPUTATION. The `actors` CTE already unions
    from v_data_access, but that only supplies the row set — the actual
    chat_turns numeric aggregation still comes from v_user_usage (Path 2).

    Accept either shape:
      (a) a dedicated `audit_chat` CTE that selects chat_turns from Path 3
      (b) the `chat` CTE itself SELECTs FROM v_data_access[_summary]"""
    body = _v_user_persona_block()

    # Extract every CTE body except `actors` (which is just the row-set union).
    # A CTE is `name AS (...)`. Simple recursive-paren match is easiest.
    def _cte_bodies(text: str) -> dict[str, str]:
        out = {}
        for m in re.finditer(r"(\w+)\s+AS\s+\(", text):
            name = m.group(1)
            if name.lower() in {"actors"}:
                continue
            # Find matching close paren by depth
            start = m.end()
            depth = 1
            i = start
            while i < len(text) and depth:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            out[name] = text[start:i - 1]
        return out

    ctes = _cte_bodies(body)
    audit_used_in_chat_ctx = False
    hit_names = []
    for name, cbody in ctes.items():
        if "v_data_access_summary" in cbody or "v_data_access`" in cbody:
            hit_names.append(name)
            audit_used_in_chat_ctx = True
    assert audit_used_in_chat_ctx, (
        "v_user_persona view has no reference to v_data_access_summary "
        "(or v_data_access). It computes chat_turns only from v_user_usage → "
        "Path 2, which is empty for OIDC tenants without Prompt & Response "
        "Logging enabled. Add an `audit_chat` CTE that reads chat_turns from "
        "v_data_access_summary and GREATEST-merges with the Path 2 chat CTE.\n"
        "\nVerified on responsive-lens-421108 mirror: actor 11126728 has\n"
        "  v_data_access_summary.chat_turns = 18   (Path 3, real)\n"
        "  v_user_persona.chat_turns_total  =  0   (Path 2 only, bug)\n"
        "→ classified as LURKER instead of ACTIVE_CONSUMER."
    )


def test_v_user_persona_uses_greatest_or_coalesce_across_paths() -> None:
    """When v_user_persona references both v_user_usage (Path 2) and
    v_data_access_summary (Path 3), the merge MUST be GREATEST (or
    equivalent) — NOT SUM — because both paths log the SAME StreamAssist
    events when both are on. SUM would double-count."""
    body = _v_user_persona_block()
    if "v_data_access_summary" not in body and "v_data_access`" not in body:
        # The other test already flags this — skip here to give one clear
        # failure instead of two.
        import pytest
        pytest.skip("audit source not referenced yet (see other test)")
    # Look for merge shape near the chat computation.
    has_merge = (
        "GREATEST" in body
        or "IFNULL" in body and "FULL OUTER JOIN" in body
        # A COALESCE(a.chat_turns, b.chat_turns) shape would only use the
        # first non-null → could work if Path 2 = 0 vs NULL is careful,
        # but GREATEST is the honest merge — enforce it.
    )
    assert has_merge, (
        "v_user_persona references audit source but doesn't seem to merge "
        "with GREATEST / FULL OUTER JOIN — check for double-counting when "
        "both Path 2 and Path 3 log the same StreamAssist events."
    )
