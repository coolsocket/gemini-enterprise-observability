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

"""Issue #2 item 2 — snapshot_refresh.sql.tftpl drift.

Reporter noticed the scheduled query references `v_session_files` and
`v_agent_usage`, neither of which are defined in views.sql.tmpl. First
scheduled refresh fails with:

  Table `<project>.<dataset>.v_session_files` was not found in location …

The two sides drift silently because they live in different files. Lock
them together with a static test: every `v_*` referenced in the tftpl
MUST have a `CREATE OR REPLACE VIEW` in views.sql.tmpl.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
VIEWS_TMPL = ROOT / "infra/sql_templates/views.sql.tmpl"
REFRESH_TFTPL = ROOT / "terraform/snapshot_refresh.sql.tftpl"


def _defined_views() -> set[str]:
    text = VIEWS_TMPL.read_text()
    return set(re.findall(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+`\{\{PROJECT\}\}\.\{\{DATASET\}\}\.(v_[a-z_]+)`",
        text,
        re.IGNORECASE,
    ))


def _referenced_views() -> set[str]:
    text = REFRESH_TFTPL.read_text()
    # Every FROM clause in the tftpl selects from a v_*.
    return set(re.findall(r"FROM\s+`\$\{project\}\.\$\{dataset\}\.(v_[a-z_]+)`", text))


def test_every_referenced_view_is_defined() -> None:
    defined = _defined_views()
    referenced = _referenced_views()
    missing = referenced - defined
    assert not missing, (
        f"terraform/snapshot_refresh.sql.tftpl references view(s) not defined "
        f"in infra/sql_templates/views.sql.tmpl: {sorted(missing)}. "
        f"First scheduled refresh will fail with 'Table … was not found'. "
        f"Either (a) add the view definitions to views.sql.tmpl, or "
        f"(b) remove the FROM/CREATE lines from snapshot_refresh.sql.tftpl."
    )
