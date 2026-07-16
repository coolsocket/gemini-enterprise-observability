# Known Limitations

> Grouped into four buckets so you can jump to the relevant caveat when debugging. See [CHANGELOG](../CHANGELOG.md) for how each of these evolved.

Everything the dashboard surfaces is grounded in what GE actually emits. These are the things it **can't** see or do — grouped so you can find the relevant one fast.

### Data — signals GE doesn't emit

1. **Chat prompt ↔ response pairing** (mostly solved as of 2026-07-06). Two paths now: (a) `v1alpha` REST calls produce paired `gen_ai.choice` logs (matched by `trace_id`, gives full reasoning + finish_reason); (b) UI calls (`v1main`) don't write `gen_ai.choice`, but with `sensitiveLoggingEnabled=true` (auto-flipped by `bootstrap.py`) the model's response text lands inline in `jsonPayload.serviceTextReply` on the same `user_activity` row. `v_conversations_with_response` `COALESCE`s both. On our data this moved match rate from ~10% to ~60%. Remaining `no_response` rows are usually Deep Research responses (see below) or errors.

2. **Deep Research prompt + response content, plus counter honesty.** DR responses aren't emitted to Cloud Logging — content view still requires the GE admin console. **On counting**: `AssistantService.AsyncAssist` is our proxy for "one Deep Research submit", but GE (as of 2026-07) fires AsyncAssist alongside plain chats too — a "check the weather" prompt triggered both `StreamAssist` AND `AsyncAssist` + `ReadAsyncAssist` at the same second (verified in production audit logs). `resourceName` is `.../assistants/default_assistant` in both cases so it can't discriminate. We now suppress DR prompt attribution when the candidate prompt already has a matched normal-chat response — but the AsyncAssist count itself may still be inflated. Bucket kept named `deep_research` for continuity; hint text warns of the imprecision.

3. **Image / video / idea generation.** GE runs these inside Google infrastructure without customer audit logs. Removed from the Quota dashboard on 2026-07-06 — the previous prompt-keyword heuristic misclassified prompts like "summarize this video". `tier_limit` rows in `quota_config` are preserved for revival if GE ever exposes real per-feature counters.

4. **Multimodal uploads.** `streamAssist` doesn't accept `inlineData`; files use a separate session-file flow. The dashboard shows `session_files` counts, not contents.

5. **Built-in agents indistinguishable from chat.** Idea Generation, Co-Scientist, AlphaEvolve all flow through `AssistantService.StreamAssist`. The agent reference is in the request body — separating them would need DATA_WRITE audit logging with payload capture (off by default).

6. **Custom agent invocation.** Opening the detail page emits `UserEventService.WriteUserEvent` with `agentinfo.{agentid,name}` (surfaced as nav events on the Agents page), but the actual invocation either goes through StreamAssist (lumped with chat) or A2A (in `a2a_invocations`).

7. **A2A per-agent breakdown.** A2A invocations are counted in aggregate as `a2a_invocations`, not per target agent yet.

8. **CreateAgent lacks the new agent's resource ID.** The audit log has the parent resource (`assistants/default_assistant`), not the new agent's ID. So per-creator "alive resources" can't be attributed. The Overview page falls back to a system-wide alive count via direct `ListAgents` API.

### API — what a service account can't do

9. **NotebookLM API is blocked for service accounts.** Even with a custom role granting all `discoveryengine.notebooks.*` permissions, SA calls return `403 "The caller does not have permission"`. The gate is at the NotebookLM service layer (workforce identity + Regional Access Boundary registry), not IAM. Attempting to bind the role surfaces this as a `Regional Access Boundary HTTP request failed... Account not found for email: <hash>|<user>` warning — cosmetic (the binding still succeeds) but signals the underlying gate. Full evidence: [`playground/de-api-probe/notebooklm-sa-gate.md`](../playground/de-api-probe/notebooklm-sa-gate.md).

10. **Deep Research REST API is blocked for SAs.** `AsyncAssist` doesn't exist in the public `v1alpha` Discovery Engine schema — it's UI-internal (`v1main`) and gated by the same workforce-identity check. SAs cannot submit DR programmatically. Existing DR from real users IS observable via audit log; we just can't generate it from code.

11. **Generated files can't be downloaded via API.** `StreamAssist` will happily produce an image (Nano Banana 2) or video and return a `fileId` in the stream response, but the download endpoints (`sessions/{sid}:listFiles`, `:getFile`, `:downloadFile`) all return `403 "Session is not owned by the provided user"` — same workforce gate. Files are only accessible in the GE UI. Full evidence: [`playground/ge-generation-probe/FINDINGS.md`](../playground/ge-generation-probe/FINDINGS.md).

12. **Deep Research vs Search vs grounded-answer are distinct services.** DR = `AssistantService.AsyncAssist`, Search API = `SearchService.Search`, grounded-answer = `ConversationalSearchService.GetAnswer`. Our counters keep them in separate buckets; DR is never conflated with Search.

### Deploy — manual steps outside our automation

13. **GE engine must be pre-provisioned.** This repo observes an existing GE deployment; it doesn't create one. Provision the engine in GE Admin Console first.

14. **GE Console toggles are mostly automated** (2026-07-06). `bootstrap.py` now `PATCH`es each engine's `observabilityConfig` field via the Discovery Engine API — `observabilityEnabled` (OpenTelemetry) + `sensitiveLoggingEnabled` (Prompt & Response Logging) flip on automatically. Only **"Enable Feedback"** still requires a manual click in GE Admin Console. Set `SKIP_OBSERVABILITY=true make bootstrap` to opt out of the automation. See [`docs/GE_CONSOLE_SETUP.md`](./GE_CONSOLE_SETUP.md).

