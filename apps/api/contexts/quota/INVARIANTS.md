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

## INV-quota-002: user-supplied fields in mutations MUST be bound as ScalarQueryParameter

Every write path (`quota_config_set`, `quota_set_tier`) receives arbitrary
strings from the frontend. All such fields — `key`, `value`, `email`,
`tier`, `by`, `notes` — MUST reach BigQuery via
`bigquery.ScalarQueryParameter`, never via f-string / `%` / `.format()`
interpolation.

Startswith / character-blocklist guards (e.g. `if "'" in email`) are
insufficient defenses on their own and MUST NOT be the last line of
defense. They may co-exist as an early 400 for obviously-bad shape, but
the SQL layer must still parameterize.

- **Code:** `apps/api/routes/quota.py::quota_config_set` (already correct
  reference impl) and `apps/api/routes/quota.py::quota_set_tier` (this
  invariant added because f-string interpolation was found in the wild
  2026-07-10; the fix mirrors the config_set pattern).
- **Test:** `tests/unit/test_quota_write_injection.py` — payloads with
  quotes, semicolons, and comment markers MUST NOT alter the executed
  SQL; parser sees them as literal string values.

Note: read-side inline SQL that concatenates *internal* identifiers
(view names, dataset names from env) is fine because those inputs are
not user-controllable. This invariant scopes to user-supplied fields on
mutation endpoints.

