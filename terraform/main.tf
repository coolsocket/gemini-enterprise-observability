terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ============================================================
# 0) Enable required APIs
# ============================================================
resource "google_project_service" "required" {
  for_each = toset([
    "bigquery.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "logging.googleapis.com",
    "discoveryengine.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ============================================================
# 1) BigQuery dataset for observability data
# ============================================================
resource "google_bigquery_dataset" "ge_observability" {
  dataset_id  = var.dataset_id
  project     = var.project_id
  location    = var.bq_location
  description = "Gemini Enterprise observability — Path 2 usage + Path 3 audit logs unified"

  labels = {
    purpose    = "ge-observability"
    managed_by = "terraform"
  }

  delete_contents_on_destroy = false

  depends_on = [google_project_service.required]
}

# ============================================================
# 1a) Metadata tables that views depend on
#     (data is populated by infra/scripts/bootstrap.py after apply)
# ============================================================
resource "google_bigquery_table" "engine_metadata" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "engine_metadata"
  deletion_protection = false

  schema = jsonencode([
    { name = "engine_id", type = "STRING", mode = "REQUIRED" },
    { name = "display_name", type = "STRING" },
    { name = "solution_type", type = "STRING" },
    { name = "data_store_id", type = "STRING" },
    { name = "create_time", type = "TIMESTAMP" },
  ])
}

resource "google_bigquery_table" "datastore_metadata" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "datastore_metadata"
  deletion_protection = false

  schema = jsonencode([
    { name = "datastore_id", type = "STRING", mode = "REQUIRED" },
    { name = "display_name", type = "STRING" },
    { name = "industry_vertical", type = "STRING" },
    { name = "create_time", type = "TIMESTAMP" },
  ])
}

resource "google_bigquery_table" "resources_alive" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "resources_alive"
  deletion_protection = false

  schema = jsonencode([
    { name = "resource_id", type = "STRING", mode = "REQUIRED" },
    { name = "display_name", type = "STRING" },
    { name = "resource_type", type = "STRING", mode = "REQUIRED" },
    { name = "state", type = "STRING" },
  ])
}

resource "google_bigquery_table" "quota_config" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "quota_config"
  deletion_protection = false

  schema = jsonencode([
    { name = "key", type = "STRING", mode = "REQUIRED" },
    { name = "value", type = "STRING" },
    { name = "updated_at", type = "TIMESTAMP" },
    { name = "updated_by", type = "STRING" },
  ])
}

# Per-actor tier assignment (standard vs plus vs custom). Free-form so admins can
# add new tiers or use "auto" to let a rules-based classifier decide.
resource "google_bigquery_table" "user_tier" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "user_tier"
  deletion_protection = false

  schema = jsonencode([
    { name = "actor_email", type = "STRING", mode = "REQUIRED" },
    { name = "tier",        type = "STRING", mode = "REQUIRED" }, # 'standard' | 'plus'
    { name = "assigned_at", type = "TIMESTAMP" },
    { name = "assigned_by", type = "STRING" },
    { name = "notes",       type = "STRING" },
  ])
}

resource "google_bigquery_table" "snapshot_meta" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.ge_observability.dataset_id
  table_id            = "snapshot_meta"
  deletion_protection = false

  schema = jsonencode([
    { name = "snapshot_name", type = "STRING", mode = "REQUIRED" },
    { name = "source_view", type = "STRING" },
    { name = "refreshed_at", type = "TIMESTAMP" },
    { name = "row_count", type = "INT64" },
    { name = "refresh_seconds", type = "FLOAT64" },
    { name = "triggered_by", type = "STRING" },
  ])
}

# ============================================================
# 2) Enable Data Access audit logging for Discovery Engine
#    (this is the project-level audit config that gives us cloudaudit/data_access)
# ============================================================
resource "google_project_iam_audit_config" "discoveryengine_data_access" {
  project = var.project_id
  service = "discoveryengine.googleapis.com"

  audit_log_config { log_type = "DATA_READ" }
  audit_log_config { log_type = "DATA_WRITE" }
  # ADMIN_READ is always on; not listing it because it's not togglable here
}

# ============================================================
# 3) Logs Router sink — routes 5 log streams to BQ dataset
# ============================================================
resource "google_logging_project_sink" "ge_observability_unified" {
  name                   = var.sink_name
  project                = var.project_id
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${var.dataset_id}"
  unique_writer_identity = true

  filter = <<-EOT
    (logName="projects/${var.project_id}/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity"
     OR logName="projects/${var.project_id}/logs/discoveryengine.googleapis.com%2Fgen_ai.user.message"
     OR logName="projects/${var.project_id}/logs/discoveryengine.googleapis.com%2Fgen_ai.choice")
    OR (logName="projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Factivity"
        AND protoPayload.serviceName="discoveryengine.googleapis.com")
    OR (logName="projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Fdata_access"
        AND (protoPayload.serviceName="discoveryengine.googleapis.com"
          OR protoPayload.serviceName="aiplatform.googleapis.com"))
  EOT

  bigquery_options {
    use_partitioned_tables = true
  }

  depends_on = [google_bigquery_dataset.ge_observability]
}

