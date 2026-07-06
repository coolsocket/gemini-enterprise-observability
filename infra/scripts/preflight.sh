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

# Pre-flight for `make deploy-infra`. Lists everything the upcoming
# `terraform apply` will touch — especially the authoritative
# `google_project_iam_audit_config` for discoveryengine (which is the one
# resource that could overwrite something already configured by another
# tool). Also detects existing resources that would 409 without a prior
# `make tf-import-orphans`.
#
# Usage:
#   PROJECT=<p> DATASET=ge_observability REGION=us-central1 AR_REPO=ge-observability \
#     bash infra/scripts/preflight.sh
#
# Exits 0 if everything's clean.
# Exits 2 if there are conflicts requiring action (existing resources or
# an audit config diff). If the caller sets `CONFIRM=y`, exits 0 anyway.

set -uo pipefail

: "${PROJECT:?ERROR: PROJECT=<gcp-project-id> required}"
DATASET="${DATASET:-ge_observability}"
REGION="${REGION:-us-central1}"
BQ_LOCATION="${BQ_LOCATION:-US}"
AR_REPO="${AR_REPO:-ge-observability}"
SA_ID="${SA_ID:-ge-observability-sa}"
SINK_NAME="${SINK_NAME:-ge-observability-sink}"
CONFIRM="${CONFIRM:-}"

# tput colors if TTY, else no-op
if [ -t 1 ]; then
  G=$(tput setaf 2); Y=$(tput setaf 3); R=$(tput setaf 1); B=$(tput bold); N=$(tput sgr0)
else
  G=""; Y=""; R=""; B=""; N=""
fi

# Bookkeeping
existing_resources=()
audit_would_change="no"
current_audit=""

echo "${B}==> Pre-flight for ${PROJECT}${N}"
echo "    REGION=${REGION}  (Cloud Run + Artifact Registry)"
echo "    BQ_LOCATION=${BQ_LOCATION}  (BigQuery dataset)"
echo ""

# Warn if REGION and BQ_LOCATION won't co-locate — often a mistake, since
# data-residency or latency intent usually applies to both.
case "${REGION}:${BQ_LOCATION}" in
  us-*:US|us-*:us*) : ;;                     # us region + US multi-region: fine
  eu-*:EU|eu-*:eu*|europe-*:EU|europe-*:eu*) : ;;  # eu + EU
  asia-*:asia|asia-*:asia-*) : ;;                  # asia + asia multi-region
  "${REGION}:${REGION}") : ;;                # exact match: fine
  *)
    echo "${Y}⚠ REGION (${REGION}) and BQ_LOCATION (${BQ_LOCATION}) don't co-locate.${N}"
    echo "    If you want everything in the same physical region, pass e.g.:"
    echo "      make deploy-infra PROJECT=${PROJECT} REGION=${REGION} BQ_LOCATION=${REGION}"
    echo "    If you WANT data in a different region than compute (data-residency"
    echo "    intent), ignore this warning."
    echo ""
    ;;
esac

# --- 1. BQ dataset ---
if bq --project_id="$PROJECT" ls -d 2>/dev/null | awk '{print $1}' | grep -Fxq "$DATASET"; then
  echo "${Y}⚠ BQ dataset '${DATASET}' already exists.${N}"
  echo "    Two options:"
  echo "      (A) Adopt it:  make tf-import-orphans PROJECT=${PROJECT} DATASET=${DATASET}"
  echo "          → terraform will manage this existing dataset; our 6 metadata"
  echo "            tables get added; other tables in it are left untouched."
  echo "      (B) Use a different name (recommended if it belongs to another team):"
  echo "          make deploy-infra PROJECT=${PROJECT} DATASET=ge_observability_v2"
  existing_resources+=("dataset:${DATASET}")
else
  echo "${G}✓ BQ dataset '${DATASET}' does not exist — will be created.${N}"
fi
echo ""

# --- 2. Service account ---
SA_EMAIL="${SA_ID}@${PROJECT}.iam.gserviceaccount.com"
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" &>/dev/null; then
  echo "${Y}⚠ Service account '${SA_EMAIL}' already exists.${N}"
  echo "    Fix: make tf-import-orphans PROJECT=${PROJECT}"
  existing_resources+=("SA:${SA_ID}")
else
  echo "${G}✓ Service account '${SA_EMAIL}' does not exist — will be created.${N}"
