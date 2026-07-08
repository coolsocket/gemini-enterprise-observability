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

## INV-obs-007: identity resolution is single-sourced

`apps/api/contexts/observability/domain/identity.py::IdentityResolver`
is the ONE place where `(principalEmail, principalSubject)` →
`Identity` classification lives. Adding a new IdP (Okta, Microsoft,
Ping, …) is exactly:

  1. Add a value to `IdentityKind` enum.
  2. Add a `ResolverRule` before the generic rules in `DEFAULT_RULES`.
  3. Add a parametrize fixture in `test_identity_resolver.py`.
  4. If the new IdP surfaces a new pool-name pattern, use that as the
     predicate (see `_is_wif_okta` / `_is_wif_azure` for the pattern).

**Contract**: `Identity.actor_id` MUST be the same string across
Path 2 (user_activity.useriamprincipal) and Path 3 (audit.
principalSubject) for the same person. This is what makes
`v_user_usage ↔ v_data_access` JOINs unify chat activity per user.

SQL views retain their COALESCE + REGEXP_EXTRACT fallback (see
INV-obs-005) because BQ Scheduled Queries run without Python
mediation — the two layers must AGREE on the extracted actor_id
form. Any future rule change that shifts actor_id extraction (e.g.
switching from `subject/([^/]+)$` to hashed IDs) MUST update both
the Python resolver AND the SQL COALESCE together.

- **Code:** `apps/api/contexts/observability/domain/identity.py`
- **Test:** `tests/unit/test_identity_resolver.py` (20+ fixtures)

## INV-obs-006: v_user_persona chat MUST fall back to Path 3 audit

Tenants without "Prompt & Response Logging" enabled in GE Admin
Console have Path 2 (`user_activity`) empty for chat activity —
StreamAssist events only land in Path 3 (audit `data_access`).

v_user_persona's `chat` CTE (Path 2 source) MUST be joined with an
`audit_chat` CTE (Path 3 source, from v_data_access_summary) and
the numeric metrics merged via GREATEST. Persona classification
threshold WHEN clauses (POWER_USER, ACTIVE_CONSUMER, TRIAL) MUST
consume the GREATEST-merged value, not raw chat.chat_turns_*.

**Violation shape**: verified on responsive-lens-421108 (mirrored
into ge_demo_readonly 2026-07-07). Actor 11126728 had 18 chat +
9 DR in v_data_access_summary but v_user_persona.chat_turns_total = 0,
classified LURKER. 101 of 104 real OIDC users incorrectly LURKER.
After fix: 19 ACTIVE_CONSUMER + 35 TRIAL surfaced.

GREATEST (not SUM) because when both P&R and audit logging are on,
the same StreamAssist event is logged in both paths — SUM would
double-count. audit is a superset when both on.

- **Code:** `infra/sql_templates/views.sql.tmpl` → v_user_persona
- **Test:** `tests/unit/test_user_persona_chat_from_audit.py`

## INV-obs-005: audit views MUST resolve principal via canonical_actor UDF

Every view that reads `protopayload_auditlog.authenticationInfo.
principalEmail` in a projection MUST route through the `canonical_actor`
UDF (defined at top of `views.sql.tmpl`):

```sql
`{{PROJECT}}.{{DATASET}}.canonical_actor`(
  protopayload_auditlog.authenticationInfo.principalEmail,
  protopayload_auditlog.authenticationInfo.principalSubject
)
```

The UDF's body (single source of truth for the extraction form):
```sql
CREATE OR REPLACE FUNCTION `{{PROJECT}}.{{DATASET}}.canonical_actor`(email STRING, subject STRING) AS (
  COALESCE(
    email,
    REGEXP_EXTRACT(subject, r'subject/([^/]+)$'),
    REGEXP_EXTRACT(subject, r'serviceAccounts/([^/]+)')
  )
);
```

If you edit the UDF body, ALSO update the Python IdentityResolver
(`apps/api/contexts/observability/domain/identity.py`) so both
layers agree on actor_id extraction. INV-obs-007 owns that contract.

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
