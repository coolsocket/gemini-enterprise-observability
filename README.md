# GE Observability

> **Language**: English · [中文](./README.zh-CN.md)

Self-hosted dashboard for **Gemini Enterprise** adoption, governance, and audit.
Pipes Cloud Logging → BigQuery → React + FastAPI.

Answers questions like:
- Who's a **power user / active consumer / trial / lurker**?
- Who built which **agent / engine / data store**?
- What **prompts** did users send, and what did the model answer?
- Which **engine** is most popular?
- Which **seats** are claimed but unused?
- How many **Deep Research / NotebookLM / custom agent** calls — and by whom, exactly which calls?

---

## Pages

| Page | What it shows |
|---|---|
| **Overview** | DAU trend, persona donut, audit/usage KPIs, engine list, data freshness |
| **User picker** | Sortable + searchable directory: every user × every feature they touched |
| **User deep dive** | One user, every metric drillable to the underlying audit events |
| **Agent dashboard** | Per-agent rollup (Deep Research / NotebookLM / custom), user breakdown, event timeline |
| **Conversations** | Prompt + response bubbles, filter by matched / prompt-only |
| **Data Access** | Per-method audit-log bucketing with NotebookLM, A2A, Deep Research columns |
| **Files & Agents** | Session file activity + custom agent navigation |
| **Builders** | Who created / updated / deleted which resources |
| **Admin Activity** | Path 3 audit-log timeline |
| **Settings** | Quota config + snapshot refresh status + data source config |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ 1) GE user actions                                               │
│    Users → GE Console UI    /    REST clients → Discovery Engine │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────┐
│ 2) Discovery Engine emits logs to Cloud Logging                  │
│                                                                  │
│   Path 2 — business logs (toggled in GE Admin Console):          │
│   • discoveryengine.googleapis.com/gemini_enterprise_user_activity │
│   • discoveryengine.googleapis.com/gen_ai.user.message           │
│   • discoveryengine.googleapis.com/gen_ai.choice                 │
│                                                                  │
│   Path 3 — audit logs (GCP platform):                            │
│   • cloudaudit.googleapis.com/activity     (default on)          │
│   • cloudaudit.googleapis.com/data_access  (must enable)         │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ Logs Router sink
┌──────────────────────────────────────────────────────────────────┐
│ 3) BigQuery dataset: ge_observability                            │
│    • 5 raw tables (auto-populated by sink)                       │
│    • 18 analytical views (v_*)                                   │
│    • 18 materialized snapshots (s_*, refreshed every 6h)         │
│    • engine_metadata + resources_alive + quota_config            │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ google-cloud-bigquery
┌──────────────────────────────────────────────────────────────────┐
│ 4) FastAPI on Cloud Run (IAM-restricted invoker)                 │
│    GET /api/v/{view}?origin=&engine_id=&live=                    │
│    GET /api/user/{email}      — single-user deep dive            │
│    GET /api/agent/{agent_id}  — single-agent rollup              │
│    POST /api/refresh          — re-materialize snapshots         │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ fetch()
┌──────────────────────────────────────────────────────────────────┐
│ 5) React 18 + Vite + Tailwind (中 / EN i18n) → browser           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Deploying to your GCP project

