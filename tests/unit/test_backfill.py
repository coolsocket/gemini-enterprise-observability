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

"""RED tests for `make backfill` (2026-07-09).

Backfill pulls historical Cloud Logging entries into the existing sink
target tables, so first-time operators see history (up to what
`_Default` bucket retains), not just from sink-creation onwards.

Non-negotiable guarantees:
  - **不重 (no dup)**: MERGE INTO sink_target USING stage ON insertId.
    Cloud Logging assigns a globally unique insertId per entry;
    both API responses and BQ sink rows expose it.
  - **不漏 (no gap)**: overlap window = [NOW - DAYS, MIN(sink_ts) + 1h].
    The +1h tail deliberately overlaps sink coverage; MERGE dedupes.
  - **filter 一致**: backfill's Cloud Logging filter MUST match the
    terraform sink filter bytewise (after variable substitution).
    Otherwise we backfill logs sink wouldn't have kept, or miss
    logs sink DOES keep.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
TF_MAIN = REPO / "terraform/main.tf"
BACKFILL = REPO / "infra/contexts/deploy/application/backfill.py"
MAKEFILE = REPO / "Makefile"


def _extract_terraform_sink_filter(tf_src: str) -> str:
    """Extract the filter string from terraform's google_logging_project_sink
    resource. Normalises variable references ${var.project_id} → __PROJECT__
    and collapses whitespace so downstream comparison is robust."""
    m = re.search(
        r"google_logging_project_sink[^{]*\{.*?filter\s*=\s*<<-?EOT(.*?)EOT",
        tf_src, re.DOTALL,
    )
    if not m:
        return ""
    raw = m.group(1)
    # Normalise: strip leading/trailing whitespace per line, collapse blank
    # lines, replace ${var.project_id} sentinel with __PROJECT__ token.
    normalised = re.sub(r"\$\{var\.project_id\}", "__PROJECT__", raw)
    normalised = re.sub(r"\s+", " ", normalised).strip()
    return normalised


def _extract_backfill_filter(py_src: str) -> str:
    """The Python module MUST expose the filter as a module-level constant
    named `SINK_FILTER_TEMPLATE` (or similar) with `{project_id}` placeholder.
    Extract + normalise the same way for comparison."""
    # Accept common Python patterns: SINK_FILTER_TEMPLATE = "..." or triple-quoted
    m = re.search(
        r"SINK_FILTER_TEMPLATE\s*=\s*(?:\"\"\"|''')(.*?)(?:\"\"\"|''')",
        py_src, re.DOTALL,
    )
    if not m:
        m = re.search(r'SINK_FILTER_TEMPLATE\s*=\s*"([^"]+)"', py_src)
    if not m:
        return ""
    raw = m.group(1)
    normalised = re.sub(r"\{project_id\}", "__PROJECT__", raw)
    normalised = re.sub(r"\s+", " ", normalised).strip()
    return normalised


def test_backfill_module_exists() -> None:
    assert BACKFILL.exists(), (
        f"{BACKFILL.relative_to(REPO)} does not exist yet — this is the "
        "backfill implementation entry point. Create it with a "
        "`SINK_FILTER_TEMPLATE` constant + a main() that reads Cloud Logging."
    )


def test_backfill_filter_matches_terraform_sink() -> None:
    """The filter backfill.py sends to Cloud Logging API MUST be
    identical (after normalisation) to the filter terraform installed
    in the sink. Any drift = backfill pulls the wrong subset."""
    assert BACKFILL.exists(), "backfill module absent — see other test"
    tf_filter = _extract_terraform_sink_filter(TF_MAIN.read_text())
    bf_filter = _extract_backfill_filter(BACKFILL.read_text())
    assert tf_filter, "terraform sink filter regex failed — recipe broken"
    assert bf_filter, (
        "backfill.py has no SINK_FILTER_TEMPLATE constant matching the "
        "expected shape. Define it at module top with `{project_id}` "
        "placeholders where terraform uses `${var.project_id}`."
    )
    assert tf_filter == bf_filter, (
        "backfill filter and terraform sink filter DIFFER:\n"
        f"  terraform: {tf_filter[:250]}...\n"
        f"  backfill:  {bf_filter[:250]}...\n"
        "They must be byte-identical (after variable substitution) — "
        "otherwise backfill fetches different logs than the sink."
    )


def test_backfill_merges_on_insertid() -> None:
    """The MERGE statement MUST join on insertId (the unique per-entry
    UUID Cloud Logging assigns). Anything else (timestamp / trace /
    logName+timestamp) risks dup or drop."""
    assert BACKFILL.exists(), "backfill module absent — see other test"
    src = BACKFILL.read_text()
    # Look for MERGE ... ON ... insertId shape
    has_merge_on_insertid = re.search(
        r"MERGE[\s\S]{0,400}insertId\s*=", src, re.IGNORECASE,
    ) is not None
    assert has_merge_on_insertid, (
        "backfill.py has no MERGE statement joining on insertId. Without "
        "it, backfill risks either duplicating rows (if window overlaps "
        "sink) or missing boundary-race entries (if window is too tight)."
    )


def test_backfill_uses_overlap_window() -> None:
    """The tail of the backfill window MUST extend past MIN(sink_ts) so
    the pipeline-latency race window is covered. MERGE-on-insertId
    handles the resulting dup rows."""
    assert BACKFILL.exists(), "backfill module absent — see other test"
    src = BACKFILL.read_text()
    # Look for the overlap intent — a `timedelta(hours=` or `INTERVAL 1 HOUR`
    # or similar being ADDED to the sink cutoff.
    has_overlap = (
        re.search(r"timedelta\s*\(\s*hours\s*=\s*[1-9]", src)
        or re.search(r"INTERVAL\s+\d+\s+HOUR", src, re.IGNORECASE)
        or "OVERLAP" in src.upper()
    )
    assert has_overlap, (
        "backfill.py window has no explicit overlap with sink coverage. "
        "Log pipeline latency can lag a few minutes at the boundary — "
        "without overlap + MERGE dedupe, those boundary logs get missed. "
        "Extend the window tail by ~1h past MIN(sink_ts)."
    )


def test_makefile_has_backfill_target() -> None:
    text = MAKEFILE.read_text()
    has_target = any(
        ln.startswith("backfill:") or ln.startswith("backfill ")
        for ln in text.splitlines()
    )
    assert has_target, (
        "Makefile has no `backfill:` target. Operators need "
        "`make backfill PROJECT=<id> DAYS=<n>` as the one-command "
        "post-deploy history import entry point."
    )
