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

"""Adversarial-sweep findings from 2026-07-08 challenge pass.

  #1  apply_views.py::_view_name silently returns "unknown" for CREATE
      FUNCTION statements — cosmetic but confusing when the UDF applies.
  #8  canonical_actor UDF returns '' (empty string) when email='', instead
      of NULL. Downstream WHERE `... IS NOT NULL` filters then let empty
      through — silent data pollution risk. Real audit rows sometimes
      have empty-string principalEmail alongside populated principalSubject.
      NULLIF(email, '') fixes it.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
APPLY_VIEWS = REPO / "infra/contexts/deploy/application/apply_views.py"
VIEWS_TMPL = REPO / "infra/sql_templates/views.sql.tmpl"


def test_apply_views_recognizes_function_statement() -> None:
    """_view_name should return a meaningful name for CREATE FUNCTION
    statements (like `canonical_actor`), not 'unknown'."""
    src = APPLY_VIEWS.read_text()
    m = re.search(r"def _view_name.*?(?=\ndef |\Z)", src, re.DOTALL)
    assert m, "_view_name function not found in apply_views.py"
    body = m.group(0)
    # Regex must match FUNCTION too, not just VIEW. Either:
    #   `CREATE\s+OR\s+REPLACE\s+(?:VIEW|FUNCTION)`  (union)
    # OR two searches (VIEW-first then FUNCTION fallback).
    accepts_function = (
        "VIEW|FUNCTION" in body
        or "FUNCTION|VIEW" in body
        or ("CREATE\\s+OR\\s+REPLACE\\s+FUNCTION" in body)
        or ("FUNCTION" in body and "VIEW" in body)
    )
    assert accepts_function, (
        "_view_name regex only matches CREATE OR REPLACE VIEW — the "
        "canonical_actor UDF gets logged as 'unknown'. Widen the regex "
        "to also match FUNCTION: `(?:VIEW|FUNCTION)`."
    )


def test_canonical_actor_udf_treats_empty_string_as_null() -> None:
    """The UDF's first COALESCE arg is `email`. If a log row has
    principalEmail = '' (empty string, not NULL), COALESCE returns ''
    and downstream filters treat it as a valid actor_email. Silent
    data-pollution risk. Fix: wrap in NULLIF(email, '')."""
    src = VIEWS_TMPL.read_text()
    m = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.canonical_actor`.*?\);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m, "canonical_actor UDF definition not found"
    body = m.group(0)
    # Any shape that treats empty as null is fine:
    #   NULLIF(email, '')
    #   IF(email='', NULL, email)
    #   IF(LENGTH(email) > 0, email, NULL)
    treats_empty = (
        "NULLIF(email" in body.replace(" ", "")
        or "NULLIF(email," in body
        or ("email=''" in body.replace(" ", "") and "NULL" in body.upper())
        or "IF(LENGTH(email)" in body.replace(" ", "")
    )
    assert treats_empty, (
        "canonical_actor UDF doesn't treat empty string as NULL. If a\n"
        "log row has principalEmail = '' (not NULL), the UDF returns\n"
        "'' → downstream `WHERE ... IS NOT NULL` lets it through →\n"
        "polluted actor list with an empty entry.\n"
        "Fix: `COALESCE(NULLIF(email, ''), REGEXP_EXTRACT(subject, ...))`"
    )