**One-shot** (assumes `gcloud` authed, `terraform` installed, GE engine already provisioned):

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability
make deploy PROJECT=my-project REGION=us-central1
```

This runs in order:

1. `terraform apply` — enables 9 APIs, creates BQ dataset + 5 metadata tables + sink + audit config + service account + Cloud Run + optional Scheduled Query
2. `gcloud builds submit` — builds + pushes the container image
3. `apply_views.py` — renders + applies 18 BigQuery views (templated with `{{PROJECT}}` / `{{DATASET}}` / `{{SIM_PATTERN}}`)
4. `bootstrap.py` — ingests `engine_metadata`, `datastore_metadata`, `resources_alive` via the Discovery Engine API; seeds `quota_config`

Two manual steps remain:

1. **Enable GE Admin Console toggles** per engine — see [`docs/GE_CONSOLE_SETUP.md`](./docs/GE_CONSOLE_SETUP.md):
   - Enable OpenTelemetry Instrumentation (generates trace IDs)
   - Enable Prompt & Response Logging (writes `gen_ai.user.message` and `gen_ai.choice`)
   - Enable Feedback (optional)
2. **Add invokers** to `terraform/terraform.tfvars` (`iap_invokers = ["user:alice@example.com", …]`), then `make tf-apply` again

Then open the dashboard:

```bash
gcloud run services proxy ge-observability --port 8080 --region us-central1
open http://localhost:8080
```

### Step-by-step (if `make deploy` fails partway)

```bash
make tf-plan   PROJECT=my-project    # preview infra
make tf-apply  PROJECT=my-project    # provision infra
# (manually flip GE Console toggles here; wait a few min for first logs)
make image     PROJECT=my-project    # build + push container
make views     PROJECT=my-project    # apply 18 BQ views
make bootstrap PROJECT=my-project    # ingest metadata
```

---

## Local development

```bash
make install                              # python venv + npm deps
make api-run                              # FastAPI on http://127.0.0.1:8000
# in another terminal:
cd apps/web && npm run dev                # Vite with HMR
```

Or single-process preview (built frontend served by FastAPI):

```bash
make serve PORT=8011
ssh -L 8011:127.0.0.1:8011 <remote-host>  # if running on a remote box
open http://localhost:8011
```

---

## Repo layout

```
ge-observability-service/
├── apps/
│   ├── api/                              # FastAPI backend
│   │   ├── main.py
│   │   └── requirements.txt
│   └── web/                              # React 18 + Vite + Tailwind frontend
│       ├── src/pages/                    # Overview · UserDeepDive · Agents · Conversations · …
│       ├── src/components/               # Sidebar · Header · Card · DataTable · Brand
│       └── src/i18n.tsx                  # 中 / EN dictionaries
├── infra/
│   ├── sql_templates/views.sql.tmpl      # 18 views parameterized with {{PROJECT}} / {{DATASET}} / {{SIM_PATTERN}}
│   └── scripts/
│       ├── apply_views.py                # render + apply views to BigQuery
│       └── bootstrap.py                  # ingest engine/datastore/agent metadata
├── terraform/
│   ├── main.tf                           # APIs + dataset + sink + audit + SA + Cloud Run + Scheduled Query
│   ├── variables.tf
│   ├── terraform.tfvars.example
│   ├── snapshot_refresh.sql.tftpl        # template for the every-6h re-materialize query
│   └── README.md
├── docs/
│   ├── RUNBOOK.md                        # operational tasks + troubleshooting
│   └── GE_CONSOLE_SETUP.md               # the 3 toggles a GE admin must flip
├── Dockerfile                            # multi-stage: node build + python runtime
├── Makefile                              # install / serve / dev / deploy / tf-* / image / views / bootstrap
└── README.md                             # ← this file
```

---

## Documented data limitations

The dashboard surfaces every signal GE actually emits. These are the things it **can't** see, and why:

1. **Multimodal**: `streamAssist` doesn't accept `inlineData`. Image / file uploads use a separate session-file flow. The dashboard surfaces file activity as `session_files` counts, but you can't see *what* was uploaded.

2. **trace_id linkage**: Only `v1alpha` (REST) chat calls produce paired `gen_ai.choice` logs. UI calls go through `v1main`, which writes `user_activity` but no `choice` — so prompts from the GE web app appear as `join_status='no_response'`. The Conversations page makes this visually obvious with a "✓ matched / prompt-only" filter.

3. **Deep Research (AsyncAssist)**: GE Deep Research uses `AssistantService.AsyncAssist` + `ReadAsyncAssist`. These calls appear in `cloudaudit_googleapis_com_data_access`, so the dashboard counts them per user/engine. **But the prompt + response text are NOT emitted** — same limitation as the UI path. To see actual research content, use the Deep Research task list in the GE admin console.

4. **NotebookLM Enterprise**: methods live under `google.cloud.notebooklm.v1main.*` (not `v1alpha` as the public docs imply — empirically `v1main` is what the UI emits). Six services observed: `NotebookService`, `SourceService`, `NoteService`, `ArtifactService`, `AudioOverviewService`, `AccountService`. All inside `serviceName="discoveryengine.googleapis.com"`. Bucketed into `notebooklm_{notebook,content,audio}_ops`. NotebookLM rows appear with `engine_id=NULL` because notebook resource names don't include `/engines/`.

   ⚠ Service accounts **cannot** trigger NotebookLM or Deep Research via REST — these methods only respond to authenticated UI sessions. To exercise the dashboard, you must use the GE web UI.

5. **A2A agent invocation**: marketplace + custom agents invoked via A2A go through `assistants.agents.a2a.v1.{message,tasks}.*`. Bucketed as `a2a_invocations`. Per-agent breakdown not yet surfaced.

6. **Other built-in agents (Idea Generation, Co-Scientist, AlphaEvolve)**: these flow through `AssistantService.StreamAssist` and are **not distinguishable from regular chat** at the method-name level. The agent reference is in the request body — would need DATA_WRITE audit logging with payload capture to break them out.

7. **Custom agent — view-only navigation**: when a user clicks a custom agent's detail page, we capture `agentinfo.{agentid, name}` via `UserEventService.WriteUserEvent`. That tells us *who opened which agent* but not whether they actually invoked it. Actual invocation either goes through StreamAssist (lumped with chat) or A2A (in `a2a_invocations`).

8. **Create events lack resource ID**: `CreateAgent`'s audit log has the parent resource (`assistants/default_assistant`), not the new agent's ID. So per-actor "alive resources" can't be attributed back to who created what. The Overview shows a system-wide alive count via direct `ListAgents` API.

9. **PII in prompts**: `v_conversations` applies regex redaction for emails, phone numbers, ID-like numbers, and credit-card-like numbers. **Not a full DLP** — long-form PII (names, addresses) is not redacted. For production, layer Cloud DLP on top.

10. **No public seat/license API**: "purchased seats" is a manual value in `quota_config`. "Claimed" is derived from distinct active actors in the last 30 days.

---

## Authentication

Cloud Run runs with `--no-allow-unauthenticated`. Only `roles/run.invoker` holders can hit it.

- **Quick local browser access**:
  ```bash
  gcloud run services proxy ge-observability --port 8080 --region us-central1
  ```
- **Production SSO**: layer Cloud IAP via the Cloud Console (Security → Identity-Aware Proxy), then add your groups to `iap_invokers` in `terraform/terraform.tfvars`.

---

## Operational tasks

- **Manual snapshot refresh**: click ⟳ in the dashboard header (or `POST /api/refresh`)
- **Scheduled refresh**: BigQuery Scheduled Query runs every 6h (set `enable_scheduled_refresh = true` in `terraform.tfvars` after `make views` has run once)
- **Add a simulated user**: see [`docs/RUNBOOK.md#simulate-users`](./docs/RUNBOOK.md)
- **Onboard a new engine**: re-run `make bootstrap PROJECT=…` to sync `engine_metadata`

---

## License

MIT — see [`LICENSE`](./LICENSE). Built by Claude Code (Opus). Contributions welcome.
