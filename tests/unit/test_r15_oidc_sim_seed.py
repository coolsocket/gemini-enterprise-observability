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

"""RED for R15 (2026-07-14) — seed OIDC/WIF-shaped log entries into
my-website-417013 Cloud Logging so we can simulate the vivo customer
flow end-to-end in a project we control.

User (2026-07-14): '你都这样试试看,能不能尝试在我的 logging 里面,
放一些 OIDC 的 logging,这样就可以模拟了. 前面做到的东西尽量不要动'.

Design:
  * NEW pure module `infra/contexts/deploy/application/oidc_log_seed.py`
    with a builder that emits Cloud Logging entries mimicking vivo's
    OIDC shape:
      - user_activity entries: useriamprincipal = numeric string,
        StreamAssist calls with request.query = null (matches vivo).
      - gen_ai_user_message entries: NO useriamprincipal, content
        with parts.text populated.
      - data_access entries: authenticationInfo.principalEmail as
        numeric string.
  * Pure fn: takes (principal_count, days_span, seed) → list of
    entry dicts ready to POST to entries.write.
  * NO changes to existing routes / views / backfill code. All new files.
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_oidc_seed_module_exists_and_is_pure() -> None:
    p = REPO / "infra/contexts/deploy/application/oidc_log_seed.py"
    assert p.exists(), (
        "Missing infra/contexts/deploy/application/oidc_log_seed.py — "
        "new module that generates OIDC-shaped log entry dicts."
    )
    src = p.read_text()
    # Pure builder: no I/O in this module (the seeder-runner CLI can go
    # elsewhere; the builder itself must be unit-testable).
    for banned in ("urllib.request", "requests.post", "urllib.request.urlopen"):
        assert banned not in src, (
            f"oidc_log_seed.py should be a pure builder — no {banned}. "
            f"I/O lives in a separate seed_oidc_logs.py CLI runner."
        )
    assert "def build_oidc_entries" in src, (
        "oidc_log_seed.py must export a `build_oidc_entries(principals, "
        "days_span, seed)` fn returning a list of Cloud Logging entry dicts."
    )


def test_oidc_seed_generates_two_log_types() -> None:
    """The seeder produces the two log types that entries.write allows.
    cloudaudit.data_access is intentionally NOT synthesized — Cloud
    Logging rejects it (only GCP services can write audit logs)."""
    from infra.contexts.deploy.application.oidc_log_seed import build_oidc_entries
    entries = build_oidc_entries(principal_count=5, days_span=10, seed=42)
    log_names = {e["logName"].split("/")[-1] for e in entries}
    assert "discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity" in log_names
    assert "discoveryengine.googleapis.com%2Fgen_ai.user.message" in log_names
    # cloudaudit intentionally absent — R15 discovered `entries.write`
    # rejects user-written audit logs.
    assert "cloudaudit.googleapis.com%2Fdata_access" not in log_names


def test_oidc_seed_uses_numeric_subject_principals() -> None:
    """Reproducing vivo's identity shape — numeric string principals
    like '10000001', not emails."""
    from infra.contexts.deploy.application.oidc_log_seed import build_oidc_entries
    entries = build_oidc_entries(principal_count=3, days_span=1, seed=42)
    # Look at user_activity entries — those DO carry useriamprincipal.
    user_activity = [
        e for e in entries
        if "gemini_enterprise_user_activity" in e["logName"]
    ]
    assert user_activity, "no user_activity entries generated"
    for e in user_activity:
        principal = e["jsonPayload"].get("useriamprincipal")
        assert principal and principal.isdigit(), (
            f"useriamprincipal should be a numeric string (OIDC subject); "
            f"got {principal!r}"
        )


def test_oidc_seed_gen_ai_has_no_principal() -> None:
    """Vivo's gen_ai_user_message has NO user identity fields — the
    seed must reproduce that gap so R11c's schema hint stays accurate."""
    from infra.contexts.deploy.application.oidc_log_seed import build_oidc_entries
    entries = build_oidc_entries(principal_count=3, days_span=1, seed=42)
    gen_ai = [e for e in entries if "gen_ai.user.message" in e["logName"]]
    assert gen_ai, "no gen_ai entries generated"
    for e in gen_ai:
        jp = e.get("jsonPayload", {})
        assert "useriamprincipal" not in jp, (
            f"gen_ai entries must NOT include useriamprincipal — vivo "
            f"schema doesn't have it. Got: {list(jp.keys())}"
        )
        # But content.parts.text should be populated (real prompts live here).
        parts = (jp.get("content") or {}).get("parts") or []
        has_text = any(p.get("text") for p in parts if isinstance(p, dict))
        assert has_text, (
            f"gen_ai entries should have content.parts[].text populated — "
            f"that's where vivo's real prompts live. entry={jp}"
        )
