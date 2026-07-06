# GE Observability

> **Language**: English · [中文](./README.zh-CN.md)

![Overview page — English](./docs/screenshots/overview-en.png)

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

### Prerequisites

Before you start, make sure you have all of these:

**Local tools on `PATH`**
- `gcloud` (Cloud SDK ≥ 460)
- `terraform` ≥ 1.5
- `python3` ≥ 3.11 + `pip`
- `npm` ≥ 8 (only needed if you want to iterate on the frontend; the container build handles it)
- `make`

**GCP project state**
- Project exists and billing is enabled (`gcloud beta billing projects link ...`)
- Your caller has **Owner** or (Editor + Security Admin + Project IAM Admin) on the project — Terraform enables APIs and grants roles
- **Gemini Enterprise engine already provisioned** in the target project — this repo observes an existing GE deployment; it doesn't create one
- **Cloud Build API pre-enabled** so `make image` works on the first pass: `gcloud services enable cloudbuild.googleapis.com --project=<project>` (Terraform enables it too, but if you run the deploy chain out of order this bites first)

**Authentication (both required)**
- `gcloud auth login` — for the Terraform + Cloud Build CLIs
- `gcloud auth application-default login` — for the Python helpers (`apply_views.py`, `bootstrap.py`, and the FastAPI backend) which all use ADC

### Full end-to-end verification checklist

Deployment isn't "done" the moment `terraform apply` finishes — several
steps depend on GE Console toggles being flipped **manually** and on the
Logs Router sink actually receiving matching entries. Use this list to
know when you've truly reached green:

- [ ] `make deploy-infra PROJECT=<p> REGION=<r>` exits 0
  - Provisions 24 resources (BQ dataset, sink, 6 metadata tables, IAM,
    audit-config, Artifact Registry repo, service account)
  - Builds + pushes the container image to Artifact Registry
  - `bootstrap.py` loads `engine_metadata` / `datastore_metadata` /
    `resources_alive` and seeds `quota_config` with live seat count
- [ ] Terraform output `dataset_full_name` prints your project + dataset
- [ ] `bq ls <project>:<dataset>` shows the 6 metadata tables
- [ ] `bq ls -a <project>:<dataset>` **also** shows the metadata tables —
  helpful when confirming region + case
- [ ] Open **GE Admin Console** for each engine and flip the toggles:
  - [ ] OpenTelemetry Instrumentation (generates `trace_id` for pairing)
  - [ ] Prompt & Response Logging (writes `gen_ai.user.message` +
        `gen_ai.choice`)
  - [ ] Feedback (optional; enables thumbs-up/down capture)
  - Full walk-through with screenshots: `docs/GE_CONSOLE_SETUP.md`
- [ ] Generate real GE traffic — at minimum: one chat turn per engine,
  one Deep Research submission, and one NotebookLM notebook interaction
- [ ] Wait ~2-5 minutes for Logs Router to deliver the first entries. Confirm:
  ```bash
  bq ls -a <project>:<dataset> | grep -E 'cloudaudit_|discoveryengine_'
  ```
  You should see `cloudaudit_googleapis_com_activity`,
  `cloudaudit_googleapis_com_data_access`, and (if traffic was chat/DR)
  `discoveryengine_googleapis_com_gemini_enterprise_user_activity` +
  `..._gen_ai_choice`. If any are missing, keep generating traffic — BQ
  auto-creates them on the first matching row.
- [ ] `make deploy-views PROJECT=<p>` — expected to be **fully green**
  now: `applied 21/21 views`, zero waiting / cascade / real errors. If
  some views are still waiting, the corresponding audit-log table hasn't
  received its first row yet; send more traffic of that type + re-run.
- [ ] `make serve PROJECT=<p>` and open `http://127.0.0.1:8000` — hit
  every page: Overview, Users, User Deep Dive, Agents, Engines,
  Conversations, Data Access, Quota, Settings. None should show
  "loading forever" or 500s.
- [ ] The Quota page's "Seats" panel shows a non-zero
  `license.total_seats` (fetched live from `licenseConfigs`)
- [ ] Optionally set `deploy_cloud_run = true` in
  `terraform.tfvars` + add `iap_invokers = […]` + `make tf-apply` again,
  then `gcloud run services proxy ge-observability --port 8080 --region <r>`

If any checkbox above stays red for more than a few minutes, the
Troubleshooting section below covers the most common causes.

### Two-phase deploy (recommended for fresh projects)

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability

# ---------- Phase A: provision + image + metadata ----------
make deploy-infra PROJECT=my-project REGION=us-central1
# Runs: terraform apply → gcloud builds submit → bootstrap.py

# ---------- Manual step ----------
# In GE Admin Console, per engine, enable:
#   - OpenTelemetry Instrumentation      (generates trace IDs)
#   - Prompt & Response Logging          (writes gen_ai.* logs)
#   - Feedback                           (optional)
# See docs/GE_CONSOLE_SETUP.md
#
# Then send a bit of traffic (chat / deep research / open a notebook) and
# wait ~2-5 min for logs to land in BigQuery.

