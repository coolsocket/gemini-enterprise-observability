<!--
  Cloud Shell tutorial · GE Observability
  Referenced from README's "Open in Cloud Shell" button. Cloud Shell
  parses the `<walkthrough-*>` HTML directives to render an interactive
  step-by-step panel (project picker widget, enable-APIs button, etc)
  alongside the terminal.

  Local preview: run `teachme docs/TUTORIAL.md` inside Cloud Shell.
-->

# GE Observability — Deploy to your project

## Welcome

This tutorial takes you from a fresh GCP project to a **populated GE
observability dashboard** in ~30 minutes. Your gcloud auth is already
in this Cloud Shell, so every step runs against **your project**, using
**your data**.

You'll:
1. Pick (or create) a GCP project + enable required APIs
2. Configure `.env` via an interactive wizard
3. Deploy sink + BigQuery + service account via Terraform
4. Enable audit / P&R Logging in GE Admin Console (manual — one-time)
5. Apply views + backfill 30 days of history
6. Serve the dashboard locally

**Prereqs your GCP project must have** (this tutorial doesn't create these):
- Billing enabled
- A Gemini Enterprise engine already provisioned
- Your account has Owner or the composite roles listed in
  [DEPLOYMENT.md prereqs](./DEPLOYMENT.md). Backfill (step 7) additionally
  needs `roles/logging.privateLogViewer` on this project to read audit
  logs from the `_Default` bucket.

Click **Start** →

## Select your project

Pick the project where your Gemini Enterprise engine lives. The picker
below confirms billing is enabled and sets it as the active `gcloud`
project for the rest of the tutorial.

<walkthrough-project-setup billing="true"></walkthrough-project-setup>

Currently targeting: <walkthrough-project-id/>

## Enable required APIs

Click the button below to enable everything the deploy needs in one shot:

<walkthrough-enable-apis apis="bigquery.googleapis.com,logging.googleapis.com,run.googleapis.com,cloudbuild.googleapis.com,artifactregistry.googleapis.com,discoveryengine.googleapis.com,iam.googleapis.com,iamcredentials.googleapis.com,bigquerydatatransfer.googleapis.com,serviceusage.googleapis.com">
</walkthrough-enable-apis>

## Configure your deployment

The wizard writes a `.env` file with your BigQuery project, region, and
dataset. Run it in the terminal:

```bash
make wizard
```

Accept the defaults unless you have a reason not to — the interesting
one is **region**, which most people should set to their nearest GCP
region (`asia-southeast1` for east Asia, `europe-west1` for EU, etc).

Verify:

```bash
cat .env
```

## Deploy infrastructure

This provisions the BigQuery dataset, Log Router sink, service account,
IAM bindings, Artifact Registry, and metadata tables. It also seeds
default tier quotas (all editable via the /quota page later).

```bash
make deploy-infra PROJECT=<walkthrough-project-id/>
```

You'll see terraform output, then Cloud Build packing the container
image, then a `bootstrap` step that syncs your GE engine metadata into
BQ. **Takes 3-5 minutes.**

**Expected end state**: `terraform apply` reports "5 resources added,
0 changed, 0 destroyed" (or similar), and no unhandled errors.

## Turn on GE audit + P&R Logging (manual)

**This step Google's GE Console owns — no CLI equivalent yet.** For
each engine you want observed, open:

<walkthrough-editor-open-file filePath="docs/GE_CONSOLE_SETUP.md">docs/GE_CONSOLE_SETUP.md</walkthrough-editor-open-file>

and follow the "Enable audit logs + prompt & response logging" section.
Concretely:

1. GE Admin Console → your engine → **Settings** → **Observability**
2. Toggle **Data Access audit logs** ON
3. Toggle **Prompt & Response Logging** ON
4. Toggle **OpenTelemetry Instrumentation** ON

Without step 3, the "Conversations" dashboard page stays empty (chat
prompts/responses never land in BigQuery).

## Generate some traffic + wait

Log in to your GE tenant and do 3-5 things:
- Ask a chat question or two
- Kick off a Deep Research task
- Open the NotebookLM tab, create a notebook
- Upload a session file if that's part of your flow

Then **wait 2-5 minutes** for logs to propagate from GE → Cloud Logging
→ your BigQuery sink target tables.

## Apply views + backfill history

Now that log-sink target tables exist, apply the 21 analytical views +
the `canonical_actor` UDF:

```bash
make deploy-views PROJECT=<walkthrough-project-id/>
```

Then pull the last 30 days of history from Cloud Logging (subject to
your `_Default` bucket retention — the script tells you actual coverage):

```bash
make backfill PROJECT=<walkthrough-project-id/> DAYS=30
```

Both are idempotent — safe to re-run.

## Start the dashboard

```bash
make serve PROJECT=<walkthrough-project-id/>
```

You'll see uvicorn start on port 8000. Open a browser tab via the
Cloud Shell "Web Preview" button (top-right, port 8000).

**What you should see:**
- **Overview**: total human_users / active_consumers / chat_turns
- **Persona**: users classified as POWER_USER / ACTIVE_CONSUMER / TRIAL
- **Data Access**: per-user API call breakdown by feature
- **User Deep Dive**: click any user → identity badge (Google / OIDC /
  SA) + per-engine breakdown
- **Quota**: tier limits (editable inline)

## You're done

Ongoing operations:
- **When you pull new code**: `make hotfix PROJECT=<walkthrough-project-id/>`
  (applies latest view SQL + triggers snapshot refresh in one shot)
- **Deploy to Cloud Run** (share the dashboard with your team):
  edit `terraform/terraform.tfvars` to set `deploy_cloud_run = true` +
  add invokers, then `make tf-apply`
- **Runbook + troubleshooting**:
  <walkthrough-editor-open-file filePath="docs/RUNBOOK.md">docs/RUNBOOK.md</walkthrough-editor-open-file>
  and
  <walkthrough-editor-open-file filePath="docs/TROUBLESHOOTING.md">docs/TROUBLESHOOTING.md</walkthrough-editor-open-file>

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>
