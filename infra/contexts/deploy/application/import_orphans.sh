#!/usr/bin/env bash
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

# Recover from a half-finished `terraform apply` — the classic case where the
# operator ran `make deploy-infra` once, it failed halfway (permission, quota,
# network blip, etc.), and now the retry fails because the BQ dataset / SA /
# AR repo / etc. already exist but aren't in terraform state.
#
# This script runs `terraform import` for every resource that might have
# leaked from a partial apply. Each import is wrapped so "already managed"
# errors don't halt the run — only truly unrecoverable problems bubble up.
#
# Usage:
#   PROJECT=<gcp-project> DATASET=ge_observability REGION=us-central1 AR_REPO=ge-observability \
#     bash infra/contexts/deploy/application/import_orphans.sh
#
# After it finishes, re-run `make tf-apply` (or `make deploy-infra`).

set -uo pipefail
cd "$(dirname "$0")/../../../../terraform"

: "${PROJECT:?ERROR: PROJECT=<gcp-project-id> required}"
DATASET="${DATASET:-ge_observability}"
REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-ge-observability}"
SA_ID="${SA_ID:-ge-observability-sa}"
SINK_NAME="${SINK_NAME:-ge-observability-sink}"
SERVICE_NAME="${SERVICE_NAME:-ge-observability}"

echo "==> Importing orphan resources into terraform state"
echo "    PROJECT=${PROJECT} DATASET=${DATASET} REGION=${REGION}"
echo ""

# terraform import errors we treat as "OK, already managed":
#   - "Resource already managed by Terraform"
#   - "Cannot import non-existent remote object"  (nothing to import — fine)
tf_import() {
  local addr="$1"
  local id="$2"
  local label="$3"
  # shellcheck disable=SC2086
  out=$(terraform import \
    -var "project_id=${PROJECT}" \
    -var "dataset_id=${DATASET}" \
    -var "region=${REGION}" \
    -var "ar_repo=${AR_REPO}" \
    "${addr}" "${id}" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "  ✓ ${label}: imported"
  elif echo "$out" | grep -qE "already managed|Cannot import non-existent"; then
    echo "  · ${label}: already in state (or doesn't exist) — skipped"
  else
    echo "  ✗ ${label}: FAILED"
    echo "$out" | sed 's/^/      /'
  fi
}

# --- BigQuery dataset + 6 metadata tables ---
tf_import 'google_bigquery_dataset.ge_observability' \
  "projects/${PROJECT}/datasets/${DATASET}" \
  "dataset ${DATASET}"

for tbl in engine_metadata datastore_metadata resources_alive quota_config user_tier snapshot_meta; do
  tf_import "google_bigquery_table.${tbl}" \
    "projects/${PROJECT}/datasets/${DATASET}/tables/${tbl}" \
    "table ${tbl}"
done

# --- Service account ---
tf_import 'google_service_account.dashboard_sa' \
  "projects/${PROJECT}/serviceAccounts/${SA_ID}@${PROJECT}.iam.gserviceaccount.com" \
  "SA ${SA_ID}"

# --- Log sink ---
tf_import 'google_logging_project_sink.ge_observability_unified' \
  "projects/${PROJECT}/sinks/${SINK_NAME}" \
  "sink ${SINK_NAME}"

# --- Artifact Registry repo ---
tf_import 'google_artifact_registry_repository.dashboard' \
  "projects/${PROJECT}/locations/${REGION}/repositories/${AR_REPO}" \
  "AR repo ${AR_REPO}"

# --- Cloud Run service (only if deploy_cloud_run=true and it was created) ---
tf_import 'google_cloud_run_v2_service.dashboard[0]' \
  "projects/${PROJECT}/locations/${REGION}/services/${SERVICE_NAME}" \
  "Cloud Run ${SERVICE_NAME} (skipped if not enabled)"

# --- Audit config ---
tf_import 'google_project_iam_audit_config.discoveryengine_data_access' \
  "${PROJECT} discoveryengine.googleapis.com" \
  "audit config discoveryengine"

# --- Enabled APIs (idempotent — enable_api is set_on_destroy=false) ---
for api in \
  bigquery.googleapis.com \
  bigquerydatatransfer.googleapis.com \
  cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com \
  discoveryengine.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  logging.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com; do
  tf_import "google_project_service.required[\"${api}\"]" \
    "${PROJECT}/${api}" \
    "API ${api}"
done

echo ""
echo "==> Import pass complete. Now re-run:"
echo "    make tf-apply PROJECT=${PROJECT} REGION=${REGION} DATASET=${DATASET}"
