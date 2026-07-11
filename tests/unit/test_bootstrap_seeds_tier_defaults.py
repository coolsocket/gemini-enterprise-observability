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

"""RED regression: bootstrap.py doesn't seed tier quota defaults.

User feedback (2026-07-07): "quota 这里要配置一下". Root cause:
Quota.tsx UI iterates FEATURE_ORDER = ["chat", "deep_research",
"agent_create"] and reads `tier.{standard,plus}.{f}_daily`, plus
`tier.{standard,plus}.storage_gib` — 8 keys total. bootstrap.py
seeds `purchased_seats`, `claimed_window_days`, and `license.*`
from the API — but NOT the 8 tier keys. Every "每天限额" and
storage cell shows "—".

Fix: extend seed_quota_config() to write sensible defaults for the
8 tier keys via MERGE ... WHEN NOT MATCHED (so admin edits via UI
aren't clobbered on re-run).
"""
from pathlib import Path
import re

BOOTSTRAP = Path(__file__).resolve().parents[2] / "infra/contexts/deploy/application/bootstrap.py"

# Keys Quota.tsx reads — must all appear in bootstrap.py as MERGE targets.
REQUIRED_TIER_KEYS = {
    "tier.standard.chat_daily",
    "tier.standard.deep_research_daily",
    "tier.standard.agent_create_daily",
    "tier.plus.chat_daily",
    "tier.plus.deep_research_daily",
    "tier.plus.agent_create_daily",
    "tier.standard.storage_gib",
    "tier.plus.storage_gib",
}


def test_bootstrap_seeds_all_tier_defaults() -> None:
    # Post-R7 (2026-07-11) the TIER_DEFAULTS list moved to a shared
    # domain module. bootstrap.py imports the same list; look up the
    # keys there instead of grepping bootstrap.py inline.
    from apps.api.contexts.quota.domain.tier_defaults import TIER_DEFAULTS
    seeded = {k for k, _ in TIER_DEFAULTS}
    missing = sorted(REQUIRED_TIER_KEYS - seeded)
    assert not missing, (
        f"TIER_DEFAULTS (imported by bootstrap.py + routes/quota.py) is "
        f"missing {len(missing)} tier keys that Quota.tsx needs:\n"
        + "\n".join(f"  - {k}" for k in missing)
        + "\n\nAdd each (key, value) pair to "
        "apps/api/contexts/quota/domain/tier_defaults.py so both the "
        "deploy-time bootstrap AND the lazy-seed path pick them up."
    )
    # Sanity: bootstrap.py must actually import + iterate over
    # TIER_DEFAULTS (not roll its own list).
    src = BOOTSTRAP.read_text()
    assert re.search(
        r"from\s+apps\.api\.contexts\.quota\.domain\.tier_defaults\s+import\s+TIER_DEFAULTS",
        src,
    ), (
        "bootstrap.py should import TIER_DEFAULTS from the domain module — "
        "any inline list would drift from routes/quota.py's lazy-seed."
    )


def test_bootstrap_tier_seeds_use_when_not_matched() -> None:
    """Tier defaults MUST be seeded with `WHEN NOT MATCHED` semantics — so
    re-running bootstrap doesn't overwrite whatever the admin has already
    tweaked via the Quota UI. `WHEN MATCHED THEN UPDATE` for tier keys
    would silently reset admin edits every re-run."""
    src = BOOTSTRAP.read_text()
    # Extract the seed_quota_config function body
    m = re.search(
        r"def seed_quota_config\([^)]*\)[^:]*:.*?(?=\ndef |\Z)",
        src, re.DOTALL,
    )
    assert m, "could not find seed_quota_config in bootstrap.py"
    body = m.group(0)
    if not any(k in body for k in REQUIRED_TIER_KEYS):
        import pytest
        pytest.skip("tier keys not seeded yet (other test flags this)")
    # Find each MERGE block that references a tier key and confirm it's
    # WHEN NOT MATCHED shape (no WHEN MATCHED THEN UPDATE for tier.*).
    # Cheap check: search for a "WHEN MATCHED THEN UPDATE" within 200 chars
    # of any tier.* string reference.
    for k in REQUIRED_TIER_KEYS:
        for m in re.finditer(re.escape(k), body):
            window = body[max(0, m.start() - 500): m.end() + 500]
            if re.search(r"WHEN\s+MATCHED\s+THEN\s+UPDATE", window, re.IGNORECASE):
                # If the same block also has WHEN NOT MATCHED THEN INSERT (both
                # branches of a MERGE) that's still UPDATE-semantics — reject.
                assert False, (
                    f"tier key `{k}` is seeded with WHEN MATCHED THEN UPDATE. "
                    "That overwrites admin edits every bootstrap re-run. "
                    "Use `WHEN NOT MATCHED THEN INSERT` only (mirror how "
                    "purchased_seats/claimed_window_days are seeded)."
                )