# ---------- Phase B: apply the analytical views ----------
make deploy-views PROJECT=my-project
```

The split matters: BigQuery only auto-creates the sink target tables
(`cloudaudit_googleapis_com_data_access`, `discoveryengine_googleapis_com_*`)
after the first matching log lands. `make deploy-views` is idempotent — safe
to re-run — and reports any views still waiting for a source table so you
know exactly what to wait for.

### Preview the dashboard

Default is **local-only** (`deploy_cloud_run = false`) so you can iterate
without spending on Cloud Run:

```bash
make serve PROJECT=my-project    # http://127.0.0.1:8000
```

Ready to expose it? In `terraform/terraform.tfvars`:

```hcl
deploy_cloud_run = true
iap_invokers     = ["user:alice@example.com", "group:ge-users@example.com"]
```

then `make tf-apply PROJECT=my-project` and open:

```bash
gcloud run services proxy ge-observability --port 8080 --region us-central1
open http://localhost:8080
```

### Step-by-step (debugging)

```bash
make tf-plan   PROJECT=my-project    # preview infra
make tf-apply  PROJECT=my-project    # provision infra + Artifact Registry repo
make image     PROJECT=my-project    # build + push container to AR
make bootstrap PROJECT=my-project    # seed metadata tables
# (manually flip GE Console toggles + generate a bit of traffic)
make views     PROJECT=my-project    # apply BQ views (re-run until 100%)
```

### Troubleshooting

**`make views` reports "N view(s) skipped — waiting for log-sink tables"**
Expected on a fresh project. The listed tables (`cloudaudit_googleapis_com_*`,
`discoveryengine_googleapis_com_*`) are created by BigQuery only after the
Logs Router sink actually delivers a matching row. Enable the GE Console
toggles, send a couple of chat messages, wait ~2 minutes, and re-run
`make views` — the count drops until all applied.

**`gcloud builds submit` fails with `NOT_FOUND` on `gcr.io/...`**
`gcr.io` (Container Registry) was deprecated by Google in February 2024;
projects created after that don't have it. This repo now uses Artifact
Registry — check that you're on a recent `main` and that the `IMAGE`
variable resolves to `<region>-docker.pkg.dev/...`. Run `make tf-apply`
first so Terraform creates the AR repo before `make image`.

**Cloud Run URL returns 403**
Add your callers to `iap_invokers` in `terraform.tfvars` and re-apply.
Without IAP: use `roles/run.invoker` on the specific principals. With IAP:
use the `principal://` form. If it still 403s, check whether Cloud Run
requires authentication (`gcloud run services describe ge-observability
--region <r> --format="value(spec.template.spec.containers[0].image)"`).

**`make views` fails with `Not found: Table quota_config`**
You skipped `make bootstrap`. That step creates the metadata tables the
views reference (also created idempotently by `terraform apply` — if you
see this after a successful apply, re-check that `PROJECT` and `DATASET`
match on both invocations).

**API returns 403 on BigQuery queries at runtime**
The runtime SA (`ge-observability-sa@…`) needs `roles/bigquery.jobUser`
project-wide and `roles/bigquery.dataViewer` on the dataset. Terraform
grants both — if you renamed the dataset outside Terraform, re-apply so
the IAM binding follows.

