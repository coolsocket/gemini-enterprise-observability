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

## Table of contents

- [Pages](#pages) — what each dashboard tab shows
- [Architecture](#architecture) — data flow, why BQ + FastAPI + React
- [Deploying to your GCP project](#deploying-to-your-gcp-project)
  - [Prerequisites](#prerequisites) — tools, GCP state, auth
  - [Full end-to-end verification checklist](#full-end-to-end-verification-checklist) — ~14 items to reach green
  - [Two-phase deploy (recommended for fresh projects)](#two-phase-deploy-recommended-for-fresh-projects)
  - [Preview the dashboard](#preview-the-dashboard) — local vs Cloud Run
  - [Step-by-step (debugging)](#step-by-step-debugging)
  - [Troubleshooting](#troubleshooting) — 6 common failure modes
- [Local development](#local-development) — `make api-run` + Vite HMR
- [Repo layout](#repo-layout) — where everything lives
- [Known Limitations](#known-limitations) — 20 items, grouped
  - [Data — signals GE doesn't emit](#data--signals-ge-doesnt-emit)
  - [API — what a service account can't do](#api--what-a-service-account-cant-do)
  - [Deploy — manual steps outside our automation](#deploy--manual-steps-outside-our-automation)
  - [Operational — freshness + performance](#operational--freshness--performance)
- [Authentication](#authentication) — runtime SA + IAM
- [Operational tasks](#operational-tasks) — refresh, rotate, backfill
- [Changelog](#changelog) — user-visible changes, newest first
- [Key contributors](#key-contributors)
- [License](#license) — Apache 2.0

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
#
# What `REGION` controls (default us-central1):
#   • Artifact Registry repo location (where the container image lives)
#   • Cloud Run service location (where the dashboard runs, if you flip
#     deploy_cloud_run=true)
# What `BQ_LOCATION` controls (default US, separate variable):
#   • BigQuery dataset location — pick asia-southeast1 for Singapore,
#     europe-west1 for Belgium, or a multi-region like US / EU / asia.
#     Common data-residency choice: BQ_LOCATION=asia-southeast1 to keep
#     analytical data in Singapore.
# Log Router sinks are global. Both REGION and BQ_LOCATION are picked once
# and can't be changed in place — tf-destroy + re-apply if you need to move.

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

### One-command recovery: `make resume`

The 90% case after a failed deploy: a fix has been pushed upstream and
you need to `git pull && re-run views`. `make resume PROJECT=<p>` does
that in one shot:

```bash
make resume PROJECT=responsive-lens-421108 DATASET=ge_observability
```

Under the hood:
1. `git pull --ff-only origin main` (safe if you have no local changes; skipped if offline / non-ff)
2. Queries the existing dataset via `bq show` to auto-detect its **actual `BQ_LOCATION`** — so preflight's region-mismatch gate doesn't trip on state that's already on GCP.
3. Runs `apply_views.py`, which is idempotent: 21 `CREATE OR REPLACE VIEW`s that no-op when nothing changed, and successfully rebuild on the affected views when a schema-drift or dependency fix was pushed.

Total time: ~30-60 seconds. Doesn't touch Terraform, image, or bootstrap
— use `make deploy-infra` for those.

### Resuming after a failure (idempotency map)

All deploy steps are idempotent — none of them delete data. But some are
smart (skip work) and some always re-run. Use this to shortcut re-tries
instead of running the whole chain:

| Step | Smart re-run? | Cost of re-run | Details |
|---|---|---|---|
| `preflight`             | n/a  | ~5 s  | Read-only scan; changes nothing. |
| `tf-apply`              | ✅ **fully smart** | ~10-30 s | Terraform diffs state; already-present + unchanged resources are no-ops. |
| `image`                 | ❌ **always rebuilds** | 1-3 min | `gcloud builds submit --tag=:latest` doesn't hash source. **Set `SKIP_IMAGE=true`** when you know the image is fresh (e.g. only tweaked Terraform). |
| `bootstrap`             | mostly | ~5 s | Metadata tables TRUNCATE-load (small); `observabilityConfig` PATCH is idempotent; `quota_config` MERGE only touches changed rows. |
| `views` / `deploy-views` | half | 30-60 s | Every `CREATE OR REPLACE VIEW` runs, but re-creating an unchanged view is a no-op. |

**Common resume scenarios:**

```bash
# Views failed (schema-drift / waiting-for-logs); everything else is fine:
make deploy-views PROJECT=<p>

# Only tf-apply changed something; image + bootstrap + views already good:
make tf-apply PROJECT=<p>

# Full re-run but skip the slow image build:
SKIP_IMAGE=true make deploy-infra PROJECT=<p>

# Just re-seed engine metadata (e.g. after adding a new engine in GE console):
make bootstrap PROJECT=<p>
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

**`terraform apply` fails with `Error 409: Already Exists` on the second run**
Your first `tf-apply` was interrupted (permission denied, quota, network
blip, Ctrl-C) after some resources had already been created in GCP but
before Terraform wrote them to state. The retry then tries to re-create
them and hits the 409. Recover with:

```bash
make tf-import-orphans PROJECT=<your-project> REGION=<region>
make tf-apply         PROJECT=<your-project> REGION=<region>
```

`tf-import-orphans` runs `terraform import` for every resource that might
have leaked (dataset + 6 metadata tables, service account, log sink,
Artifact Registry repo, audit config, enabled APIs, and Cloud Run if
enabled). It's idempotent — "already in state" and "doesn't exist" are
both silent no-ops, so it's safe to re-run.

**`make deploy-infra` stops at "Continue anyway?" or shows an audit-config warning**
That's `make preflight` doing its job — it runs before `terraform apply`
and reports:
  1. Which of `ge_observability` dataset / SA / sink / AR repo already exist
     (needing `tf-import-orphans` OR a different `DATASET=` name).
  2. Whether the authoritative `discoveryengine.googleapis.com` audit config
     will be modified (it's the one resource that overwrites — will strip
     any `exempted_members` you had set).

For a script or CI run, skip the interactive prompt with:
```bash
CONFIRM=y make deploy-infra PROJECT=<p> REGION=<r>
```

To pick a different dataset name (recommended if `ge_observability`
belongs to another team):
```bash
make deploy-infra PROJECT=<p> DATASET=ge_observability_v2 REGION=<r>
```

**Preflight refused: "region mismatch, ALLOW_REGION_MISMATCH=y to bypass"**
You passed a `REGION` (e.g. `asia-southeast1`) that doesn't match the
dataset's `BQ_LOCATION` (e.g. `US` — the default). Most of the time this
is a typo — you wanted everything in one region but only remembered one
of the two variables. Preflight blocks by default because BQ dataset
location is **immutable after create** and fixing it later means
`tf-destroy` + rebuild + re-ingest.

Fix — co-locate:
```bash
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```
Actual data-residency intent (data in EU, compute in US, etc.)? Opt in:
```bash
ALLOW_REGION_MISMATCH=y make deploy-infra PROJECT=<p> …
```

**"I already deployed with mismatched regions. How do I rescue?"**
The dataset location can't be changed in place. Two paths depending on
how much data you've accumulated:

*Case A — fresh deploy, little/no useful data (recommended for most)*:
```bash
# 1. Nuke everything so the mismatched dataset is gone
cd terraform && terraform destroy \
    -var project_id=<p> -var region=<old-region> \
    -var bq_location=<old-loc> -var dataset_id=<d> -var container_image=…
# (delete_contents_on_destroy = false will refuse — override for this rescue)
# Or manually: bq rm -r -f <p>:<d>  &&  make tf-import-orphans + terraform state rm

# 2. Redeploy everything in the right region
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```

*Case B — production dataset with weeks of logs to preserve*:
```bash
# 1. Snapshot the existing dataset to GCS
bq extract --location=<old-loc> \
  '<p>:<d>.cloudaudit_googleapis_com_data_access' \
  gs://<backup-bucket>/data_access-*.avro
# (repeat for each table you care about)

# 2. Destroy + redeploy in new region (as Case A)

# 3. Re-load from GCS into the new dataset
bq load --location=<new-loc> --source_format=AVRO \
  '<p>:<d>.cloudaudit_googleapis_com_data_access' \
  gs://<backup-bucket>/data_access-*.avro
```
Practically, if you're moving *dashboard-only* usage, Case A is almost
always fine — the dashboard shows near-real-time data anyway, and old
audit rows aren't queried after a few weeks.

**BigQuery data-residency: dataset in a specific region (e.g. Singapore)**
Pass `BQ_LOCATION=asia-southeast1` (or `europe-west1`, `asia-east1`, etc.):
```bash
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```
`REGION` (Cloud Run + Artifact Registry) and `BQ_LOCATION` (BQ dataset) are
independent — you can put the dashboard in `us-central1` while keeping
analytical data in Singapore. Dataset location is immutable after create;
change requires `tf-destroy` + fresh apply (data is preserved because
`delete_contents_on_destroy = false`, but you'd need to re-ingest to the
new dataset).

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

## Known Limitations

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

9. **NotebookLM API is blocked for service accounts.** Even with a custom role granting all `discoveryengine.notebooks.*` permissions, SA calls return `403 "The caller does not have permission"`. The gate is at the NotebookLM service layer (workforce identity + Regional Access Boundary registry), not IAM. Attempting to bind the role surfaces this as a `Regional Access Boundary HTTP request failed... Account not found for email: <hash>|<user>` warning — cosmetic (the binding still succeeds) but signals the underlying gate. Full evidence: [`playground/de-api-probe/notebooklm-sa-gate.md`](./playground/de-api-probe/notebooklm-sa-gate.md).

10. **Deep Research REST API is blocked for SAs.** `AsyncAssist` doesn't exist in the public `v1alpha` Discovery Engine schema — it's UI-internal (`v1main`) and gated by the same workforce-identity check. SAs cannot submit DR programmatically. Existing DR from real users IS observable via audit log; we just can't generate it from code.

11. **Generated files can't be downloaded via API.** `StreamAssist` will happily produce an image (Nano Banana 2) or video and return a `fileId` in the stream response, but the download endpoints (`sessions/{sid}:listFiles`, `:getFile`, `:downloadFile`) all return `403 "Session is not owned by the provided user"` — same workforce gate. Files are only accessible in the GE UI. Full evidence: [`playground/ge-generation-probe/FINDINGS.md`](./playground/ge-generation-probe/FINDINGS.md).

12. **Deep Research vs Search vs grounded-answer are distinct services.** DR = `AssistantService.AsyncAssist`, Search API = `SearchService.Search`, grounded-answer = `ConversationalSearchService.GetAnswer`. Our counters keep them in separate buckets; DR is never conflated with Search.

### Deploy — manual steps outside our automation

13. **GE engine must be pre-provisioned.** This repo observes an existing GE deployment; it doesn't create one. Provision the engine in GE Admin Console first.

14. **GE Console toggles are mostly automated** (2026-07-06). `bootstrap.py` now `PATCH`es each engine's `observabilityConfig` field via the Discovery Engine API — `observabilityEnabled` (OpenTelemetry) + `sensitiveLoggingEnabled` (Prompt & Response Logging) flip on automatically. Only **"Enable Feedback"** still requires a manual click in GE Admin Console. Set `SKIP_OBSERVABILITY=true make bootstrap` to opt out of the automation. See [`docs/GE_CONSOLE_SETUP.md`](./docs/GE_CONSOLE_SETUP.md).

15. **Sink target tables are lazy.** `cloudaudit_googleapis_com_data_access` and `discoveryengine_googleapis_com_*` are auto-created by BigQuery only when the first matching sink row arrives. `make deploy-views` reports which are still waiting and is idempotent — re-run once traffic flows.

16. **Cloud Run access needs manual IAP config.** Default `deploy_cloud_run = false`. Flipping it true creates the service, but you still need `iap_invokers = […]` in `terraform.tfvars` and (typically) Identity-Aware Proxy configuration for external access.

### Operational — freshness + performance

17. **Snapshot refresh cadence is 6h.** Dashboard pages read `s_*` snapshot tables refreshed by a BigQuery Scheduled Query every 6 hours. Manual refresh: `POST /api/refresh` (also exposed as a button on the Settings page). Live `v_*` views are always current but slower.

18. **Seat count refresh is 24h.** `licenseConfigs` is pulled at API startup and every 24h by a background asyncio task. Manual refresh: `POST /api/refresh/seats`. Cloud Run cold starts trigger a fresh fetch; long-lived processes stay accurate for a day.

19. **PII redaction is regex-only.** `v_conversations` redacts emails, phone numbers, ID-like numbers, and card-number-like sequences. **Not a full DLP** — names, addresses, and long-form PII pass through. For production, layer Cloud DLP on top.

20. **`quota_config.default_tier` drives seat-to-tier attribution.** Total quota is computed as `sum over tiers of (seats_in_tier × per_tier_limit)`. Explicit user tier assignments (in `user_tier` table) are honored; unassigned seats fall back to `quota.default_tier` (default `plus`). Change the default in the Quota page's tier config editor.

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

- **2026-07-06** — Addressed [issue #1](https://github.com/coolsocket/gemini-enterprise-observability/issues/1) from panliuyang-debug (fresh-project deployment friction, 8 findings): (a) removed the `PORT` env var from `google_cloud_run_v2_service` — Cloud Run injects it automatically and refuses explicit values as of provider v6; (b) set `deletion_protection = false` on the Cloud Run resource so a bad first-deploy can be recovered without `terraform state rm`; (c) added `google_artifact_registry_repository.dashboard` to Cloud Run's `depends_on` so create order is correct; (d) `bootstrap.py` now `PATCH`es each engine's `observabilityConfig` field (`observabilityEnabled` + `sensitiveLoggingEnabled`) via Discovery Engine API — GE Admin Console clicking is no longer required (only "Enable Feedback" remains manual). Set `SKIP_OBSERVABILITY=true` to opt out; (e) huge pairing improvement: `v_conversations_with_response` now `COALESCE`s `gen_ai.choice` (trace-JOIN) with `jsonPayload.serviceTextReply` from `user_activity` — UI-only chat pairs went from ~10% to ~60% match rate. New `join_status` values: `matched_gen_ai_choice` / `matched_service_reply` / `no_response`; (f) DR attribution honesty: reporter proved plain chats trigger `AsyncAssist` alongside `StreamAssist` (byte-identical audit logs, `resourceName` doesn't discriminate) — `v_deep_research_prompts` now suppresses attribution when the candidate prompt already has a matched normal-chat response, and Quota's DR feature hint warns of the imprecision. Updated `docs/GE_CONSOLE_SETUP.md` to reflect the new API automation.
- **2026-07-06** — Reorganized `Documented data limitations` → `Known Limitations` with 20 items grouped into four sections: Data (what GE doesn't emit), API (what SAs can't do), Deploy (manual steps outside automation), and Operational (freshness/PII/tier attribution). Refreshed all entries, dropped a stale "no seat API" item (we use `licenseConfigs` now), and pulled in the newer discoveries about SA-blocked file downloads and the Search-vs-DR distinction. Both EN + zh-CN.
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

## Key contributors

- [**@panliuyang-debug**](https://github.com/panliuyang-debug) — deep audit-log detective work on a fresh-project deploy (issue [#1](https://github.com/coolsocket/gemini-enterprise-observability/issues/1)). Two of their discoveries genuinely changed the product: **(a)** `Engine.observabilityConfig` is a real API field — GE Console clicking is no longer required (`bootstrap.py` now auto-flips it per engine); **(b)** `jsonPayload.serviceTextReply` carries the full UI-chat response inline in `user_activity` — dashboard pairing rate went from ~10% to ~60%. Also reported the reserved-`PORT`, `deletion_protection` deadlock, deploy ordering, SQL splitter, and the plain-chat-triggers-AsyncAssist mislabeling — all fixed in [`a5a3d3f`](https://github.com/coolsocket/gemini-enterprise-observability/commit/a5a3d3f).

Contributions welcome — issues, PRs, and audit-log war stories all appreciated.

---

## License

Apache 2.0 — see [`LICENSE`](./LICENSE). Built by Claude Code (Opus).