15. **Sink target tables are lazy.** `cloudaudit_googleapis_com_data_access` and `discoveryengine_googleapis_com_*` are auto-created by BigQuery only when the first matching sink row arrives. `make deploy-views` reports which are still waiting and is idempotent — re-run once traffic flows.

16. **Cloud Run access needs manual IAP config.** Default `deploy_cloud_run = false`. Flipping it true creates the service, but you still need `iap_invokers = […]` in `terraform.tfvars` and (typically) Identity-Aware Proxy configuration for external access.

### Operational — freshness + performance

17. **Snapshot refresh cadence is 6h.** Dashboard pages read `s_*` snapshot tables. An in-process background loop re-materializes them every `SNAPSHOT_REFRESH_INTERVAL_SEC` (6h default), added 2026-07-15 after a reporter's dashboard froze at the last manual refresh: despite an earlier code comment, terraform creates **no** BigQuery Scheduled Query, so without this loop snapshots only refresh on manual `POST /api/refresh` and go stale the moment the last manual run ages out. The loop is the deploy-target-agnostic guarantee (Cloud Run / VM / local). Set `SNAPSHOT_REFRESH_INTERVAL_SEC=0` to disable it and drive refresh from Cloud Scheduler → `POST /api/refresh` or a BQ Scheduled Query instead. Manual refresh is still the Settings-page button. Live `v_*` views are always current but slower.

18. **Seat count refresh is 24h.** `licenseConfigs` is pulled at API startup and every 24h by a background asyncio task. Manual refresh: `POST /api/refresh/seats`. Cloud Run cold starts trigger a fresh fetch; long-lived processes stay accurate for a day.

19. **PII redaction is regex-only.** `v_conversations` redacts emails, phone numbers, ID-like numbers, and card-number-like sequences. **Not a full DLP** — names, addresses, and long-form PII pass through. For production, layer Cloud DLP on top.

20. **`quota_config.default_tier` drives seat-to-tier attribution.** Total quota is computed as `sum over tiers of (seats_in_tier × per_tier_limit)`. Explicit user tier assignments (in `user_tier` table) are honored; unassigned seats fall back to `quota.default_tier` (default `plus`). Change the default in the Quota page's tier config editor.

### History — how far back a fresh deploy can pull

21. **History reaches only as far as Cloud Logging retention, per log type.** The Log Router sink is **forward-only** — it captures events from sink-creation onward, nothing before. Pre-sink history is recoverable one time via `make backfill` (Cloud Logging `entries.list` → `MERGE ON insertId`, idempotent), but **only within Cloud Logging's retention window**, and the window differs by bucket:
    - `_Default` (30 days, adjustable) holds `gemini_enterprise_user_activity`, `gen_ai.*`, and `cloudaudit.../data_access` — i.e. **all chat / usage / prompt content**.
    - `_Required` (400 days, **locked** — can't be shortened) holds admin `cloudaudit.../activity` (CreateEngine, BatchUpdateUserLicenses, ACL changes).

    So on a fresh deploy a full pull recovers **~30 days of chat/usage** and **~400 days of admin operations** — no further. Anything older than the `_Default` window is **permanently gone** (not "not yet imported" — deleted at source). To keep more chat/usage history, **extend `_Default` retention (or route those logs to a long-retention custom bucket) _before_ it rolls off** — this cannot be done retroactively. Verified on a real tenant 2026-07-14.

22. **"Bought" ≠ "used" ≠ "retained" — usage history won't reach the purchase date.** Assigning licenses emits no usage logs; usage logs appear only when someone actually uses GE **and** observability/P&R logging is on. Real-tenant timeline (2026-07-14): engine + 404 licenses created **2026-06-10** (admin audit, still visible in the 400-day `_Required` bucket), but the earliest readable **chat** log is **2026-06-22** — a ~12-day gap from onboarding lag and/or P&R logging being enabled later, compounded by the 30-day `_Default` window having already purged everything before ~06-15. Don't expect the usage floor to line up with when the customer "bought" GE; expect it at `max(first-real-use, first-P&R-log, today − 30d)`.

23. **Backfilling Data Access logs needs `roles/logging.privateLogViewer`.** `cloudaudit.../data_access` are **private** logs — reading them via `entries.list` requires `logging.privateLogEntries.list`, a level above the ordinary `logging.logEntries.list` in `roles/logging.viewer`. A read-only identity with only `logging.viewer` sees `user_activity` + admin `activity` but gets **nothing** for `data_access` (verified: yehao User ADC on vivo). The deploy grants `privateLogViewer` to the sink runner; an operator running `backfill.py` by hand against a locked-down project needs it explicitly, or `data_access`-derived panels come back empty with no error.

24. **Prompt→user attribution is impossible on OIDC/WIF tenants.** On Workspace tenants the prompt and the caller land on the same `user_activity` row (`request.query` populated) — attribution works (see item 1). On **OIDC/WIF** tenants (numeric subject IDs, e.g. vivo) GE writes `request.query = null` on `StreamAssist` and routes the prompt text to `gen_ai.user.message`, which carries **no identity field** (no `useriamprincipal`, `operation=null`; only engine/agent/assistant labels + content). The lone shared column is `trace`, populated on ~0.4% of `user_activity` rows (verified: 32 of 8,596; only 7 overlap the 254K `gen_ai` rows). So "user X asked Y" is **not reconstructable** — you can list prompts by engine/agent (anonymous) and per-user activity counts, but not link the two. Resolving it needs a Google-side change (identity on `gen_ai.user.message`, or `request.query` populated in `user_activity` for OIDC tenants).


