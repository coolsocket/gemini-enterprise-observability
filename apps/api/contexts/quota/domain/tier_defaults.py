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

"""Canonical starting values for `quota_config` tier keys.

Single source of truth for the (key, value) pairs `bootstrap.py` seeds
at deploy time AND `routes/quota.py::quota_overview` lazy-upserts on
first hit against a fresh tenant. Extracted here (2026-07-11) so both
call sites share the same list — any future edit lands once.

Pure module: no I/O, no framework imports. `Tuple[str, str]` values so
the callers can build MERGE parameters without any transformation.

Values are starting points; admins tune them via `POST /api/quota/config`
and the UI's editable numbers on the Quota page. Both bootstrap and the
lazy-seed use `WHEN NOT MATCHED THEN INSERT`, so re-running never
clobbers admin edits — only creates missing rows.
"""
from __future__ import annotations

from typing import List, Tuple

TIER_DEFAULTS: List[Tuple[str, str]] = [
    # standard tier (baseline license)
    ("tier.standard.chat_daily",           "50"),
    ("tier.standard.deep_research_daily",   "3"),
    ("tier.standard.agent_create_daily",    "1"),
    ("tier.standard.notebooklm_daily",     "20"),  # write-side actions only (see v_daily_usage_per_user)
    ("tier.standard.a2a_daily",            "10"),
    ("tier.standard.storage_gib",          "10"),
    # plus tier (SUBSCRIPTION_TIER_SEARCH_AND_ASSISTANT)
    ("tier.plus.chat_daily",              "300"),
    ("tier.plus.deep_research_daily",      "20"),
    ("tier.plus.agent_create_daily",       "10"),
    ("tier.plus.notebooklm_daily",        "100"),
    ("tier.plus.a2a_daily",               "50"),
    ("tier.plus.storage_gib",             "100"),
    # Load-bearing: v_quota_totals uses this to bucket "seats not
    # explicitly assigned via user_tier" into a tier. Without it,
    # seat_pool has NULL tier → JOIN tier_limits drops those rows →
    # per_feature_capacity ends up empty even when every tier.*_daily
    # key IS seeded. Conservative default 'standard'; admin can flip.
    ("quota.default_tier",                 "standard"),
]
