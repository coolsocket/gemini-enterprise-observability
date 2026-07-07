# Deploy invariants

Invariants that MUST hold for `make deploy-infra` and friends to be
safe / non-surprising. Each has a corresponding test in tests/unit/.

## INV-001: BQ_LOCATION follows REGION by default

If the operator explicitly sets `REGION` (either on the make command
line or in `.env`) but does not explicitly set `BQ_LOCATION`,
`BQ_LOCATION` MUST resolve to `REGION`. `.env.example` MUST NOT ship
a hardcoded `BQ_LOCATION=US` default, because that value survives a
`cp .env.example .env` and silently mismatches any non-us REGION the
operator later picks.

**Violation shape**: operator runs `make deploy-infra REGION=asia-southeast1`
after `make install` created their `.env` from the template. Preflight
correctly refuses because `.env` still has `BQ_LOCATION=US`. Operator
did nothing wrong; the template default betrayed them.

**Correct behavior**: `.env.example`'s BQ_LOCATION line is commented
out (or absent) so new users inherit the REGION-derived default from
Makefile. Explicit multi-region ("US" / "EU" / "asia") stays available
as an explicit opt-in for advanced users.

**Rationale**: Data-residency intent (data in region X, compute in
region Y) is a legitimate but rare configuration. Making it the
DEFAULT behavior surprises 90%+ of deployers. The default should
be "everything co-located". Advanced users can opt into
cross-region by setting BQ_LOCATION explicitly.

## INV-002: DTS service agent gets TokenCreator on dashboard SA

If `enable_scheduled_refresh = true`, terraform MUST grant
`roles/iam.serviceAccountTokenCreator` on `google_service_account.dashboard_sa`
to `service-<project_number>@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com`.
Test: `tests/unit/test_scheduled_refresh_iam.py`.

**Violation shape**: fresh deploy sets `enable_scheduled_refresh = true`.
Terraform apply succeeds, but the first scheduled refresh fails with
`Error code 9 : DTS service agent needs iam.serviceAccounts.getAccessToken
permission on ge-observability-sa@…`. Operator now has to debug an IAM
error from a service-account they never asked to know about.

**Correct behavior**: on the same apply that creates the scheduled query,
create (a) the DTS service agent via `google_project_service_identity`
and (b) the `google_service_account_iam_member` grant. Both are
gated on `enable_scheduled_refresh` so operators who only use manual
`POST /api/refresh` don't pay for these extra IAM resources.

## INV-003: snapshot_refresh.sql.tftpl view list ⊆ views.sql.tmpl definitions

Every `v_*` that the scheduled query references in a `FROM` clause MUST
also be defined by `CREATE OR REPLACE VIEW` in `infra/sql_templates/views.sql.tmpl`.
Test: `tests/unit/test_snapshot_tftpl_view_drift.py`.

**Violation shape**: someone adds `s_foo` to the tftpl during a demo,
forgets to add the underlying view definition, ships it. Next
scheduled refresh fails with `Table … was not found`. The two files
live in different directories and drift silently.

**Correct behavior**: static test asserts subset relationship. To add
a new snapshot, add its view definition FIRST, verify it, then add
the `CREATE OR REPLACE TABLE ... AS SELECT * FROM v_new` line.
