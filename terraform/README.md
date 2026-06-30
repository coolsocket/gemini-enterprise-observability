# Terraform — GE Observability dashboard

Reproducible infra for the GE Observability dashboard. Apply to any GCP project that has
Gemini Enterprise (Discovery Engine) deployed.

## What this creates

| Resource | Purpose |
|---|---|
| `google_bigquery_dataset.ge_observability` | Stores sinked logs + analytical views |
| `google_project_iam_audit_config` (Data Access) | Enables `cloudaudit.googleapis.com/data_access` for Discovery Engine |
| `google_logging_project_sink` | Routes 5 log streams (3 GE + 2 audit) to BQ |
| `google_service_account.dashboard_sa` | Runtime SA for the Cloud Run service |
| `google_bigquery_dataset_iam_member` (×2) | sink writer + dashboard SA access |
| `google_project_iam_member` (×2) | dashboard SA: bigquery.jobUser + discoveryengine.viewer |
| `google_cloud_run_v2_service` | Dashboard service (optional, gate via `deploy_cloud_run`) |
| `google_cloud_run_v2_service_iam_binding` | Who can invoke the service (set `iap_invokers`) |

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars

terraform init
terraform plan
terraform apply
```

## What this does NOT do (manual steps after apply)

1. **Enable GE observability toggles in the GE Admin Console**:
   - Enable OpenTelemetry Instrumentation
   - Enable Prompt and Response Logging
   - (Enable Feedback, if available for your engine)

2. **Bootstrap the BQ views** (after first log entries land):
   ```bash
   PROJECT=<your-project> DATASET=<dataset> \
     python3 ../infra/scripts/apply_views.py
   ```

3. **Build + push the container image** that Cloud Run will run:
   ```bash
   cd ../apps/web && npm run build && cd ../..
   gcloud builds submit --tag $(terraform output -raw container_image)
   ```

4. **Configure IAP** via Cloud Console (Security → Identity-Aware Proxy) and set OAuth consent screen.

## Destroying

```bash
terraform destroy
```

The dataset has `delete_contents_on_destroy = false` so your historical logs survive a teardown.
Set it to `true` if you want a clean slate.
