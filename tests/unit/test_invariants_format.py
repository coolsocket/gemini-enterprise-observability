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

"""Every INV in every INVARIANTS.md MUST have a `**Code:**` pointer AND
a `**Test:**` pointer. Enforces the format normalised 2026-07-09.

Rationale: 3 INV files drift out of format when nobody's watching.
Consistent structure means anyone reading a new INV knows exactly
where to jump for the enforcing code and the locking test.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]

INV_FILES = [
    "apps/api/contexts/observability/INVARIANTS.md",
    "apps/api/contexts/quota/INVARIANTS.md",
    "infra/contexts/deploy/INVARIANTS.md",
]


def _iter_inv_blocks(src: str):
    """Yield (inv_heading, block_text) for each `## INV-...` section."""
    # Split by top-level `## ` — everything after a heading up to the next.
    parts = re.split(r"(?=^## INV-)", src, flags=re.MULTILINE)
    for part in parts:
        m = re.match(r"^(## INV-[^\n]+)\n", part)
        if m:
            yield m.group(1), part


def test_every_inv_has_code_and_test_pointer() -> None:
    missing: list[str] = []
    for f in INV_FILES:
        src = (REPO / f).read_text()
        for heading, block in _iter_inv_blocks(src):
            has_code = "**Code:**" in block
            has_test = "**Test:**" in block
            if not (has_code and has_test):
                missing.append(
                    f"{f}: {heading}  "
                    f"code={has_code} test={has_test}"
                )
    assert not missing, (
        f"{len(missing)} INV(s) missing **Code:** and/or **Test:** pointers:\n"
        + "\n".join(f"  {m}" for m in missing)
        + "\n\nNormalise the block to end with:\n"
        "  - **Code:** `path/to/module.py::function` or wider\n"
        "  - **Test:** `tests/unit/test_xxx.py`\n"
    )


def test_no_inv_files_beyond_the_three() -> None:
    """If a new INVARIANTS.md appears somewhere, either add it to this
    test's list (so it's checked) or that's a mistake."""
    found = set()
    for md in REPO.glob("**/INVARIANTS.md"):
        if "node_modules" in str(md) or ".venv" in str(md):
            continue
        rel = str(md.relative_to(REPO))
        found.add(rel)
    expected = set(INV_FILES)
    extra = found - expected
    assert not extra, (
        f"Extra INVARIANTS.md files not in the format-lock list: {sorted(extra)}. "
        "If intentional, add them to INV_FILES in this test."
    )
    missing = expected - found
    assert not missing, f"Expected INV files missing: {sorted(missing)}"
