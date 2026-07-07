# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
  description = "Container image for the dashboard. Default targets Artifact Registry (<region>-docker.pkg.dev/<project>/<repo>/dashboard:latest); pass the value from the Makefile IMAGE variable."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello" # placeholder; overridden by Makefile
}

variable "ar_repo" {
  description = "Artifact Registry repository name used for the dashboard container image."
  type        = string
  default     = "ge-observability"
}

variable "max_instances" {
  description = "Cloud Run max instances"
  type        = number
  default     = 5
}

variable "deploy_cloud_run" {
  description = "If true, deploy Cloud Run service. Default false so first-time deployers can iterate locally (make api-run) before spending on Cloud Run. Set true once you're ready to expose the dashboard."
  type        = bool
  default     = false
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
  description = "If true, create the Scheduled Query that re-materializes snapshots. Needs apply_views.py to have been run first (views must exist)."
  type        = bool
  default     = false
}

variable "snapshot_refresh_schedule" {
  description = "BigQuery Data Transfer schedule string for snapshot refresh. Format: 'every N hours' | 'every N minutes' | 'every day HH:MM' | crontab. Default 'every 6 hours' balances freshness against BQ query cost — bump to 'every 1 hours' for near-realtime demos, or 'every day 03:00' for once-nightly."
  type        = string
  default     = "every 6 hours"
}
