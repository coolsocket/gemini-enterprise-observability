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

"""Pure SQL builder for /api/quota/overview totals.

Extracted from routes/quota.py (R9, 2026-07-11) so the SQL can be
unit-tested. Two critical departures from the `v_quota_totals` view:

  * `quota.default_tier` config key is COALESCE'd with `'standard'`
    as a hard fallback. Without this, a tenant missing the key gets
    NULL tier in seat_pool → JOIN tier_limits drops everything →
    totals silently empty (R9 fix).
  * `tier_limits` is UNNEST'd from TIER_DEFAULTS as a fallback layer;
    config values override defaults when present, missing config
    entries fall back to canonical defaults. Without this fallback,
    a tenant that seeded only some tier.*_daily keys (e.g. vivo old
    bootstrap: chat / deep_research / agent_create) shows only those
    features in totals; notebooklm / a2a are invisible even though
    the frontend expects them (R10 2026-07-13 fix).
  * All computation reads base tables (quota_config, user_tier,
    v_daily_usage_per_user) directly. No dependency on v_quota_totals
    or v_quota_utilization views. Read-only viewers still work.

Pure module: no I/O, no framework imports.
"""
from __future__ import annotations

from apps.api.contexts.quota.domain.tier_defaults import TIER_DEFAULTS


def render_totals_sql(project: str, dataset: str, window_days: int) -> str:
    """Build the SELECT that populates the "总配额 vs 已用" panel.

    Args:
      project, dataset: BigQuery target.
      window_days: 1, 7, or 30. Values outside this set are treated as 1.

    Semantics:
      * window_days=1 → usage from today's row in v_daily_usage_per_user
        (California day). Capacity from tier_limits × seat_pool.
      * window_days=7|30 → usage summed over last N CA days. Capacity
        multiplied by N so the ratio stays interpretable ("this window's
        budget burn").

    Returns:
      A SELECT string safe to hand to _bq.query(...). Inputs are
      Python-controlled (not user-supplied) so f-string interpolation
      of project/dataset/window_days is not an injection concern.
    """
    if window_days not in (1, 7, 30):
        window_days = 1
    # Usage window predicate.
    if window_days == 1:
        usage_where = (
            "WHERE d = DATE(CURRENT_TIMESTAMP(), 'America/Los_Angeles')"
        )
        capacity_multiplier = 1
    else:
        usage_where = (
            f"WHERE d >= DATE_SUB("
            f"DATE(CURRENT_TIMESTAMP(), 'America/Los_Angeles'), "
            f"INTERVAL {window_days - 1} DAY)"
        )
        capacity_multiplier = window_days
    # Build the STRUCT list for the tier_limits_defaults CTE.
    # Only include _daily keys (skip tier.*.storage_gib — not a per-day
    # feature, not surfaced in the totals grid).
    default_structs: list[str] = []
    for key, val in TIER_DEFAULTS:
        if not key.startswith("tier.") or not key.endswith("_daily"):
            continue
        # tier.<tier>.<feature>_daily
        parts = key.split(".")
        tier = parts[1]
        feature = parts[2][:-len("_daily")]
        default_structs.append(
            f"STRUCT('{tier}' AS tier, '{feature}' AS feature, "
            f"{int(val)} AS default_limit)"
        )
    default_structs_sql = ",\n        ".join(default_structs)
    # SQL. Base tables only — no v_quota_totals / v_quota_utilization.
    # tier_limits now merges TIER_DEFAULTS with the tenant's cfg so every
    # canonical (tier, feature) always has a limit, but a configured
    # value wins when present.
    return f"""
    WITH cfg AS (
      SELECT key, value FROM `{project}.{dataset}.quota_config`
    ),
    tier_limits_configured AS (
      SELECT SPLIT(key, '.')[SAFE_OFFSET(1)] AS tier,
             REGEXP_EXTRACT(key, r'\\.([^.]+)_daily$') AS feature,
             CAST(value AS INT64) AS cfg_limit
      FROM cfg WHERE key LIKE 'tier.%_daily'
    ),
    tier_limits_defaults AS (
      SELECT * FROM UNNEST([
        {default_structs_sql}
      ])
    ),
    tier_limits AS (
      SELECT d.tier, d.feature,
             COALESCE(c.cfg_limit, d.default_limit) AS daily_limit
      FROM tier_limits_defaults d
      LEFT JOIN tier_limits_configured c USING (tier, feature)
    ),
    default_tier AS (
      -- KEY FIX (R9): COALESCE with 'standard' so a tenant that hasn't
      -- explicitly set quota.default_tier still gets a working panel.
      SELECT COALESCE(
               (SELECT value FROM cfg WHERE key = 'quota.default_tier'),
               'standard'
             ) AS t
    ),
    purchased AS (
      SELECT COALESCE(
               (SELECT CAST(value AS INT64) FROM cfg WHERE key = 'license.total_seats'),
               (SELECT CAST(value AS INT64) FROM cfg WHERE key = 'purchased_seats'),
               0
             ) AS n
    ),
    assigned AS (
      SELECT tier, COUNT(*) AS n
      FROM `{project}.{dataset}.user_tier`
      GROUP BY tier
    ),
    seat_pool AS (
      -- (a) users with explicit tier assignments
      SELECT tier, n FROM assigned
      UNION ALL
      -- (b) leftover seats bucketed under default_tier (never NULL now)
      SELECT (SELECT t FROM default_tier) AS tier,
             GREATEST(0,
               (SELECT n FROM purchased)
                 - COALESCE((SELECT SUM(n) FROM assigned), 0)) AS n
    ),
    capacity AS (
      SELECT tl.feature,
             SUM(sp.n * tl.daily_limit) * {capacity_multiplier} AS total_daily_quota
      FROM tier_limits tl
      JOIN seat_pool sp USING (tier)
      GROUP BY tl.feature
    ),
    usage AS (
      SELECT feature,
             SUM(n) AS total_used_today,
             COUNT(DISTINCT actor_email) AS active_users
      FROM `{project}.{dataset}.v_daily_usage_per_user`
      {usage_where}
      GROUP BY feature
    )
    SELECT
      c.feature,
      (SELECT n FROM purchased) AS eligible_users,
      c.total_daily_quota,
      IFNULL(u.total_used_today, 0) AS total_used_today,
      SAFE_DIVIDE(IFNULL(u.total_used_today, 0), c.total_daily_quota) AS overall_utilization,
      -- users_over_quota requires per-user aggregation; only well-defined
      -- for window_days=1. We report 0 for windows > 1 (frontend hides
      -- the label in that mode already).
      0 AS users_over_quota
    FROM capacity c
    LEFT JOIN usage u USING (feature)
    ORDER BY overall_utilization DESC
    """
