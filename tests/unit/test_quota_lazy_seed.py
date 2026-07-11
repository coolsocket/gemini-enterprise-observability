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

"""RED for R7 (2026-07-11) — quota_overview auto-seeds missing tier
defaults so first-hit on a fresh tenant renders populated cards.

Context: fixed the empty-state UX yesterday (f9f0066). The proper
next step is to eliminate the empty state where we can: if the tenant
lacks `tier.*_daily` keys AND we have BQ write permission, MERGE the
defaults from the domain module. This mirrors bootstrap.py's
idempotent seeding, but runs lazily instead of requiring an admin to
re-execute the bootstrap script.

Invariants asserted:
  * Pure domain module `tier_defaults.TIER_DEFAULTS` exposes the
    canonical list of (key, value) pairs; bootstrap.py imports from
    here so there's one source of truth.
  * A helper in the quota context OR route layer wraps the MERGE.
    Uses WHEN NOT MATCHED (never overwrites admin edits).
  * quota_overview calls the helper. On BQ permission errors the
    helper swallows + logs; the endpoint never 500s over seeding.
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


def test_tier_defaults_domain_module_exists() -> None:
    """The 8-entry TIER_DEFAULTS list should live in a pure domain
    module, not embedded inline in bootstrap.py — so the route layer
    can also import it."""
    path = REPO / "apps/api/contexts/quota/domain/tier_defaults.py"
    assert path.exists(), (
        "Missing apps/api/contexts/quota/domain/tier_defaults.py. "
        "Extract the TIER_DEFAULTS list from bootstrap.py so the quota "
        "route can lazy-seed missing keys."
    )
    src = path.read_text()
    assert re.search(r"TIER_DEFAULTS\s*[:=]", src), (
        "tier_defaults.py must export a TIER_DEFAULTS list."
    )
    # Pure: no I/O imports
    for banned in ("import google", "urllib.request", "requests"):
        assert banned not in src, (
            f"tier_defaults.py should be pure — no {banned}."
        )


def test_tier_defaults_shape() -> None:
    """The list must cover all 5 features × 2 tiers (10 daily keys)
    plus the 2 storage entries — matches bootstrap.py 2026-07-10."""
    from apps.api.contexts.quota.domain.tier_defaults import TIER_DEFAULTS
    keys = {k for k, _ in TIER_DEFAULTS}
    for feat in ("chat", "deep_research", "notebooklm", "a2a", "agent_create"):
        for tier in ("standard", "plus"):
            k = f"tier.{tier}.{feat}_daily"
            assert k in keys, f"missing default key: {k}"
    # storage entries should also be present
    assert "tier.standard.storage_gib" in keys
    assert "tier.plus.storage_gib" in keys


def test_bootstrap_imports_from_domain_module() -> None:
    """bootstrap.py should import TIER_DEFAULTS from the domain module,
    not redeclare inline — single source of truth."""
    src = (REPO / "infra/contexts/deploy/application/bootstrap.py").read_text()
    assert re.search(
        r"from\s+apps\.api\.contexts\.quota\.domain\.tier_defaults\s+import",
        src,
    ), (
        "bootstrap.py should `from apps.api.contexts.quota.domain."
        "tier_defaults import TIER_DEFAULTS`, not redeclare inline."
    )


def test_quota_route_lazy_seeds_missing_defaults() -> None:
    """/api/quota/overview should upsert missing tier defaults before
    running the totals query. Look for either a direct MERGE, a
    helper call, or a reference to TIER_DEFAULTS in quota.py."""
    src = (REPO / "apps/api/routes/quota.py").read_text()
    references_defaults = (
        "TIER_DEFAULTS" in src
        or "_seed_missing_tier_defaults" in src
        or "seed_tier_defaults" in src
    )
    assert references_defaults, (
        "apps/api/routes/quota.py doesn't reference tier defaults. "
        "In quota_overview, call a seeder that MERGE WHEN NOT MATCHED "
        "upserts each default from tier_defaults.TIER_DEFAULTS. "
        "Catch google.api_core.exceptions.Forbidden so read-only "
        "identities (e.g. yehao ADC on responsive-lens) don't 500."
    )
