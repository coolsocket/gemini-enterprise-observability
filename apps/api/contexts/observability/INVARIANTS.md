# Observability invariants

Invariants owned by this context. Every one has a test — if you change
the behavior, either update the invariant here (with a link to the ADR)
or update the test. Don't silently drift.

## INV-obs-001: `_rows()` falls back to live view on missing snapshot

On fresh deploys the `s_*` snapshot tables don't exist until BQ Scheduled
Query has ticked (~6h) or someone POSTs `/api/refresh`. `_rows()` MUST
catch `google.api_core.exceptions.NotFound` on the snapshot query and
retry against the live `v_*` view. Without this, every dashboard tab
returns HTTP 500 until the first snapshot refresh.

- **Code:** `apps/api/routes/observability.py::_rows`
- **Domain support:** `apps/api/contexts/observability/domain/query_builder.py::render_live_fallback_sql`
- **Test:** `tests/unit/test_snapshot_fallback.py`

The same fallback applies to `summary()` (which runs a CTE across five
snapshot tables — any one missing triggers NotFound). It re-invokes
itself with `live=True` instead of pointing at a single fallback view.

## INV-obs-002: `refresh_now()` pre-checks INFORMATION_SCHEMA

Some `v_*` views may not exist yet on a fresh deploy (their source
log-sink tables haven't materialized — see `apply_views.py`'s
graceful-skip logic). Refresh MUST filter the iteration via
`INFORMATION_SCHEMA.VIEWS` and skip missing ones with INFO logs
(`snapshot skipped: … view not built yet`), reserving `log.error` for
genuine problems (permission, SQL syntax, quota).

- **Code:** `apps/api/routes/refresh.py::refresh_now`
- **Test:** `tests/unit/test_refresh_skips_missing_views.py`

## INV-obs-003: `/api/user/{email}` honors `live` uniformly

Every `FROM` clause inside `user_deep_dive` MUST route through the
`tbl()` lambda so `?live=false` (default) reads snapshots consistently
and `?live=true` reads live views consistently. A single hardcoded
`{PROJECT}.{DATASET}.v_*` inside the queries dict silently bypasses
the operator's choice and creates two anomalies:

  - `live=false` still hits BQ live for that one panel — defeats the
    whole point of snapshotting.
  - The panel's freshness diverges from the rest of the page.

Exception: `agentspace_events` legitimately queries the raw
`discoveryengine_googleapis_com_gemini_enterprise_user_activity` sink
table directly — there is no `v_*` for the un-aggregated stream.

- **Code:** `apps/api/routes/observability.py::user_deep_dive`
- **Test:** `tests/unit/test_user_deep_dive_live_flag.py`

## INV-obs-005: audit views MUST resolve principal via COALESCE

Every view that reads `protopayload_auditlog.authenticationInfo.
principalEmail` in a projection MUST COALESCE it with subject-extraction
from `principalSubject`:

```sql
COALESCE(
  protopayload_auditlog.authenticationInfo.principalEmail,
  REGEXP_EXTRACT(
    protopayload_auditlog.authenticationInfo.principalSubject,
    r'subject/([^/]+)$'
  )
)
```

**Violation shape**: on a tenant that authenticates users via OIDC or
Workforce Identity Federation, `principalEmail` is NULL for real users.
Only `principalSubject` carries the identity, in the shape
`principal://iam.googleapis.com/locations/global/workforcePools/POOL_ID/subject/SUBJ_ID`.
Verified on responsive-lens-421108 (2026-07-07): 997/1000 audit rows
had NULL principalEmail; extracting `subject/([^/]+)$` recovered 73
distinct actors and 40+ users in v_data_access_summary that were
previously invisible.

The extracted subject ID matches the numeric OIDC principal already
used in `user_activity.jsonPayload.useriamprincipal` — so JOINs across
Path 2 (user_activity) and Path 3 (audit) unify to the same actor.

Every `WHERE …principalEmail IS NOT NULL` MUST also use the COALESCEd
expression, otherwise OIDC rows get filtered out AFTER the SELECT
recovers them.

- **Code:** `infra/sql_templates/views.sql.tmpl` — every audit-log view
  (v_admin_activity, v_data_access, v_deep_research_prompts)
- **Test:** `tests/unit/test_audit_principal_subject_coalesce.py`

## INV-obs-004: lifespan is the startup hook

App startup work MUST be wired through FastAPI's lifespan context
manager, not `app.add_event_handler("startup", …)`. The event-handler
form AttributeErrors on some FastAPI/starlette version combos in the
wild (reported on responsive-lens-421108, 2026-07-07). Lifespan is
the officially supported cross-version hook.

- **Code:** `apps/api/main.py::lifespan`
- **Test:** `tests/unit/test_lifespan_not_add_event.py`
