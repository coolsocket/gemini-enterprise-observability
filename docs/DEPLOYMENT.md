# Deployment guide

> The comprehensive path. For a 5-line quick start see the main [README](../README.md).


## Prerequisites

Before you start, make sure you have all of these:

**Local tools on `PATH`**
- `gcloud` (Cloud SDK ≥ 460)
- `terraform` ≥ 1.5
- `python3` ≥ 3.11 + `pip`
- `npm` ≥ 8 (only needed if you want to iterate on the frontend; the container build handles it)
- `make`

**GCP project state**
- Project exists and billing is enabled (`gcloud beta billing projects link ...`)
- **Gemini Enterprise engine already provisioned** in the target project — this repo observes an existing GE deployment; it doesn't create one
- **Cloud Build API pre-enabled** so `make image` works on the first pass: `gcloud services enable cloudbuild.googleapis.com --project=<project>` (Terraform enables it too, but if you run the deploy chain out of order this bites first)

**IAM roles the caller (or the SA if you're impersonating) needs on the project — verified 2026-07-06 by hitting each denial in turn:**

| Terraform resource | Minimum role (concrete) | Composite role that covers it |
|---|---|---|
| Enable required APIs | `serviceusage.services.enable` | `roles/serviceusage.serviceUsageAdmin` |
| Create BQ dataset + tables | `bigquery.datasets.create`, `bigquery.tables.create` | `roles/bigquery.dataOwner` |
| Create Log Router sink | `logging.sinks.create` + `logging.buckets.get` | `roles/logging.configWriter` |
| Create Artifact Registry repo | `artifactregistry.repositories.create` | `roles/artifactregistry.admin` |
| Create the runtime service account | `iam.serviceAccounts.create` | `roles/iam.serviceAccountAdmin` |
| Grant project-level roles to the SA (bigquery.jobUser, discoveryengine.viewer) | `resourcemanager.projects.setIamPolicy` | `roles/resourcemanager.projectIamAdmin` |
| Set audit-config for discoveryengine (authoritative) | `resourcemanager.projects.setIamPolicy` (same) | `roles/resourcemanager.projectIamAdmin` |
| Create Cloud Run service (if `deploy_cloud_run = true`) | `run.services.create` | `roles/run.admin` |

**The single easy answer** is `roles/owner` on the project. If your org doesn't allow that, grant all seven of the composites above to the deploying principal. Missing any one of them causes `terraform apply` to fail partway with `403 Permission denied on resource ...` and you'll need [`make tf-import-orphans`](../TROUBLESHOOTING.md#terraform-apply-fails-with-error-409-already-exists-on-the-second-run) to recover the partial state.

**Authentication (both required)**
- `gcloud auth login` — for the Terraform + Cloud Build CLIs
- `gcloud auth application-default login` — for the Python helpers (`apply_views.py`, `bootstrap.py`, and the FastAPI backend) which all use ADC

## Full end-to-end verification checklist

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

## Two-phase deploy (recommended for fresh projects)

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

## Preview the dashboard

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

## One-command view recovery: `make resume`

For the 90% case where views failed to apply and you want to retry:

```bash
# Pull upstream fixes first if you want them (your call — Make won't do this):
git pull

# Then one command:
make resume PROJECT=responsive-lens-421108 DATASET=ge_observability
```

Under the hood `make resume`:
1. Queries the existing dataset via `bq show` to auto-detect its **actual `BQ_LOCATION`** — so preflight's region-mismatch gate doesn't trip on state that's already on GCP.
2. Runs `apply_views.py`, which is idempotent: 21 `CREATE OR REPLACE VIEW`s that no-op when nothing changed, and successfully rebuild on the affected views when a schema-drift or dependency fix was pushed.

Total time: ~30-60 seconds. Doesn't touch git, Terraform, image, or
bootstrap — those are yours to manage.

## Resuming after a failure (idempotency map)

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

## Step-by-step (debugging)

```bash
make tf-plan   PROJECT=my-project    # preview infra
make tf-apply  PROJECT=my-project    # provision infra + Artifact Registry repo
make image     PROJECT=my-project    # build + push container to AR
make bootstrap PROJECT=my-project    # seed metadata tables
# (manually flip GE Console toggles + generate a bit of traffic)
make views     PROJECT=my-project    # apply BQ views (re-run until 100%)
```


