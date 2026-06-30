# GE Observability

Internal dashboard for **Gemini Enterprise** adoption + governance + audit, built on Cloud
Logging → BigQuery → React/FastAPI.

Answers questions like:
- 谁是 BUILDER / ACTIVE_CONSUMER / TRIAL / LURKER 用户？
- 谁建了哪个 agent / engine / data store？
- 用户问了什么 prompt，模型答了什么？
- 哪个 engine 最受欢迎？
- 哪些 seat 占用了但没用？

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ 1) GE 用户操作                                                    │
│    users → GE 控制台 → 后端 API                                                      │
│    或：客户/sim SA → curl → Discovery Engine REST API             │
└──────────────────────────────────┬──────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────┐
│ 2) Discovery Engine 后台 emit 5 类日志到 Cloud Logging           │
│                                                                   │
│  Path 2 (业务日志, GE Admin Console 3 开关控制):                  │
│  • discoveryengine.googleapis.com/gemini_enterprise_user_activity│
│  • discoveryengine.googleapis.com/gen_ai.user.message            │
│  • discoveryengine.googleapis.com/gen_ai.choice                   │
│                                                                   │
│  Path 3 (审计日志, GCP 平台层):                                   │
│  • cloudaudit.googleapis.com/activity (默认开)                    │
│  • cloudaudit.googleapis.com/data_access (要手动启)               │
└──────────────────────────────────┬──────────────────────────────┘
                                   ↓ Logs Router sink
┌──────────────────────────────────────────────────────────────────┐
│ 3) BigQuery dataset: ge_observability                            │
│    • 5 张原始表（sink 自动落）                                    │
│    • 13 个分析 view（v_*）                                        │
│    • 13 个 snapshot 表（s_*，每 6h 由 Scheduled Query 物化）      │
│    • engine_metadata + resources_alive + quota_config             │
└──────────────────────────────────┬──────────────────────────────┘
                                   ↓ google-cloud-bigquery
┌──────────────────────────────────────────────────────────────────┐
│ 4) FastAPI (Cloud Run, IAM 限定 invoker)                         │
│    GET /api/v/{view}?origin=&engine_id=&live=                    │
│    POST /api/refresh                                              │
└──────────────────────────────────┬──────────────────────────────┘
                                   ↓ fetch()
┌──────────────────────────────────────────────────────────────────┐
│ 5) React SPA (中/EN 双语) → 浏览器                                │
└──────────────────────────────────────────────────────────────────┘
```

---

## Repo layout

```
ge-observability-service/
├── apps/
│   ├── api/                  FastAPI backend
│   │   ├── main.py
│   │   └── requirements.txt
│   └── web/                  React + Vite + Tailwind frontend
│       ├── src/
│       │   ├── pages/        Overview / Persona / Conversations / ...
│       │   ├── components/   Sidebar / Header / Card / ...
│       │   ├── i18n.tsx      中/EN dictionary + LangToggle
│       │   └── origin.tsx, engine.tsx  React contexts
│       └── package.json
├── infra/
│   ├── sql_templates/views.sql.tmpl    13 views parameterized with {{PROJECT}}/{{DATASET}}
│   └── scripts/apply_views.py          render + apply
├── terraform/
│   ├── main.tf               BQ dataset + sink + audit-config + Cloud Run + IAM
│   ├── variables.tf
│   ├── terraform.tfvars.example
│   └── README.md
├── docs/
│   ├── ARCHITECTURE.md       This file's deep-dive
│   ├── RUNBOOK.md            "the snapshot pipeline failed, how do I debug"
│   └── GE_CONSOLE_SETUP.md   Step-by-step screenshots for the 3 GE toggles
├── Dockerfile                Multi-stage: node build + python runtime
├── .dockerignore
├── Makefile                  install / serve / dev / tunnel-info
└── README.md                 (this file)
```

---

## Quick start (existing project)

```bash
# 1. Local dev
make install
make serve PORT=8011

