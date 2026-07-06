# Troubleshooting

> Symptom → cause → fix. If you don't see your symptom here, check [Known Limitations](./KNOWN_LIMITATIONS.md) first — it's often expected behavior.


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

