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

"""RED for the 2 remaining polish items (2026-07-08):

  M2 — User DETAIL page (not just picker) must render `identity.kind`
       + `identity.display` from the /api/user/{email} response.
       Backend already returns this; frontend detail-header renders
       persona badge but not IdP badge → operator can't see "who this
       user really is at IdP level" without reading URLs.

  M3 — BQ UDF `canonical_actor(email, subject)` centralizes the
       COALESCE + REGEXP_EXTRACT logic that currently lives inline in
       7 places across views.sql.tmpl. Views then call the UDF;
       Python IdentityResolver keeps its own copy for its callers but
       both layers derive actor_id from the same string form.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
USER_DEEP_DIVE_TSX = REPO / "apps/web/src/pages/UserDeepDive.tsx"
VIEWS_TMPL = REPO / "infra/sql_templates/views.sql.tmpl"


# ============================================================
# M2 · detail page badge
# ============================================================

def test_detail_page_renders_identity_from_backend() -> None:
    """UserDeepDive detail (the function that renders `d.persona[0]` etc)
    must render `d.identity.kind` or `d.identity.display` somewhere —
    the backend field is otherwise silently dropped in the detail view.
    Picker badge exists (commit f9015b1), detail page badge doesn't."""
    src = USER_DEEP_DIVE_TSX.read_text()
    # We need a JSX reference to identity_kind/identity.kind/d.identity.
    # A `.identity_kind` in a TypeScript type isn't proof of rendering;
    # look for JSX-level access: d.identity or persona.identity.
    detail_area = src[src.find("function") if "function UserDeepDive" not in src else src.find("function UserDeepDive"):]
    # Fallback: whole file.
    if "identity.kind" not in src and "identity.display" not in src and "d.identity" not in src:
        assert False, (
            "UserDeepDive.tsx never accesses `d.identity` / `identity.kind` "
            "/ `identity.display`. Backend returns the object at "
            "/api/user/{email} response's `.identity` key (verified live: "
            "kind='oidc_wif_generic', display='11126728 (vivo-gemini-enterprise)'). "
            "Frontend detail header should render it as a badge near the "
            "persona chip — otherwise operator can't tell IdP vendor without "
            "hovering the picker."
        )


def test_userdeepdive_ts_type_has_identity() -> None:
    """The `UserDeepDive` TS type in api.ts must declare `identity` so TS
    doesn't strip it at compile time."""
    api_ts = (REPO / "apps/web/src/api.ts").read_text()
    m = re.search(r"export\s+type\s+UserDeepDive\s*=\s*\{.*?^\};", api_ts,
                  re.DOTALL | re.MULTILINE)
    assert m, "UserDeepDive type block not found in api.ts"
    body = m.group(0)
    assert "identity" in body, (
        "UserDeepDive TS type doesn't declare `identity`. Backend sends "
        "an `identity: {kind, actor_id, display, is_human}` object — TS "
        "will drop it silently. Add:\n"
        "  identity: { kind: IdentityKind; actor_id: string; display: string; is_human: boolean; };"
    )


# ============================================================
# M3 · BQ UDF for identity canonicalization
# ============================================================

def test_views_sql_defines_canonical_actor_udf() -> None:
    """views.sql.tmpl must define (or import) a persistent function that
    canonicalizes (email, subject) → actor_id, so the 7 inline COALESCE
    sites can be replaced with a single function call."""
    src = VIEWS_TMPL.read_text()
    has_udf_def = (
        re.search(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.canonical_actor`",
                  src, re.IGNORECASE) is not None
        or re.search(r"CREATE\s+FUNCTION\s+IF\s+NOT\s+EXISTS\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.canonical_actor`",
                     src, re.IGNORECASE) is not None
    )
    assert has_udf_def, (
        "views.sql.tmpl doesn't define a `canonical_actor` UDF. Add:\n"
        "  CREATE OR REPLACE FUNCTION `{{PROJECT}}.{{DATASET}}.canonical_actor`\n"
        "    (email STRING, subject STRING) AS (\n"
        "      COALESCE(\n"
        "        email,\n"
        "        REGEXP_EXTRACT(subject, r'subject/([^/]+)$')\n"
        "      )\n"
        "    );\n"
        "Then replace inline COALESCE sites with `canonical_actor(email, subject)` calls."
    )


def test_audit_views_use_canonical_actor_udf() -> None:
    """The 5 SELECT sites that used to inline
    `COALESCE(principalEmail, REGEXP_EXTRACT(principalSubject, r'subject/([^/]+)$'))`
    should now call the UDF — deduplicated logic + easier to test."""
    src = VIEWS_TMPL.read_text()
    # `canonical_actor` may be qualified with backticks and dataset path:
    # `{{PROJECT}}.{{DATASET}}.canonical_actor\`(email, subject).
    # Count total occurrences of the name; UDF def contributes 1, call
    # sites contribute the rest. Expect ≥ 6 = def + 5 SELECT invocations.
    total = len(re.findall(r"canonical_actor", src, re.IGNORECASE))
    assert total >= 6, (
        f"canonical_actor referenced only {total}x (need ≥6: 1 UDF def + "
        f"5 SELECT invocations across v_admin_activity, v_data_access, "
        f"v_deep_research_prompts, v_custom_agent_prompts, and their "
        f"WHERE clauses). Replace remaining inline COALESCE with UDF calls."
    )
