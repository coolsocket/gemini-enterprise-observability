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

"""RED for R10 (2026-07-13) — quota totals must surface EVERY canonical
feature, even when tier.*_daily config keys are missing.

Bug (vivo, live-verified 2026-07-13): /api/quota/overview returns only
3 rows (chat / deep_research / agent_create) because vivo's old
bootstrap seeded only those 3 tier keys. The R9 SQL builder reads
tier_limits from cfg WHERE key LIKE 'tier.%_daily'; missing keys
never contribute. Read-only ADC (yehao on responsive-lens) can't
write the missing notebooklm/a2a keys via lazy-seed. Reporter
explicitly wanted notebooklm on the panel.

Fix: render_totals_sql injects TIER_DEFAULTS as an UNNEST-based
fallback for tier_limits. Config values override defaults when
present; missing (tier, feature) pairs fall back to the domain
module's canonical value. Every canonical feature always shows on
the panel regardless of config completeness.
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_render_totals_sql_includes_default_tier_limits() -> None:
    """The generated SQL must include the TIER_DEFAULTS values so
    every canonical (tier, feature) pair has a limit even without
    corresponding config. Look for UNNEST([STRUCT(...)]) shape."""
    from apps.api.contexts.quota.domain.quota_sql import render_totals_sql
    sql = render_totals_sql("p", "d", 1)
    assert "UNNEST" in sql.upper(), (
        "render_totals_sql must UNNEST TIER_DEFAULTS values so features "
        "missing from cfg still get a fallback limit. Otherwise vivo "
        "(missing tier.*.notebooklm_daily) shows 0 notebooklm rows."
    )
    # notebooklm and a2a values from TIER_DEFAULTS must appear
    assert "'notebooklm'" in sql or '"notebooklm"' in sql, (
        "render_totals_sql SQL doesn't hardcode 'notebooklm' feature — "
        "the UNNEST fallback should include every canonical feature."
    )
    assert "'a2a'" in sql or '"a2a"' in sql, (
        "render_totals_sql SQL doesn't hardcode 'a2a' feature."
    )


def test_render_totals_sql_config_overrides_defaults() -> None:
    """The generated SQL must use a LEFT JOIN or COALESCE so that
    when a config value IS present, it overrides the default. Sandbox
    tenants that have tuned tier limits shouldn't get reset to
    TIER_DEFAULTS just because we added a fallback."""
    from apps.api.contexts.quota.domain.quota_sql import render_totals_sql
    sql = render_totals_sql("p", "d", 1).upper()
    # Look for LEFT JOIN with a config-side subquery. The fallback
    # pattern should be "default LEFT JOIN cfg" so cfg.value overrides
    # when present, and default_limit is used when cfg.value is NULL.
    assert "LEFT JOIN" in sql, (
        "render_totals_sql needs a LEFT JOIN to layer config values "
        "over defaults. Otherwise defaults would win everywhere."
    )
    # The COALESCE (config_value, default_value) shape ensures config
    # wins when set — verified via presence of COALESCE with two args
    # of the form (cfg-side, default-side).
    assert "COALESCE" in sql, (
        "render_totals_sql needs COALESCE(cfg_limit, default_limit) so "
        "the config value takes precedence when present."
    )