fi
echo ""

# --- 3. Artifact Registry repo ---
if gcloud artifacts repositories describe "$AR_REPO" --project="$PROJECT" --location="$REGION" &>/dev/null; then
  echo "${Y}⚠ Artifact Registry repo '${AR_REPO}' already exists in ${REGION}.${N}"
  echo "    Fix: make tf-import-orphans PROJECT=${PROJECT} REGION=${REGION}"
  existing_resources+=("AR:${AR_REPO}")
else
  echo "${G}✓ Artifact Registry repo '${AR_REPO}' does not exist — will be created.${N}"
fi
echo ""

# --- 4. Log sink ---
if gcloud logging sinks describe "$SINK_NAME" --project="$PROJECT" &>/dev/null; then
  echo "${Y}⚠ Log sink '${SINK_NAME}' already exists.${N}"
  echo "    Fix: make tf-import-orphans PROJECT=${PROJECT}"
  existing_resources+=("sink:${SINK_NAME}")
else
  echo "${G}✓ Log sink '${SINK_NAME}' does not exist — will be created.${N}"
fi
echo ""

# --- 5. Audit config (the risky authoritative one) ---
echo "${B}==> Audit log config for discoveryengine.googleapis.com${N}"
current_audit=$(gcloud projects get-iam-policy "$PROJECT" \
  --format=json 2>/dev/null \
  | python3 -c "
import json, sys
p = json.load(sys.stdin)
for a in p.get('auditConfigs', []):
    if a.get('service') == 'discoveryengine.googleapis.com':
        for c in a.get('auditLogConfigs', []):
            exempt = c.get('exemptedMembers', [])
            print(f\"  {c['logType']}\" + (f\" (exempt: {len(exempt)} member(s))\" if exempt else ''))
        sys.exit(0)
print('  (no audit config set yet)')
")

echo "Current on GCP:"
echo "${current_audit}"
echo ""
echo "Terraform will set it to (this is authoritative — it will OVERWRITE any existing config):"
echo "  DATA_READ"
echo "  DATA_WRITE"
echo "  (no exempted_members)"
echo ""

if echo "$current_audit" | grep -qE "DATA_READ|DATA_WRITE"; then
  if echo "$current_audit" | grep -q "exempt:"; then
    echo "${R}⚠ Existing audit config has exempted members — those will be REMOVED.${N}"
    audit_would_change="yes-with-exempt"
  else
    echo "${G}✓ Existing audit config matches what we'd set — no functional change.${N}"
    audit_would_change="no"
  fi
else
  echo "${Y}⚠ Audit config for discoveryengine will be created (currently unset).${N}"
  audit_would_change="yes-create"
fi
echo ""

# --- Summary + confirmation gate ---
echo "${B}==> Summary${N}"
if [ ${#existing_resources[@]} -eq 0 ] && [ "$audit_would_change" != "yes-with-exempt" ]; then
  echo "${G}✓ Fresh project — nothing conflicts. Safe to proceed.${N}"
  exit 0
fi

if [ ${#existing_resources[@]} -gt 0 ]; then
  echo "${Y}⚠ Existing resources found (need tf-import-orphans OR different names):${N}"
  for r in "${existing_resources[@]}"; do echo "    - $r"; done
  echo ""
fi

if [ "$audit_would_change" = "yes-with-exempt" ]; then
  echo "${R}⚠ Audit config change will REMOVE existing exempted members.${N}"
  echo "    If those exemptions matter (e.g. cost control), add them to"
  echo "    the terraform config before applying."
  echo ""
fi

echo "${B}Continue anyway?${N}"
echo "  - Set ${B}CONFIRM=y${N} to auto-accept (for scripts / CI):"
echo "      CONFIRM=y make deploy-infra PROJECT=${PROJECT}"
echo "  - Or answer the prompt below."
echo ""

if [ "$CONFIRM" = "y" ]; then
  echo "CONFIRM=y set — proceeding."
  exit 0
fi

# Interactive prompt (skipped in non-TTY, exits 2 so caller sees the block)
if [ ! -t 0 ]; then
  echo "Non-interactive shell — refusing to auto-continue. Set CONFIRM=y to bypass."
  exit 2
fi

read -p "  Type 'yes' to continue: " reply
if [ "$reply" = "yes" ]; then
  echo "Proceeding."
  exit 0
fi
echo "Aborted."
exit 2
