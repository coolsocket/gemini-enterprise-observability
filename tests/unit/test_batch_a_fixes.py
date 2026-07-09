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

"""RED for Batch A (2026-07-09) — 4 items from reporter's list:

  A1 · urllib3 connection pool warning
     "Connection pool is full, discarding connection: bigquery.googleapis.com.
     Connection pool size: 10". Happens whenever user_deep_dive / refresh_now
     fan out >10 concurrent BQ queries (both do). Default pool = 10, we
     regularly saturate → warnings spam + connections churn (perf hit).
     Fix: mount an HTTPAdapter with pool_maxsize=20+ on the BQ client's
     underlying session.

  A2 · Conversations page empty with no explanation
     When user_activity has 0 StreamAssist (P&R Logging off in GE Console),
     v_conversations is empty and the page shows a generic empty state.
     Reporter sees blank page, doesn't know why. Fix: enrich the empty
     state to explain the P&R Logging root cause + link to setup doc.

  A3 · Data Access page has no export
     Frontend DataAccess.tsx has zero references to CSV/Excel/download.
     Fix: add "Download CSV" button that serialises the current table.

  A4 · Some users show "NULL engine" — confusing
     170/175 rows have NULL engine_id in v_data_access_summary (real vivo).
     Not a bug — NULL means calls to services not scoped by an engine
     (admin API, license API, etc). Fix: label these rows as
     "(cross-engine · admin API)" in the UI + tooltip that explains.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_a1_bq_client_configures_larger_pool() -> None:
    """apps/api/shared/infrastructure/bq_client.py MUST configure the
    BQ client's underlying HTTP session with pool_maxsize > default 10.
    Otherwise `Connection pool is full` warnings spam every /api/user
    request (15+ parallel BQ queries) and every /api/refresh (10+ parallel)."""
    src = (REPO / "apps/api/shared/infrastructure/bq_client.py").read_text()
    assert "pool_maxsize" in src or "HTTPAdapter" in src or "PoolManager" in src, (
        "bq_client.py doesn't configure the HTTP connection pool. Default "
        "urllib3 pool_maxsize=10 → user_deep_dive (15 concurrent queries) + "
        "refresh_now (10 concurrent) BOTH saturate → 'Connection pool is full' "
        "warnings + connection churn.\nFix example:\n"
        "  from requests.adapters import HTTPAdapter\n"
        "  adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=3)\n"
        "  bq._http.mount('https://', adapter)"
    )


def test_a2_conversations_page_has_pnr_hint() -> None:
    """Conversations.tsx empty state MUST mention P&R Logging (the upstream
    cause of empty v_conversations) + link to the setup doc — otherwise
    operators see a blank page and don't know how to unblock themselves."""
    src = (REPO / "apps/web/src/pages/Conversations.tsx").read_text()
    has_pnr_ref = (
        "P&R" in src or "Prompt & Response" in src or "Prompt Logging" in src
        or "sensitiveLogging" in src or "GE_CONSOLE_SETUP" in src
    )
    assert has_pnr_ref, (
        "Conversations.tsx empty state doesn't mention Prompt & Response "
        "Logging (the upstream toggle in GE Console that gates whether "
        "chat prompts land in BigQuery at all). When empty, users see "
        "a blank page and don't know it's a Console-side config gap. "
        "Enrich the EmptyState hint with a message + link to "
        "docs/GE_CONSOLE_SETUP.md."
    )


def test_a3_data_access_page_has_export_button() -> None:
    """DataAccess.tsx MUST have a Download CSV button — reporter's ask."""
    src = (REPO / "apps/web/src/pages/DataAccess.tsx").read_text()
    has_download = (
        re.search(r"download\s*=", src, re.IGNORECASE)   # <a download=...>
        or re.search(r"Download\s+CSV", src)
        or "toCSV" in src or "downloadCSV" in src or "exportCSV" in src
    )
    assert has_download, (
        "DataAccess.tsx has no CSV/Excel download button. Add one that "
        "serialises the current table rows to CSV. Standard pattern: "
        "`<a href={dataUri} download=\"data-access.csv\">Download CSV</a>` "
        "where dataUri = URL.createObjectURL(new Blob([csvString], "
        "{type:'text/csv'})) or a plain `data:text/csv;charset=utf-8,` URI."
    )


def test_a4_null_engine_has_explanatory_label() -> None:
    """Rows in per-engine breakdown with engine_id=NULL should NOT display
    as blank / "—" only. They represent cross-engine admin/license API calls.
    UI should label them so operators aren't confused."""
    tsx = (REPO / "apps/web/src/pages/UserDeepDive.tsx").read_text()
    # Look for the per-engine breakdown handling — must have specific text
    # explaining what NULL engine means, not just a fallback dash.
    has_label = (
        "cross-engine" in tsx.lower()
        or "admin api" in tsx.lower()
        or "无 engine" in tsx or "跨 engine" in tsx
        or "no engine context" in tsx.lower()
    )
    assert has_label, (
        "UserDeepDive.tsx renders NULL engine rows without explaining what "
        "they are. Reporter's confusion: 'why is this user not in an "
        "engine?' Answer: those are calls to admin/license/cross-engine "
        "APIs. Label the NULL-engine row with something like "
        "'(cross-engine · admin API)' + a tooltip."
    )
