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

## INV-deploy-backfill: historical log import is idempotent + gap-free

`infra/contexts/deploy/application/backfill.py` (invoked via
`make backfill DAYS=<n>`) MUST preserve two guarantees so operators
can run it any number of times without harm:

1. **No duplicate rows**: the MERGE MUST match on `insertId`
   (Cloud Logging's unique per-entry UUID, verified present in both
   API responses and sink target rows). Any other match key (timestamp
   / logName+timestamp) risks either dup or drop.

2. **No gap at sink boundary**: the read window's tail deliberately
   extends past `MIN(sink_ts)` by `OVERLAP_WINDOW` (currently 1h).
   Log-pipeline latency can lag a few minutes at the boundary; without
   the overlap, boundary entries fall in the gap. The MERGE handles
   the resulting dup rows.

3. **Filter parity**: `SINK_FILTER_TEMPLATE` in backfill.py MUST
   remain byte-identical (after `{project_id}` substitution) to the
   filter installed in terraform's `google_logging_project_sink`
   resource. Any drift means backfill fetches a different subset than
   the sink stores. Locked by
   `tests/unit/test_backfill.py::test_backfill_filter_matches_terraform_sink`.

**Violation shape**: without insertId MERGE, a re-run of `make backfill`
would double every row in the target tables — dashboards would show
2×/3×/N× inflated counts silently. Without the overlap window, the
first few minutes of sink coverage overlap with the last few minutes
of backfill coverage inconsistently — some boundary entries drop.

**Actual limits (documented for operators)**:
- Bounded by Cloud Logging `_Default` bucket retention (default 30d)
- Bounded by exclusion filters on `_Default` — if org policy excludes
  discoveryengine logs, backfill will report 0 fetched (as it should)
- Bounded by Cloud Logging API rate limits (60 req/sec/project) —
  backfill.py handles 429 with exponential backoff (up to 4 retries)

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
