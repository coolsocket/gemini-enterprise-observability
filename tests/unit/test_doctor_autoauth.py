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

"""RED test for Tier 3 — doctor.sh should OFFER to spawn `gcloud auth
login` and `gcloud auth application-default login` when their credential
files are missing, not just print a hint.

Inspired by vigenair's checkGcloudAuth() which spawn.syncs gcloud auth
with stdio:'inherit' so the browser OAuth flow just works. The user
answers Y/n; default Y for non-interactive-friendly behavior.
"""
from pathlib import Path

DOCTOR = Path(__file__).resolve().parents[2] / "infra/contexts/deploy/application/doctor.sh"


def test_doctor_offers_to_spawn_gcloud_auth() -> None:
    """When gcloud is installed but the user hasn't authed yet, doctor
    MUST prompt to spawn `gcloud auth login` (not just print instructions)."""
    src = DOCTOR.read_text()
    # Look for `gcloud auth login` being called via read+conditional, not
    # merely mentioned in a `bad(...)` hint string.
    # Correct pattern:
    #   read -p ... reply
    #   [ "$reply" != "n" ] && gcloud auth login
    # OR
    #   if [confirm]; then gcloud auth login; fi
    assert "gcloud auth login" in src, (
        "doctor.sh doesn't reference `gcloud auth login` at all — expected "
        "it to spawn the auth flow when creds are missing."
    )
    # Not just mentioned in a hint string — must actually be invoked
    # (heuristic: appears outside of quoted double-string context)
    # Check: at least one line has `gcloud auth login` followed by end-of-line
    # (real invocation), not just `→ gcloud auth login` (hint).
    invocation_present = any(
        (
            "&& gcloud auth login" in ln
            or "; gcloud auth login" in ln
            or ln.strip().startswith("gcloud auth login")
        )
        for ln in src.splitlines()
    )
    assert invocation_present, (
        "doctor.sh mentions `gcloud auth login` only in a hint string. "
        "It should actually invoke it (after a read -p confirmation) so "
        "the operator's next step is one Enter away, not a copy-paste."
    )


def test_doctor_offers_to_spawn_adc_login() -> None:
    """Same for ADC (Application Default Credentials) — main.py + bootstrap
    read via ADC, so this is the more important auth to auto-offer."""
    src = DOCTOR.read_text()
    assert "gcloud auth application-default login" in src, (
        "doctor.sh doesn't reference `gcloud auth application-default "
        "login`."
    )
    invocation_present = any(
        (
            "&& gcloud auth application-default login" in ln
            or "; gcloud auth application-default login" in ln
            or ln.strip().startswith("gcloud auth application-default login")
        )
        for ln in src.splitlines()
    )
    assert invocation_present, (
        "doctor.sh only mentions `gcloud auth application-default login` in "
        "a hint. Spawn it after a read -p confirmation instead."
    )