# Open SSH tunnel from laptop:
ssh -L 8011:127.0.0.1:8011 <host>
open http://localhost:8011
```

## Quick start (new project, full Terraform)

**One-shot deploy** (assumes you have `gcloud` + `terraform` installed and authed):

```bash
make deploy PROJECT=my-project REGION=us-central1
```

This runs in order:

1. `terraform apply` — creates dataset, 5 metadata tables, sink, audit config, SA, Cloud Run, IAM, Scheduled Query
2. `gcloud builds submit` — builds + pushes container image
3. `apply_views.py` — renders + applies 15 BQ views with placeholders
4. `bootstrap.py` — ingests engine_metadata + resources_alive + seeds quota_config

After this you still need to **manually**:

- **Enable GE Admin Console toggles** for each engine you want to observe
  (see `docs/GE_CONSOLE_SETUP.md`)
- **Add IAP invokers** to `terraform/terraform.tfvars` and re-apply if you want SSO instead
  of native Cloud Run IAM

Then:

```bash
gcloud run services proxy ge-observability --port 8080 --region $REGION
open http://localhost:8080
```

### Step-by-step (if `make deploy` fails partway)

```bash
make tf-plan   PROJECT=my-project    # preview
make tf-apply  PROJECT=my-project    # provision infra
# (manually enable GE Console toggles here, wait for logs to land)
make image     PROJECT=my-project    # build container
make views     PROJECT=my-project    # apply BQ views
make bootstrap PROJECT=my-project    # ingest metadata
```

---

## Required GE Admin Console toggles

These are **NOT** automatable from API. Must be done by a GE admin per engine.

| Toggle | Effect |
|---|---|
| Enable OpenTelemetry Instrumentation | Generates trace IDs for chat requests |
| Enable Prompt and Response Logging | Writes gen_ai.user.message and gen_ai.choice logs |
| Enable Feedback | Captures thumbs-up/down events (optional, may not exist on all engines) |

See `docs/GE_CONSOLE_SETUP.md` for screenshots.

---

## Documented data limitations

1. **Multimodal**: GE `streamAssist` API does not accept `inlineData` parts (image/file).
   File uploads go through a separate session-file flow; signal via `session_files` count
   in `v_data_access_summary`. **You cannot see what image a user uploaded.**

2. **trace_id linkage**: Only `v1alpha` (REST) chat calls produce `gen_ai.choice` logs with
   matching `trace_id`. Calls via the GE Console UI (`v1main`) write `user_activity` logs
   but no `choice` logs — so prompts from the GE web app appear with `join_status='no_response'`
   in `v_conversations_with_response`.

3. **Deep Research (AsyncAssist)**: GE Deep Research uses `AssistantService.AsyncAssist`
   + `ReadAsyncAssist`. These calls appear in `cloudaudit_googleapis_com_data_access`
   (Path 3), so the dashboard counts them per user/engine in
   `v_data_access_summary.deep_research_calls`. **But the prompt + response text are NOT
   emitted to `gen_ai.user.message` / `gen_ai.choice`** (same fundamental limitation as the
   GE web UI). To see actual research content, use the Deep Research task list in the GE admin
   console.

   See also `v_agentspace_navigation_summary.deep_research_visits` — counts how many times
   each user *opened the Deep Research page*, independent of whether they actually submitted
   a research task.

4. **NotebookLM Enterprise**: methods live under `google.cloud.notebooklm.v1main.*`
   (not `v1alpha` as the public docs imply — empirically `v1main` is what the UI emits).
   Six services observed: `NotebookService`, `SourceService`, `NoteService`, `ArtifactService`,
   `AudioOverviewService`, `AccountService`. All inside `serviceName="discoveryengine.googleapis.com"`
   (no separate `notebooklm.googleapis.com`). The dashboard buckets them into 3 columns:
   `notebooklm_{notebook,content,audio}_ops`. NotebookLM rows appear with `engine_id=NULL`
   because notebook resource names don't include `/engines/`.

   ⚠️ Service accounts CANNOT trigger NotebookLM via REST — methods only respond to UI
   sessions. Same for Deep Research. To 'test the dashboard' you must use the GE web UI.
   "User opened the NotebookLM home page" is also captured separately as
   `v_agentspace_navigation_summary.notebooklm_visits`.

5. **A2A agent invocation**: marketplace agents (Microsoft 365 / Salesforce / Jira) and
   custom agents invoked via the A2A protocol go through
   `assistants.agents.a2a.v1.{message,tasks}.*`. Bucketed as
   `v_data_access_summary.a2a_invocations`. The specific agent ID is in `resourceName`
   (parse from `…/assistants/*/agents/<AGENT_ID>/…`) — currently not surfaced as a separate
   per-agent breakdown.

6. **Other special agents (Idea Generation, Co-Scientist, AlphaEvolve)**: these flow through
   `AssistantService.StreamAssist` and are **NOT distinguishable from regular chat** at the
   audit-log method-name level. The agent reference is in the request body (`request.agentsConfig`
   or similar). To break them out you'd need to enable DATA_WRITE audit logging with request
   payload capture — not done by default.

7. **Custom user-built agents — view-only navigation**: when a user clicks into a custom
   agent's detail page in GE, we capture `agentinfo.{agentid, name}` via
   `v_agentspace_navigation` (the GE web UI emits a WriteUserEvent). That tells us *who opened
   which agent*, but not whether they actually invoked it. Actual invocation either goes
   through StreamAssist (lumped with chat) or A2A (counted in `a2a_invocations`).

8. **Create events lack resource ID**: `CreateAgent` audit log's `resourceName` is the
   parent (`assistants/default_assistant`), not the new agent's ID. So per-actor "alive
   resources" can't be attributed back to who created what. The Overview page shows a
   system-wide alive count via direct `ListAgents` API.

9. **PII in prompts**: `v_conversations` applies regex redaction for emails, phone numbers,
   ID-like numbers, and credit-card-like numbers. **It is not a full DLP** — long-form PII
   (names, addresses) is NOT redacted. For production: layer Cloud DLP API on top.

10. **No public GE seat/license API**: "purchased seats" is a manual config value in
   `quota_config` table. "Claimed" derived from distinct active actors in 30 days.

---

## Languages

UI supports 中文 + English. Toggle in top-right (中 / EN buttons). Persisted via
localStorage. Add new locales by extending `apps/web/src/i18n.tsx`.

---

## Authentication

The Cloud Run service runs with `--no-allow-unauthenticated`. Only members with
`roles/run.invoker` on the service can hit it.

For local browser access:
```bash
gcloud run services proxy ge-observability --port 8080 --region us-central1
# Then open http://localhost:8080 in browser
```

For production: layer **Cloud IAP** on top (set up via Cloud Console → Security → IAP).
Restrict to specific groups via `iap_invokers` in `terraform/variables.tf`.

---

## Operational tasks

- **Refresh snapshots manually**: click ⟳ button in dashboard header (or POST /api/refresh)
- **Scheduled refresh**: BQ Scheduled Query runs every 6 hours (see Settings → Snapshot status)
- **Add a simulated user**: see `docs/RUNBOOK.md#simulate-users`
- **Onboard a new engine**: re-run `infra/scripts/apply_views.py` (the engine_metadata table syncs on demand)

---

## License & ownership

Built by Claude Code (Opus). MIT license. Contributions welcome.
