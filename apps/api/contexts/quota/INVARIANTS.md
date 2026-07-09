# Quota invariants

Invariants owned by this context.

## INV-quota-001: seat count is `licenseConfigs.total`, not active-user count

Platform quota per feature = purchased seats × per-tier limit. NOT
active-user count × per-tier limit. Purchased seats come from the
Discovery Engine `licenseConfigs` REST endpoint and are MERGE'd into
`quota_config` under the `license.*` keys.

Assigned tiers are honored via the `user_tier` table (an admin action);
seats not covered by an assignment fall back to `quota.default_tier`
(typically `standard`).

- **Code:** `apps/api/contexts/quota/domain/license_parse.py::parse_license_configs`
  (pure parser) + `apps/api/contexts/quota/domain/tier_allocation.py::allocate_seats`
  (pure Python reference spec) + `apps/api/routes/refresh.py::_fetch_and_persist_license_configs`
  (I/O shell) + `infra/sql_templates/views.sql.tmpl` (`v_quota_totals` /
  `v_quota_utilization` — production math also encoded here so dashboards
  compute in BigQuery without a round trip)
- **Test:** `tests/unit/test_quota_domain.py` (19 tests covering pure-fn
  contracts, edge cases, overflow clamping, and the `sum == purchased`
  property for the allocator)

Note: the tier-allocation math is deliberately duplicated in Python and
SQL. Python `allocate_seats` is the reference implementation; keep both
in sync when the invariant evolves.
