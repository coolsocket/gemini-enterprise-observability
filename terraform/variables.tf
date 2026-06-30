variable "project_id" {
  description = "GCP project ID where GE is deployed and dashboard runs"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run + other regional resources"
  type        = string
  default     = "us-central1"
}

variable "dataset_id" {
  description = "BigQuery dataset name to store sinked logs + analytical views"
  type        = string
  default     = "ge_observability"
}

variable "bq_location" {
  description = "BigQuery dataset location (US, EU, asia-east2, etc.)"
  type        = string
  default     = "US"
}

variable "sink_name" {
  description = "Logs Router sink name"
  type        = string
  default     = "ge-observability-unified"
}

variable "service_name" {
  description = "Cloud Run service name for the dashboard"
  type        = string
  default     = "ge-observability"
}

variable "container_image" {
  description = "Container image for the dashboard (gcr.io/.../ge-observability:tag)"
  type        = string
  default     = "gcr.io/cloudrun/hello" # placeholder; replace with your built image
}

variable "max_instances" {
  description = "Cloud Run max instances"
  type        = number
  default     = 5
}

variable "deploy_cloud_run" {
  description = "If true, deploy Cloud Run service. Set false to only provision BQ/sink/IAM."
  type        = bool
  default     = true
}

variable "iap_invokers" {
  description = "Members allowed to invoke the Cloud Run service. Use IAP-secured form when behind IAP."
  type        = list(string)
  default = [
    # "domain:google.com",         # for IAP-protected: replace with your org domain
    # "user:alice@example.com",
    # "group:dashboard-viewers@example.com",
  ]
}

variable "enable_scheduled_refresh" {
  description = "If true, create the every-6h Scheduled Query that re-materializes snapshots. Needs apply_views.py to have been run first (views must exist)."
  type        = bool
  default     = false
}
