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

"""Seat → tier allocation (INV-quota-001).

The production computation lives in views.sql.tmpl SQL — porting it out
of the view would be invasive and buy nothing today. This Python
version is intentionally a spec/reference: it documents the invariant
in executable form so future maintainers can round-trip small inputs
mentally without reading BigQuery SQL.

If a future change wants Python-side quota math (e.g. an admin UI that
previews "what if I move this user to plus?"), this is the function to
call — no BigQuery needed.
"""
from __future__ import annotations


def allocate_seats(
    purchased: int,
    assigned: dict[str, int],
    default_tier: str,
) -> dict[str, int]:
    """Split `purchased` seats across tiers.

    INV-quota-001: total quota is `purchased` × per-tier limit. Users
    explicitly assigned a tier (via user_tier table) consume seats from
    that tier's bucket. Remaining seats go to `default_tier`.

    Args:
        purchased: total purchased seats (from licenseConfigs.total).
        assigned: {tier: count_of_users_assigned_this_tier} — usually
            drawn from `SELECT tier, COUNT(*) FROM user_tier GROUP BY tier`.
        default_tier: tier for unassigned seats (from quota.default_tier
            config key). Typically 'standard'.

    Returns:
        {tier: seat_count}. Sum equals `purchased` (or `purchased`
        clamped to non-negative if assignments overflow).

    Raises:
        ValueError: purchased < 0, any assigned value < 0, or default_tier is empty.
    """
    if purchased < 0:
        raise ValueError(f"purchased must be >= 0, got {purchased}")
    if not default_tier:
        raise ValueError("default_tier must be a non-empty string")
    for tier, count in assigned.items():
        if count < 0:
            raise ValueError(f"assigned[{tier!r}] must be >= 0, got {count}")

    out: dict[str, int] = {tier: cnt for tier, cnt in assigned.items() if cnt > 0}
    assigned_total = sum(out.values())
    # Unassigned seats fall to the default tier; clamp to 0 so overflow
    # (assigned > purchased) doesn't produce negative seat counts.
    remaining = max(0, purchased - assigned_total)
    if remaining:
        out[default_tier] = out.get(default_tier, 0) + remaining
    return out
