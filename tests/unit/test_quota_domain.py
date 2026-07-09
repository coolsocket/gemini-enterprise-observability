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

"""Coverage for the quota context's pure domain functions.

Filed 2026-07-09 after cleanliness audit flagged the quota context
as untested. Both `parse_license_configs` and `allocate_seats` are
zero-I/O pure functions — ideal test targets. INV-quota-001 is now
locked here, not just documented in INVARIANTS.md.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.api.contexts.quota.domain.license_parse import parse_license_configs
from apps.api.contexts.quota.domain.tier_allocation import allocate_seats


# ============================================================
# parse_license_configs — takes the raw DE `licenseConfigs` list,
# returns the MERGE-ready dict.
# ============================================================

class TestParseLicenseConfigs:
    def test_empty_input_returns_zeros_with_note(self):
        """When the API returns no licenseConfigs (fresh tenant with no
        licenses provisioned), we must emit a `note` — otherwise the
        caller can't distinguish "API returned []" from "we forgot to
        call the API"."""
        r = parse_license_configs([])
        assert r["total_seats"] == 0
        assert r["config_count"] == 0
        assert r["by_tier"] == {}
        assert r["note"] == "no licenseConfigs returned"
        assert r["raw_json"] == "[]"

    def test_single_config_aggregates_licenseCount(self):
        r = parse_license_configs([
            {"licenseCount": "50", "subscriptionTier": "SUBSCRIPTION_TIER_SEARCH_AND_ASSISTANT"}
        ])
        assert r["total_seats"] == 50
        assert r["config_count"] == 1
        assert r["by_tier"] == {"SUBSCRIPTION_TIER_SEARCH_AND_ASSISTANT": 50}
        assert "note" not in r   # only present on empty input

    def test_multiple_configs_same_tier_sum(self):
        """Multiple configs with the same tier accumulate — GE may return
        several licenseConfig rows for the same subscription tier when
        seats are allocated in batches."""
        r = parse_license_configs([
            {"licenseCount": "30", "subscriptionTier": "A"},
            {"licenseCount": "20", "subscriptionTier": "A"},
        ])
        assert r["total_seats"] == 50
        assert r["by_tier"] == {"A": 50}
        assert r["config_count"] == 2

    def test_multiple_tiers_grouped_separately(self):
        r = parse_license_configs([
            {"licenseCount": "10", "subscriptionTier": "plus"},
            {"licenseCount": "40", "subscriptionTier": "standard"},
            {"licenseCount": "5",  "subscriptionTier": "plus"},
        ])
        assert r["total_seats"] == 55
        assert r["by_tier"] == {"plus": 15, "standard": 40}

    def test_missing_licenseCount_defaults_to_zero(self):
        """Defensive against GE returning a config with no seat count."""
        r = parse_license_configs([
            {"subscriptionTier": "A"},                        # no licenseCount
            {"licenseCount": "10", "subscriptionTier": "A"},
        ])
        assert r["total_seats"] == 10
        assert r["by_tier"] == {"A": 10}

    def test_missing_subscriptionTier_becomes_UNKNOWN(self):
        """Defensive against GE returning a config with no tier."""
        r = parse_license_configs([{"licenseCount": "7"}])
        assert r["total_seats"] == 7
        assert r["by_tier"] == {"UNKNOWN": 7}

    def test_licenseCount_string_int_coerced(self):
        """Discovery Engine returns licenseCount as a JSON string
        (`"50"`, not `50`) per GAPIC convention for uint64."""
        r = parse_license_configs([{"licenseCount": "42", "subscriptionTier": "A"}])
        assert r["total_seats"] == 42
        assert isinstance(r["total_seats"], int)

    def test_raw_json_roundtrips_the_input(self):
        """raw_json field must be a valid JSON of the input, so debug
        queries can `SELECT JSON_QUERY(license.raw, '$[0].licenseCount')`."""
        cfg = [{"licenseCount": "12", "subscriptionTier": "X", "displayName": "test"}]
        r = parse_license_configs(cfg)
        assert json.loads(r["raw_json"]) == cfg