**`bootstrap.py` fails with `licenseConfigs` 404 or 403**
Your GE deployment may not have a `licenseConfigs` API response yet (very
new tenants) or the caller lacks `roles/discoveryengine.viewer`. The
script degrades gracefully — the seat count on the Quota page will fall
back to whatever's already in `quota_config`.

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

   ⚠ **Service accounts CANNOT use NotebookLM programmatically, even with full IAM roles.** Empirically confirmed (2026-07-03): granting `discoveryengine.notebooks.{list,create,get,update,delete}` to a service account results in a different, deeper 403 (`"The caller does not have permission"`, not the usual `"Permission X denied"`). The gate is at the NotebookLM service layer, not IAM — it requires the caller to have a valid Workforce Identity Federation subject registered in the Regional Access Boundary registry. Attempting IAM binding surfaces this as a `Regional Access Boundary HTTP request failed... Account not found for email: <hash>|<user>` warning (cosmetic — doesn't block the binding, but signals the underlying gate). SAs and Deep Research (AsyncAssist REST) share this limitation: they only respond to authenticated UI sessions. See `playground/de-api-probe/notebooklm-sa-gate.md` for full evidence.

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

## Changelog

Keep this list current when changing user-visible behavior, quota semantics, or dashboard data model. Newest first. See `git log` for full detail.

- **2026-07-06** — Two Deep Research consistency fixes: (a) `v_data_access_summary.deep_research_calls` used to count both `AsyncAssist` (submit) AND `ReadAsyncAssist` (UI polling) — inflating per-user counts 3-5×. Now aligned with `v_daily_usage_per_user` to count submits only; a user who ran two research tasks over two days now shows `4` on both the Quota page and User Deep Dive, not `4` and `12`. (b) Verified via full method-name audit: Deep Research (`AssistantService.AsyncAssist`), Google Search API (`SearchService.Search`), and grounded chat search (`ConversationalSearchService.GetAnswer`) are three distinct services that our counters keep in separate buckets — Deep Research is never conflated with Search.
- **2026-07-06** — README Prerequisites now includes a full end-to-end verification checklist (~14 items) so first-time deployers know exactly when to declare victory, including the manual GE Console toggle step and the "wait for logs then re-run views" loop. Both EN + zh-CN.
- **2026-07-06** — Deploy pipeline fixes for first-time deployers (simulated from scratch, hit 3 blockers): (a) `apply_views.py` now categorizes missing-source-table errors as "waiting for log-sink tables" (idempotent, safe to re-run once logs flow) vs "missing Terraform-managed table" (actionable: run `tf-apply`) vs "real errors". (b) `bootstrap.py` migrated from `subprocess("gcloud auth print-access-token")` to `google.auth.default()` — no gcloud CLI needed in containers/CI. (c) Container image moved from deprecated `gcr.io/` to Artifact Registry (`<region>-docker.pkg.dev/...`); Terraform now provisions a `google_artifact_registry_repository`. (d) `make deploy` split into two-phase `deploy-infra` + `deploy-views` reflecting the fact that BQ sink target tables only exist after GE toggles ON + traffic flows. (e) `deploy_cloud_run` default flipped to `false` so first-time deployers can iterate locally. (f) README got a full Prerequisites section + Troubleshooting covering the 5 common failure modes.
- **2026-07-06** — Removed `image_gen`, `video_gen`, `idea_gen` from the Quota dashboard. GE runs those generations inside Google infrastructure and does not emit customer audit logs, so we had been relying on a prompt-keyword heuristic that misclassified "summarize this video" style prompts. Underlying tier_limit rows in `quota_config` preserved for revival if GE ever exposes real per-feature counters.
- **2026-07-06** — Quota total now computed from **purchased seats** (`licenseConfigs`), not active-user count. Previously an org that bought 20 seats but had 10 active users showed only 10× per-tier limit; now it correctly shows 20× (assigned tiers honored, remaining seats fall back to `quota.default_tier`). Per-feature card label changed from "eligible" to "seats".
- **2026-07-06** — NotebookLM quota count now includes only user-initiated write ops (`Create*`/`Update*`/`Delete*`/`BatchCreate*`/`Generate*`), excluding the ~20 background `Get*`/`List*`/`BatchGet*` calls the UI fires per notebook open. Per-user daily counts now match perceived actions. Also: seat count (`licenseConfigs` API) auto-refreshes every 24h from a FastAPI background task, tunable via `LICENSE_REFRESH_INTERVAL_SEC`; exposed via `POST /api/refresh/seats`.
- **2026-07-06** — Quota Deep Dive: per-user table headers are click-sortable (email / tier / per-feature utilization).
- **2026-07-03** — Playground findings: NotebookLM + Deep Research + image/video generation download APIs are gated by a workforce-identity check, not IAM; service accounts cannot pass regardless of role bundle. See `playground/de-api-probe/notebooklm-sa-gate.md` and `playground/ge-generation-probe/FINDINGS.md`.
- **2026-07-03** — Compliance sweep: switched LICENSE MIT → Apache 2.0, applied license header to all 36 source files, replaced hardcoded actor-email prefix with the `SIM_PREFIX` env var (default `sim-`), scrubbed real project IDs / user emails / workforce hashes from `playground/`.
- **2026-07-02** — Cover screenshots added to `README.md` and `README.zh-CN.md`.
- **2026-06-30** — Snapshot Scheduled Query updated to also refresh 8 newly added `s_*` tables that were missing from the previous 15-view rotation.
- **2026-06-29** — Quota page: seat count now sourced from live `v1alpha/licenseConfigs` (real 20-seat SEARCH_AND_ASSISTANT tier), replacing the static config value. Inline-editable tier limits and California-midnight reset semantics were already in place.
- **2026-06-28** — Prompt reverse-lookup: attributes StreamAssist prompts to Deep Research (AsyncAssist ±60s) and custom agents (post-`page_type='agent'` navigation).
- **2026-06-27** — Views transparently rename `vivo-sim-*` → `demo-*` at query time (source data untouched); later parameterized as `SIM_PREFIX`.
- **2026-06-25** — NotebookLM audit-log capture: correct namespace is `notebooklm.v1main.*` (not `v1alpha` as public docs imply). Six services observed: Notebook, Source, Note, Artifact, AudioOverview, Account.
- **2026-06-22** — Header time-range filter (24h / 7d / 30d / all).

---

## License

Apache 2.0 — see [`LICENSE`](./LICENSE). Built by Claude Code (Opus). Contributions welcome.
