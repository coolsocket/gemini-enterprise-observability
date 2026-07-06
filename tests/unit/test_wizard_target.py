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

"""RED tests for `make wizard` — the interactive .env editor.

`cp .env.example .env && $EDITOR .env` is unfriendly for first-timers
who don't know which fields they need to change. vigenair (Google
Marketing Solutions) uses a Node.js `prompts`-based wizard for the
same reason. We do the same in plain Bash to stay zero-dep.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
WIZARD_SH = ROOT / "infra/contexts/deploy/application/wizard.sh"


def test_wizard_target_exists_in_makefile() -> None:
    text = MAKEFILE.read_text()
    has_target = any(
        ln.startswith("wizard:") or ln.startswith("wizard ")
        for ln in text.splitlines()
    )
    assert has_target, (
        "Makefile missing `wizard` target. Add it — the wizard drives "
        "interactive .env creation for first-time deployers so they don't "
        "have to memorize which env vars to set."
    )


def test_wizard_script_exists_and_executable() -> None:
    assert WIZARD_SH.exists(), (
        f"{WIZARD_SH.relative_to(ROOT)} missing — Makefile's `wizard` "
        "target has nothing to run."
    )
    assert WIZARD_SH.stat().st_mode & 0o111, (
        f"{WIZARD_SH.relative_to(ROOT)} is not executable — chmod +x it."
    )


def test_wizard_prompts_for_all_required_env_keys() -> None:
    """The wizard MUST prompt for every env var that .env.example
    documents as required-or-commonly-tuned. Otherwise a new user runs
    the wizard and still has to hand-edit .env for the missing pieces."""
    text = WIZARD_SH.read_text()
    required_keys = ["BQ_PROJECT", "REGION", "BQ_LOCATION", "SIM_PREFIX", "DATASET"]
    missing = [k for k in required_keys if k not in text]
    assert not missing, (
        f"wizard.sh doesn't prompt for or write these keys: {missing}. "
        "A first-time deployer running `make wizard` would still need to "
        "hand-edit .env for them. Prompt via `read -p` + write to .env."
    )


def test_wizard_references_env_example() -> None:
    """The wizard should read defaults from .env.example (or at minimum
    reference it) so as .env.example evolves the wizard stays in sync."""
    text = WIZARD_SH.read_text()
    assert ".env.example" in text or ".env" in text, (
        "wizard.sh doesn't reference .env or .env.example. Should either "
        "sed-in-place the template or write a fresh .env from prompted "
        "values."
    )