# ============================================================
# allocate_seats — split purchased seats across tiers, remainder
# to default. INV-quota-001: quota = purchased × per-tier limit
# (not active-user × limit).
# ============================================================

class TestAllocateSeats:
    def test_happy_path_remainder_to_default(self):
        r = allocate_seats(purchased=100, assigned={"plus": 30}, default_tier="standard")
        assert r == {"plus": 30, "standard": 70}
        assert sum(r.values()) == 100

    def test_all_assigned_no_default_entry(self):
        """When assigned totals exactly purchased, default gets nothing —
        and should NOT appear in the output (avoids showing '0 seats'
        in the dashboard for a tier that has no allocation)."""
        r = allocate_seats(purchased=50, assigned={"plus": 50}, default_tier="standard")
        assert r == {"plus": 50}
        assert "standard" not in r

    def test_empty_assigned_all_go_to_default(self):
        """First-time tenant: nobody assigned yet, all seats sit in
        the default tier's bucket ready for use."""
        r = allocate_seats(purchased=100, assigned={}, default_tier="standard")
        assert r == {"standard": 100}

    def test_zero_purchased_returns_empty(self):
        """Trial/dev tenant with 0 seats — no output, not {default: 0}."""
        r = allocate_seats(purchased=0, assigned={}, default_tier="standard")
        assert r == {}

    def test_overflow_clamped_to_zero_no_negative(self):
        """Assignment overflow (someone assigned tiers beyond purchased —
        happens when admin removes seats but forgets to unassign) MUST
        NOT produce negative seat counts. Clamp remainder to 0."""
        r = allocate_seats(purchased=10, assigned={"plus": 50}, default_tier="standard")
        assert r == {"plus": 50}
        assert all(v >= 0 for v in r.values())

    def test_zero_count_assignments_filtered(self):
        """`assigned={'plus': 0}` shouldn't create a `plus: 0` entry —
        BQ `SELECT ... GROUP BY tier` can emit 0-count rows in edge cases."""
        r = allocate_seats(purchased=100, assigned={"plus": 0}, default_tier="standard")
        assert "plus" not in r
        assert r == {"standard": 100}

    def test_default_tier_in_assigned_merges(self):
        """If default_tier is also in `assigned` (admin has explicitly
        assigned some users to what happens to be the default), the
        remainder ADDS to that assignment (not overwrites)."""
        r = allocate_seats(purchased=100, assigned={"standard": 10}, default_tier="standard")
        assert r == {"standard": 100}   # 10 assigned + 90 default → 100

    def test_purchased_negative_raises(self):
        with pytest.raises(ValueError, match="purchased must be >= 0"):
            allocate_seats(purchased=-1, assigned={}, default_tier="standard")

    def test_empty_default_tier_raises(self):
        with pytest.raises(ValueError, match="default_tier"):
            allocate_seats(purchased=100, assigned={}, default_tier="")

    def test_negative_assignment_raises(self):
        with pytest.raises(ValueError, match=r"assigned\['plus'\] must be >= 0"):
            allocate_seats(purchased=100, assigned={"plus": -1}, default_tier="standard")

    def test_sum_equals_purchased_for_normal_inputs(self):
        """Property: for non-overflow inputs, sum(result.values()) == purchased.
        This is the INV-quota-001 arithmetic guarantee."""
        for p in (0, 1, 50, 999, 10000):
            for a in ({}, {"plus": 10}, {"plus": 3, "custom": 2}):
                assigned_total = sum(a.values())
                if assigned_total > p:
                    continue   # overflow case is separate test
                r = allocate_seats(purchased=p, assigned=a, default_tier="standard")
                assert sum(r.values()) == p, (
                    f"purchased={p} assigned={a} → {r} (sum={sum(r.values())})"
                )