# Grant sink writer identity BQ Data Editor on the dataset
resource "google_bigquery_dataset_iam_member" "sink_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.ge_observability.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.ge_observability_unified.writer_identity
}

# ============================================================
# 4) Service account for the dashboard Cloud Run service
# ============================================================
resource "google_service_account" "dashboard_sa" {
  account_id   = "ge-observability-sa"
  display_name = "GE Observability dashboard service account"
  project      = var.project_id
}

# Grant the SA permissions needed:
# - bigquery.dataViewer on the dataset (read views)
# - bigquery.jobUser on project (run queries)
resource "google_bigquery_dataset_iam_member" "dashboard_reader" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.ge_observability.dataset_id
  role       = "roles/bigquery.dataEditor" # needs Editor to run CREATE OR REPLACE TABLE s_*
  member     = "serviceAccount:${google_service_account.dashboard_sa.email}"
}

resource "google_project_iam_member" "dashboard_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dashboard_sa.email}"
}

# Allow the SA to list Discovery Engine resources (for engine_metadata + resources_alive sync)
resource "google_project_iam_member" "dashboard_de_viewer" {
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
  member  = "serviceAccount:${google_service_account.dashboard_sa.email}"
}

# ============================================================
# 5) Cloud Run service for the dashboard
# ============================================================
resource "google_cloud_run_v2_service" "dashboard" {
  count    = var.deploy_cloud_run ? 1 : 0
  name     = var.service_name
  project  = var.project_id
  location = var.region

  template {
    service_account = google_service_account.dashboard_sa.email

    containers {
      image = var.container_image
      env {
        name  = "BQ_PROJECT"
        value = var.project_id
      }
      env {
        name  = "BQ_DATASET"
        value = var.dataset_id
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }
    }

    scaling {
      max_instance_count = var.max_instances
    }
  }

  depends_on = [
    google_bigquery_dataset_iam_member.dashboard_reader,
    google_project_iam_member.dashboard_bq_jobuser,
  ]
}

# IAP / public access policy
# Default: only members in iap_invokers can hit the service
resource "google_cloud_run_v2_service_iam_binding" "invokers" {
  count    = var.deploy_cloud_run ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dashboard[0].name
  role     = "roles/run.invoker"
  members  = var.iap_invokers
}

# ============================================================
# 6) Snapshot refresh — BQ Scheduled Query every 6 hours
# ============================================================
resource "google_bigquery_data_transfer_config" "snapshot_refresh" {
  count                = var.enable_scheduled_refresh ? 1 : 0
  project              = var.project_id
  location             = lower(var.bq_location)
  display_name         = "GE Observability snapshot refresh"
  data_source_id       = "scheduled_query"
  schedule             = "every 6 hours"
  service_account_name = google_service_account.dashboard_sa.email
  params = {
    query = templatefile("${path.module}/snapshot_refresh.sql.tftpl", {
      project = var.project_id
      dataset = var.dataset_id
    })
  }
  depends_on = [
    google_bigquery_dataset.ge_observability,
    google_project_iam_member.dashboard_bq_jobuser,
    google_project_service.required,
  ]
}

# ============================================================
# 7) Outputs
# ============================================================
output "service_url" {
  value       = var.deploy_cloud_run ? google_cloud_run_v2_service.dashboard[0].uri : null
  description = "Cloud Run service URL"
}

output "service_account_email" {
  value = google_service_account.dashboard_sa.email
}

output "sink_writer_identity" {
  value = google_logging_project_sink.ge_observability_unified.writer_identity
}

output "dataset_full_name" {
  value = "${var.project_id}.${google_bigquery_dataset.ge_observability.dataset_id}"
}

output "next_steps" {
  value = <<-EOT

    Terraform applied successfully. Next manual steps:

    1. Open GE Admin Console for each engine and enable:
       - Enable Feedback (if available)
       - Enable OpenTelemetry Instrumentation
       - Enable Prompt and Response Logging

    2. Bootstrap the views + metadata tables:
       PROJECT=${var.project_id} DATASET=${google_bigquery_dataset.ge_observability.dataset_id} \\
       python3 infra/scripts/apply_views.py

    3. Build + push the container image:
       cd apps/web && npm run build && cd ../..
       gcloud builds submit --tag ${var.container_image}

    4. If deploy_cloud_run = true, the service should be live at the URL above.
       Configure IAP via Cloud Console (Security → Identity-Aware Proxy).
  EOT
}
