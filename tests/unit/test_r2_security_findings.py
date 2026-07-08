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

"""R2 challenge findings (2026-07-08) — security / injection.

Real finding: /api/quota/config POST directly interpolates user-controlled
`key`, `value`, `by` into a MERGE SQL. Frontend calls this every time an
admin edits a limit → attacker with dashboard access can pass a payload
that escapes the string and mutates other config keys / drops the table.
The prefix guard (key.startswith("tier.")) doesn't help — `key="tier.
foo'; DROP TABLE ..."` still passes startswith.

Also flagged: _fetch_and_persist_license_configs._merge inlines `k` from
external GE license API into SQL. Google service so low practical risk,
but defensive param binding is worth 5 lines.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
QUOTA_ROUTES = REPO / "apps/api/routes/quota.py"
REFRESH_ROUTES = REPO / "apps/api/routes/refresh.py"


def test_quota_config_set_uses_parameters_not_fstring() -> None:
    """The /api/quota/config POST endpoint receives (key, value, by) from
    the frontend and MUST send them as bigquery.ScalarQueryParameter,
    not embed via f-string. Otherwise: `value=x'; DROP TABLE ...` fires."""
    src = QUOTA_ROUTES.read_text()
    m = re.search(
        r"def quota_config_set.*?(?=\n@router|\ndef |\Z)", src, re.DOTALL,
    )
    assert m, "quota_config_set function not found in routes/quota.py"
    body = m.group(0)
    # Real fix: query_parameters + @key / @value / @by placeholders.
    has_params = "query_parameters" in body and "ScalarQueryParameter" in body
    assert has_params, (
        "quota_config_set doesn't use ScalarQueryParameter for its inputs. "
        "`key`, `value`, `by` all flow from frontend POST → SQL via f-string "
        "interpolation. Payload like `value=x'; DROP TABLE ...` escapes.\n"
        "Fix: swap the MERGE to use @key / @value / @by placeholders + "
        "`job_config=bigquery.QueryJobConfig(query_parameters=[...])`."
    )


def test_license_merge_uses_parameters_not_fstring() -> None:
    """`_fetch_and_persist_license_configs` calls `_merge(k, v)` which
    embeds `k` via f-string. `k` comes from GE license API response —
    Google-owned so practical risk is low, but defensive param binding
    is the same 5 lines and closes the class of bug."""
    src = REFRESH_ROUTES.read_text()
    m = re.search(r"def _merge.*?\)\.result\(\)", src, re.DOTALL)
    assert m, "_merge helper not found in routes/refresh.py"
    body = m.group(0)
    # Currently: `USING (SELECT '{k}' k, @v v)` — k inlined, v parameterized.
    # Both should be parameters.
    has_k_inlined = "'{k}'" in body or "'{key}'" in body
    assert not has_k_inlined, (
        "_merge helper inlines the key into SQL via f-string ('{k}' k, ...). "
        "Even for internal Google-service inputs, prefer defensive "
        "parameterisation:\n"
        "  USING (SELECT @k k, @v v)\n"
        "with a second ScalarQueryParameter('k', 'STRING', k)."
    )
