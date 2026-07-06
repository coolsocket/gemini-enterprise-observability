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

"""Parser for Discovery Engine `licenseConfigs` responses.

Extracted from routes/refresh.py `_fetch_and_persist_license_configs`
(2026-07-06, Phase 3 of the TDDD split). Pure function: takes the raw
list-of-dicts as returned by the REST API, returns the aggregated
{total, by_tier, config_count} shape that gets MERGE'd into
quota_config. Zero I/O — the caller does the HTTP request and the
BigQuery persistence.

Guards INV-quota-001: seat count comes from `licenseCount` (purchased),
not from any active-user metric.
"""
from __future__ import annotations

import json
from typing import Any


def parse_license_configs(configs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a `licenseConfigs` list into MERGE-ready values.

    Args:
        configs: `data["licenseConfigs"]` from the Discovery Engine
            list endpoint. May be empty.

    Returns:
        {
          "total_seats": int,        # sum of licenseCount across all configs
          "config_count": int,       # len(configs)
          "by_tier": {tier: int},    # licenseCount grouped by subscriptionTier
          "raw_json": str,           # json.dumps(configs) — persisted as-is
                                     # so debugging can inspect what the API returned
          "note": str,               # only present when configs is empty
        }
    """
    if not configs:
        return {
            "total_seats": 0,
            "config_count": 0,
            "by_tier": {},
            "raw_json": json.dumps([]),
            "note": "no licenseConfigs returned",
        }
    total = 0
    by_tier: dict[str, int] = {}
    for c in configs:
        cnt = int(c.get("licenseCount", "0"))
        total += cnt
        tier = c.get("subscriptionTier", "UNKNOWN")
        by_tier[tier] = by_tier.get(tier, 0) + cnt
    return {
        "total_seats": total,
        "config_count": len(configs),
        "by_tier": by_tier,
        "raw_json": json.dumps(configs),
    }
