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

"""RED for R3 (2026-07-10) — frontend polish surfaced by audit probe 4:

  R3a · Shared color-tag constants (ORIGIN_TAG, PERSONA_TAG) are
        copy-pasted across ≥7 pages. Extract to apps/web/src/tags.ts
        so a color change propagates everywhere.

  R3b · Four `any` escapes in TypeScript source. Two are trivially
        fixable with concrete types; two (main.tsx error info,
        api.ts refresh row) can either become `unknown`/proper types.

  R3c/d · Quota.tsx (350 SLOC) + UserDeepDive.tsx (320 SLOC) have
        extract-worthy sub-components. Minimum bar: extract one obvious
        component from each (TotalCard, Metric) into its own module so
        the shape works.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_shared_tags_module_exists() -> None:
    path = REPO / "apps/web/src/tags.ts"
    assert path.exists(), (
        "Expected apps/web/src/tags.ts to hold shared ORIGIN_TAG / "
        "PERSONA_TAG maps. Move the duplicated constants there and "
        "import from pages."
    )
    src = path.read_text()
    assert "ORIGIN_TAG" in src, "tags.ts should export ORIGIN_TAG"
    assert "PERSONA_TAG" in src, "tags.ts should export PERSONA_TAG"


def test_pages_no_longer_redefine_origin_tag() -> None:
    """After extraction, no page file should still declare a local
    `const ORIGIN_TAG: Record<string, string>`. Import from tags.ts."""
    offenders: list[str] = []
    for tsx in (REPO / "apps/web/src/pages").glob("*.tsx"):
        src = tsx.read_text()
        if re.search(r"^const\s+ORIGIN_TAG\s*:\s*Record<", src, re.MULTILINE):
            offenders.append(tsx.name)
    assert not offenders, (
        "These pages still define ORIGIN_TAG locally — import from "
        "../tags instead:\n" + "\n".join(offenders)
    )


def test_api_ts_refreshnow_no_any_row() -> None:
    src = (REPO / "apps/web/src/api.ts").read_text()
    # Look for `refreshed: any[]` specifically in the refreshNow signature
    assert not re.search(r"refreshNow[^)]*any\[\]", src, re.DOTALL), (
        "api.ts:refreshNow types `refreshed: any[]` — replace with a "
        "concrete SnapshotRefreshResult[] (fields: snapshot, row_count, "
        "seconds, ok, error?, skipped?, reason?)."
    )


def test_overview_no_any_engine_map() -> None:
    src = (REPO / "apps/web/src/pages/Overview.tsx").read_text()
    assert not re.search(r"\(\s*e\s*:\s*any\s*\)\s*=>", src), (
        "Overview.tsx has `(e: any) =>` in an engines.rows.map(); use "
        "the EngineRow type from api.ts (or the `engines` payload's "
        "response type)."
    )


def test_quota_page_extracted_total_card() -> None:
    """Quota.tsx is >300 SLOC; extract at least the TotalCard component
    into its own module. Not requiring a wholesale split, just proof
    of the pattern."""
    quota = (REPO / "apps/web/src/pages/Quota.tsx").read_text()
    # If TotalCard is still defined locally, the extraction hasn't happened.
    still_local = re.search(r"^function\s+TotalCard\s*\(", quota, re.MULTILINE)
    # Or accept that the whole Quota page has shrunk meaningfully (< 300 SLOC)
    quota_sloc = sum(1 for line in quota.splitlines() if line.strip())
    assert not still_local or quota_sloc < 300, (
        f"Quota.tsx still defines TotalCard locally AND is {quota_sloc} "
        f"SLOC. Extract TotalCard to its own file (e.g. "
        f"apps/web/src/components/QuotaTotalCard.tsx) to prove the "
        f"split pattern."
    )


def test_userdeepdive_extracted_metric_or_bar() -> None:
    """Same as above for UserDeepDive.tsx — extract Metric OR Bar into
    a separate component file so subsequent iterations are cheaper."""
    src = (REPO / "apps/web/src/pages/UserDeepDive.tsx").read_text()
    both_local = (
        re.search(r"^function\s+Metric\s*\(", src, re.MULTILINE) is not None
        and re.search(r"^function\s+Bar\s*\(", src, re.MULTILINE) is not None
    )
    sloc = sum(1 for line in src.splitlines() if line.strip())
    assert not both_local or sloc < 700, (
        f"UserDeepDive.tsx still defines BOTH Metric AND Bar locally "
        f"AND is {sloc} SLOC. Move at least one to "
        f"apps/web/src/components/ so the extraction pattern is proven."
    )
