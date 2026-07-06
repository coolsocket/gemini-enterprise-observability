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

"""RED test for cross-project sink-table schema drift.

Reported failure (user, responsive-lens-421108, 2026-07-06):

  applied 14/21 views

  ❌ 4 view(s) failed with unexpected errors:
    • v_conversations: Cannot access field parts on a value with type STRING
    • v_agentspace_navigation: Field name agentinfo does not exist in
                                STRUCT<agentspacepagetype STRING>
    • v_agentspace_navigation_summary: (same)
    • v_custom_agent_prompts:         (same)

Root cause: BigQuery auto-generates each sink-target table's schema from the
first matching log entry that lands. If that first entry had a minimal
payload (query as a plain string, or agentspaceinfo with only
agentspacepagetype), the resulting schema is a STRICT SUBSET of what our
views assume. Later richer log entries land, but the schema is already
locked, so richer fields become inaccessible (STRING) or absent entirely.

Fix pattern: wrap the ambiguous chain in TO_JSON_STRING(...) at the outer
level and navigate via JSON_VALUE, which is schema-agnostic — works whether
the sub-field is STRUCT, STRING (JSON-encoded), or absent.

These tests fail RED before the fix (they detect the bare .parts / .agentinfo
chains) and pass GREEN after the SQL is rewritten to use JSON_VALUE wrappers.
"""
from pathlib import Path
import re

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "infra/sql_templates/views.sql.tmpl"


@pytest.fixture(scope="module")
def views_sql() -> str:
    """The raw view template — placeholders unresolved, which is fine for
    schema-drift checks: we're grepping for unsafe patterns, not executing."""
    return TEMPLATE.read_text()


def _lines_matching(sql: str, pattern: str) -> list[tuple[int, str]]:
    """Return (line_no, line_text) for each source line matching `pattern`."""
    rx = re.compile(pattern)
    hits = []
    for i, line in enumerate(sql.splitlines(), start=1):
        if rx.search(line):
            hits.append((i, line.strip()))
    return hits


# -------------------------------------------------------------------
# Bug 1: unguarded access to .query.parts (fails when query is STRING)
# -------------------------------------------------------------------
def test_no_unguarded_query_parts_access(views_sql: str) -> None:
    """v_conversations et al. must NOT access `.query.parts` directly on
    jsonPayload.request; use JSON_VALUE(TO_JSON_STRING(jsonPayload), '$....')
    or an equivalent schema-agnostic pattern instead.

    RED before fix: matches the `UNNEST(jsonPayload.request.query.parts)`
    line in v_conversations base CTE. GREEN after: no matches — the SQL
    wraps via JSON.
    """
    hits = _lines_matching(
        views_sql,
        r"UNNEST\s*\(\s*jsonPayload\.request\.query\.parts\s*\)"
        r"|jsonPayload\.request\.query\.parts\[",
    )
    assert not hits, (
        f"Found {len(hits)} unguarded `jsonPayload.request.query.parts` access(es):\n"
        + "\n".join(f"  line {ln}: {txt}" for ln, txt in hits)
        + "\nThese fail with 'Cannot access field parts on a value with type STRING' "
        "when the sink target table's schema was inferred from a log entry where "
        "`query` arrived as a plain string. Wrap via "
        "JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.request.query.parts[0].text') "
        "or similar."
    )


# -------------------------------------------------------------------
# Bug 2: unguarded access to agentspaceinfo.agentinfo.*
# -------------------------------------------------------------------
def test_no_unguarded_agentinfo_access(views_sql: str) -> None:
    """v_agentspace_navigation, v_agentspace_navigation_summary,
    v_custom_agent_prompts must NOT access
    `.userevent.agentspaceinfo.agentinfo.*` directly on jsonPayload.request;
    if the sink table's schema was inferred from a log entry that only had
    `agentspacepagetype` under agentspaceinfo, the whole SELECT fails at
    plan time with 'Field name agentinfo does not exist in
    STRUCT<agentspacepagetype STRING>'.

    RED before fix: matches the direct chain access. GREEN after: no matches.
    """
    hits = _lines_matching(
        views_sql,
        r"jsonPayload\.request\.userevent\.agentspaceinfo\.agentinfo\.",
    )
    assert not hits, (
        f"Found {len(hits)} unguarded agentspaceinfo.agentinfo access(es):\n"
        + "\n".join(f"  line {ln}: {txt}" for ln, txt in hits)
        + "\nThese fail when the sink target table's schema doesn't include "
        "the agentinfo sub-struct. Wrap via "
        "JSON_VALUE(TO_JSON_STRING(jsonPayload), "
        "'$.request.userevent.agentspaceinfo.agentinfo.agentid') "
        "or similar so the missing field returns NULL instead of a plan error."
    )


# -------------------------------------------------------------------
# Regression guard: verify JSON_VALUE + TO_JSON_STRING pattern is used
# for the SAME concept the buggy access was reaching for.
# -------------------------------------------------------------------
def test_json_wrapper_pattern_present_for_query_parts(views_sql: str) -> None:
    """Confirm the intended replacement is actually there. Prevents a
    'fix' that simply deletes the field access without providing a substitute
    (which would silently zero out prompt content everywhere)."""
    # Look for a JSON path literal navigating request.query.parts — the
    # canonical replacement pattern is
    # JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.request.query.parts[0].text').
    has_wrapper = re.search(r"'\$\.request\.query\.parts\[", views_sql)
    assert has_wrapper, (
        "Expected at least one JSON path literal '$.request.query.parts[...]' "
        "in the views template — otherwise the prompt column is silently "
        "empty on projects where `query` is a STRING schema."
    )


def test_json_wrapper_pattern_present_for_agentinfo(views_sql: str) -> None:
    """Same regression guard, for the agentspaceinfo/agentinfo chain."""
    has_wrapper = re.search(
        r"'\$\.request\.userevent\.agentspaceinfo\.agentinfo\.",
        views_sql,
    )
    assert has_wrapper, (
        "Expected at least one JSON path literal "
        "'$.request.userevent.agentspaceinfo.agentinfo.*' in the views "
        "template — otherwise custom-agent nav events disappear on projects "
        "where agentspaceinfo has no agentinfo sub-struct."
    )
