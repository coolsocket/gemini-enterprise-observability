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

"""RED for the "totals empty even with tier limits seeded" bug (2026-07-11).

Symptom (user report on vivo): Quota page's totals panel shows empty
state even though `quota_config` HAS the 8 tier.*_daily keys (visible
in the "Tier 阈值配置" table below).

Root cause: `v_quota_totals` builds `seat_pool` via UNION of:
  (a) explicitly assigned tiers from user_tier
  (b) leftover seats bucketed under (SELECT value FROM quota_config
      WHERE key = 'quota.default_tier')

If `quota.default_tier` is MISSING, path (b) produces (NULL, n).
`per_feature_capacity` JOINs `tier_limits` USING (tier). NULL tier
never matches. If user_tier is also empty (no explicit assignments),
seat_pool.tier ends up entirely NULL → JOIN yields 0 rows → totals
empty.

Sandbox was fine because it had `quota.default_tier = plus` seeded
ad-hoc long ago. Vivo never had it. TIER_DEFAULTS covered the 12
tier keys but forgot this 13th required config entry.

Fix: add `quota.default_tier = 'standard'` to TIER_DEFAULTS so
bootstrap + lazy-seed both cover it. Also update the frontend empty-
state hint — the old copy misled the user by claiming tier keys were
missing when they weren't.
"""
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]


def test_tier_defaults_includes_quota_default_tier() -> None:
    """The 'quota.default_tier' key is a load-bearing v_quota_totals
    dependency (bucketed seats without user_tier assignments end up
    here). Must be in TIER_DEFAULTS so bootstrap and lazy-seed both
    write it, otherwise totals silently returns empty.
    """
    from apps.api.contexts.quota.domain.tier_defaults import TIER_DEFAULTS
    keys = {k for k, _ in TIER_DEFAULTS}
    assert "quota.default_tier" in keys, (
        "TIER_DEFAULTS missing `quota.default_tier`. Without it, "
        "v_quota_totals's seat_pool CTE bucketizes leftover seats "
        "under NULL tier, per_feature_capacity's JOIN drops them all, "
        "and /api/quota/overview returns empty totals — even when "
        "every tier.*_daily key IS seeded. Fixed by adding "
        "('quota.default_tier', 'standard') to the list."
    )
    val = dict(TIER_DEFAULTS)["quota.default_tier"]
    assert val in {"standard", "plus"}, (
        f"quota.default_tier value must be 'standard' or 'plus'; got {val!r}. "
        "Standard is the conservative default (lower per-user limits)."
    )


def test_frontend_empty_state_hint_not_misleading() -> None:
    """The empty-state hint on Quota.tsx (from f9f0066) claims
    tier.*_daily keys are missing. But we now know the actual failure
    mode can be `quota.default_tier` missing too. Update the hint to
    mention checking the full quota_config chain, not just tier keys.
    """
    src = (REPO / "apps/web/src/pages/Quota.tsx").read_text()
    # Locate the empty-state block. EmptyState may be self-closing (`/>`)
    # OR paired (`</EmptyState>`), depending on how the hint is passed.
    m = re.search(
        r"totals\.length\s*===\s*0[\s\S]{0,2000}?(</EmptyState>|/>)",
        src,
    )
    assert m, "Quota.tsx empty-state block not found"
    block = m.group(0)
    # The hint should either mention quota.default_tier explicitly,
    # OR admit the check is "some quota_config entry" not specifically
    # tier.*_daily (which we now know isn't the only cause).
    mentions_default_tier = (
        "default_tier" in block
        or "quota.default_tier" in block
    )
    admits_broader = (
        "quota_config" in block  # already there
        and re.search(r"缺|missing|not.*seed|未.*配|尚未", block)
    )
    assert mentions_default_tier or admits_broader, (
        "Quota.tsx empty-state hint blames tier.*_daily keys, but on "
        "vivo the real cause was `quota.default_tier` missing. Update "
        "the hint to either mention default_tier explicitly or admit "
        "the diagnosis is 'some quota_config chain' broader than just "
        "tier keys."
    )
