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

# End-to-end test of `make backfill` — proves the full chain:
#   Cloud Logging → fetch → stage table → MERGE ON insertId → target table
# Also proves idempotency (re-run is noop) and bootstrap (target created
# on first run when sink hadn't populated it yet).
#
# Usage:
#   TARGET_PROJECT=my-website-417013 \
#   SOURCE_PROJECT=responsive-lens-421108 \  # where the real GE logs live
#   REGION=asia-southeast1 \
#   bash e2e_backfill.sh
#
# Creates a fresh dataset (ge_e2e_backfill_<epoch>), runs backfill twice,
# checks row counts + idempotency, prints PASS/FAIL, and by default
# leaves the dataset around for inspection (set CLEAN=1 to auto-delete).
#
# Requires the caller identity to have:
#   - bigquery.datasets.create + tables.create on TARGET_PROJECT
#   - logging.entries.list on SOURCE_PROJECT (privateLogViewer for data_access)

set -euo pipefail
cd "$(dirname "$0")/../../../.."

TARGET_PROJECT="${TARGET_PROJECT:-my-website-417013}"
SOURCE_PROJECT="${SOURCE_PROJECT:-responsive-lens-421108}"
BILLING_PROJECT="${BILLING_PROJECT:-${TARGET_PROJECT}}"
REGION="${REGION:-asia-southeast1}"
DAYS="${DAYS:-20}"
CLEAN="${CLEAN:-0}"
GRANT_USER="${GRANT_USER:-}"   # if set, given WRITER on the fresh dataset

TS=$(date +%s)
DATASET="ge_e2e_backfill_${TS}"
FULL_DS="${TARGET_PROJECT}:${DATASET}"

# Colors
if [ -t 1 ]; then G=$(tput setaf 2); R=$(tput setaf 1); Y=$(tput setaf 3); B=$(tput bold); N=$(tput sgr0); else G=""; R=""; Y=""; B=""; N=""; fi

echo "${B}=== e2e backfill test ===${N}"
echo "  target BQ  : ${TARGET_PROJECT}.${DATASET}"
echo "  source LOG : ${SOURCE_PROJECT} _Default bucket"
echo "  window     : past ${DAYS} days"
echo ""

# ---- 1. create fresh dataset ----
echo "${B}[1/6]${N} create fresh dataset ${FULL_DS}"
bq --project_id="${TARGET_PROJECT}" mk --location="${REGION}" --dataset "${FULL_DS}"
if [ -n "${GRANT_USER}" ]; then
  echo "  granting WRITER on ${FULL_DS} to ${GRANT_USER}"
  # Update dataset access list to include GRANT_USER as WRITER (needed
  # when BILLING_PROJECT != TARGET_PROJECT — the billing user still needs
  # dataEditor on the destination dataset).
  bq --project_id="${TARGET_PROJECT}" show --format=prettyjson "${FULL_DS}" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
d.setdefault('access', []).append({'role':'WRITER','userByEmail':'${GRANT_USER}'})
json.dump(d, sys.stdout)
" > /tmp/ds.json
  bq --project_id="${TARGET_PROJECT}" update --source /tmp/ds.json "${FULL_DS}" > /dev/null
fi
echo "  ✓ dataset created"

# ---- 2. run backfill (SCENARIO A: bootstrap — target tables absent) ----
echo ""
echo "${B}[2/6]${N} first backfill run (SCENARIO A · bootstrap)"
PROJECT="${TARGET_PROJECT}" \
DATASET="${DATASET}" \
SOURCE_PROJECT="${SOURCE_PROJECT}" \
BILLING_PROJECT="${BILLING_PROJECT}" \
SCHEMA_SOURCE_DATASET="${SCHEMA_SOURCE_DATASET:-}" \
DAYS="${DAYS}" \
GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-/tmp/user-adc.json}" \
GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_QUOTA_PROJECT:-cloud-llm-preview1}" \
  ./.venv/bin/python3 infra/contexts/deploy/application/backfill.py

# ---- 3. record row counts after run 1 ----
echo ""
echo "${B}[3/6]${N} row counts after run 1"
declare -A COUNT1
tables=(
  "discoveryengine_googleapis_com_gemini_enterprise_user_activity"
  "discoveryengine_googleapis_com_gen_ai_choice"
  "discoveryengine_googleapis_com_gen_ai_user_message"
  "cloudaudit_googleapis_com_activity"
  "cloudaudit_googleapis_com_data_access"
)
for t in "${tables[@]}"; do
  # Tolerate absent table (that logName had 0 entries in the window
  # → sink target never got created → COUNT would 404).
  n=$(bq --project_id="${TARGET_PROJECT}" --location="${REGION}" query --nouse_legacy_sql --format=csv --quiet \
        "SELECT COUNT(*) FROM \`${TARGET_PROJECT}.${DATASET}.${t}\`" 2>/dev/null | tail -1 \
        || echo "0")
  n="${n:-0}"
  COUNT1["${t}"]="${n}"
  printf "  %-64s %s\n" "${t}" "${n}"
done

# ---- 4. re-run backfill (SCENARIO C: idempotency) ----
echo ""
echo "${B}[4/6]${N} re-run backfill (SCENARIO C · idempotency)"
PROJECT="${TARGET_PROJECT}" \
DATASET="${DATASET}" \
SOURCE_PROJECT="${SOURCE_PROJECT}" \
BILLING_PROJECT="${BILLING_PROJECT}" \
SCHEMA_SOURCE_DATASET="${SCHEMA_SOURCE_DATASET:-}" \
DAYS="${DAYS}" \
GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-/tmp/user-adc.json}" \
GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_QUOTA_PROJECT:-cloud-llm-preview1}" \
  ./.venv/bin/python3 infra/contexts/deploy/application/backfill.py

# ---- 5. verify idempotency ----
echo ""
echo "${B}[5/6]${N} verify row counts unchanged (idempotency)"
FAIL=0
for t in "${tables[@]}"; do
  n2=$(bq --project_id="${TARGET_PROJECT}" --location="${REGION}" query --nouse_legacy_sql --format=csv --quiet \
        "SELECT COUNT(*) FROM \`${TARGET_PROJECT}.${DATASET}.${t}\`" 2>/dev/null | tail -1 \
        || echo "0")
  n2="${n2:-0}"
  n1="${COUNT1[$t]}"
  if [ "${n1}" = "${n2}" ]; then
    printf "  ${G}✓${N} %-64s run1=%s  run2=%s  (matches)\n" "${t}" "${n1}" "${n2}"
  else
    printf "  ${R}✗${N} %-64s run1=%s  run2=%s  (DIFFERS → dup risk)\n" "${t}" "${n1}" "${n2}"
    FAIL=1
  fi
done

# ---- 6. summary + cleanup ----
echo ""
echo "${B}[6/6]${N} summary"
if [ ${FAIL} -eq 0 ]; then
  echo "  ${G}${B}PASS${N} — backfill is idempotent + bootstrap works"
else
  echo "  ${R}${B}FAIL${N} — see mismatches above"
fi

if [ "${CLEAN}" = "1" ]; then
  echo ""
  echo "  CLEAN=1 → deleting ${FULL_DS}"
  bq --project_id="${TARGET_PROJECT}" rm -r -f --dataset "${FULL_DS}"
  echo "  ✓ deleted"
else
  echo ""
  echo "  dataset left at ${FULL_DS} for inspection (set CLEAN=1 to auto-delete)"
fi

exit ${FAIL}
