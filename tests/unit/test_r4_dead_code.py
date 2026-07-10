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

"""RED for R4 (2026-07-10) — dead-code cleanup surfaced by audit probe 3.

Removals:
  R4a · `apps/api/shared/infrastructure/bq_client.py::table()` — 5-line
        helper generating `project.dataset.name`. Zero grep hits outside
        its own file.
  R4b · Three unused TS types in `apps/web/src/api.ts`:
          - AgentUsageRow  (backend endpoint was retired 2026-07-07)
          - ConversationRow (superseded by ConversationWithResponseRow)
          - ChoiceRow  (superseded by ChoicesAggRow / not exposed on api)
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_bq_client_table_helper_removed() -> None:
    src = (REPO / "apps/api/shared/infrastructure/bq_client.py").read_text()
    assert not re.search(r"^def\s+table\s*\(", src, re.MULTILINE), (
        "Dead helper `def table(name)` in bq_client.py should be removed. "
        "Zero grep hits outside its own file — never called by any route."
    )


def test_api_ts_no_unused_row_types() -> None:
    src = (REPO / "apps/web/src/api.ts").read_text()
    for name in ("AgentUsageRow", "ConversationRow", "ChoiceRow"):
        assert f"export type {name}" not in src, (
            f"Unused TypeScript type export `{name}` should be removed from "
            f"apps/web/src/api.ts. Grep across apps/web/src turned up zero "
            f"consumers. Historical types can be recovered from git if "
            f"session_files views come back one day."
        )
