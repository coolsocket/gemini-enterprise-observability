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

"""RED test for INV-001: BQ_LOCATION follows REGION by default.

See infra/contexts/deploy/INVARIANTS.md#INV-001.

Reported: `make install` copied .env.example to .env, which shipped a
hardcoded `BQ_LOCATION=US`. Operator ran
`make deploy-infra REGION=asia-southeast1` — preflight refused with
"REGION and BQ_LOCATION don't co-locate" because .env's US default
survived. Operator did nothing wrong; the template betrayed them.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = ROOT / ".env.example"
MAKEFILE = ROOT / "Makefile"


def test_env_example_does_not_hardcode_bq_location() -> None:
    """INV-001 (a): .env.example MUST NOT ship BQ_LOCATION uncommented.
    Users copy .env.example → .env once and never touch BQ_LOCATION
    again; a hardcoded default there is stuck-on-US-forever."""
    text = ENV_EXAMPLE.read_text()
    # Scan for any un-commented `BQ_LOCATION=` line
    bad_lines = [
        (i, ln) for i, ln in enumerate(text.splitlines(), start=1)
        if re.match(r"^\s*BQ_LOCATION\s*=", ln)
    ]
    assert not bad_lines, (
        ".env.example ships an uncommented BQ_LOCATION default:\n"
        + "\n".join(f"  line {ln_no}: {ln}" for ln_no, ln in bad_lines)
        + "\nComment it out (`# BQ_LOCATION=asia-southeast1`) with an "
        "explanatory note. The Makefile default (see next test) will make "
        "BQ_LOCATION follow REGION when unset."
    )


def test_makefile_bq_location_defaults_to_region() -> None:
    """INV-001 (b): Makefile MUST default BQ_LOCATION to REGION when
    the operator hasn't set it. `?=` doesn't fire if .env or CLI set it,
    so operators can still explicitly opt into cross-region."""
    text = MAKEFILE.read_text()
    # Look for `BQ_LOCATION ?= $(REGION)` OR any conditional-default pattern
    # that resolves BQ_LOCATION from REGION when unset.
    ok = re.search(r"BQ_LOCATION\s*\?=\s*\$\(REGION\)", text) is not None
    if not ok:
        # Also accept a `ifeq/ifndef` style conditional
        ok = re.search(
            r"ifn?deq?\s*.*BQ_LOCATION.*\n.*BQ_LOCATION\s*[:?]?=\s*\$\(REGION\)",
            text,
            re.MULTILINE,
        ) is not None
    assert ok, (
        "Makefile doesn't derive BQ_LOCATION from REGION when unset. "
        "Add `BQ_LOCATION ?= $(REGION)` to the deploy variables block so "
        "an operator who only sets REGION gets a co-located dataset by "
        "default (INV-001)."
    )


def test_derivation_actually_works_via_make() -> None:
    """Integration-style: shell out to `make -n tf-plan REGION=asia-southeast1`
    without setting BQ_LOCATION, then assert the rendered command includes
    `-var "bq_location=asia-southeast1"`. This catches the invariant end-to-end
    (Makefile → shell → subprocess env)."""
    # Use `make -n` (dry-run) so we don't need real GCP credentials.
    # Env-scrub BQ_LOCATION so a stray shell var doesn't mask the bug.
    result = subprocess.run(
        ["make", "-n", "tf-plan", "PROJECT=x", "REGION=asia-southeast1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(Path.home()),
            # Deliberately NOT setting BQ_LOCATION — we want the default to kick in.
        },
    )
    combined = result.stdout + result.stderr
    assert 'bq_location=asia-southeast1' in combined, (
        f"Derivation failed. `make -n tf-plan REGION=asia-southeast1` should "
        f"render `-var \"bq_location=asia-southeast1\"` (auto-derived from "
        f"REGION), got:\n{combined[-800:]}"
    )
