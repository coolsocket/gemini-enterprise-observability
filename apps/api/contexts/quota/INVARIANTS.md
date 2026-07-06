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

- **Parser (pure):** `apps/api/contexts/quota/domain/license_parse.py::parse_license_configs`
- **Allocator (pure spec):** `apps/api/contexts/quota/domain/tier_allocation.py::allocate_seats`
- **Persistence I/O:** `apps/api/routes/refresh.py::_fetch_and_persist_license_configs`
- **Live SQL (production):** the tier-allocation math is also encoded in
  `apps/api/views.sql.tmpl` (v_quota_totals / v_quota_utilization) so
  dashboards can compute it in BigQuery without a round trip. The Python
  `allocate_seats` is a reference implementation of the same logic —
  keep them in sync when the invariant evolves.
