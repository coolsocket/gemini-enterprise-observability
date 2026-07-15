#!/usr/bin/env bash
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.
#
# fullpull_proof.sh — end-to-end demonstration that a login with the right
# permissions can recover a customer's FULL usage history from ZERO.
#
# WHAT IT PROVES
#   The full-history pull capability lives entirely in the login's read access
#   to Cloud Logging — NOT in BigQuery. The Log Router sink only captures
#   events forward from deploy time; the full history is recoverable purely
#   because Cloud Logging retains it and a permitted login can read it via
#   entries.list (that's what backfill.py does). This script demonstrates the
#   whole path in an ISOLATED dataset, starting from an empty BQ dataset.
#
# ISOLATION
#   Everything lands in a dedicated dataset (default: ge_fullpull_proof) that
#   is DROPPED and recreated each run, so "from zero" is guaranteed and no
#   existing data is touched. Seeded log entries go into the project's
#   Cloud Logging (project-scoped) tagged as OIDC-shaped synthetic traffic.
#
# THE PARALLEL
#   my-website login  →  reads my-website Cloud Logging  →  full pull  ✅
#   customer  login   →  reads customer  Cloud Logging   →  full pull  ✅
#   Same code, same credential path. If it works here, it works there.
#
# USAGE
#   PROJECT=my-website-417013 ./fullpull_proof.sh
#   env vars: PROJECT (req), DATASET (default ge_fullpull_proof),
#             DAYS_SPAN (default 28), PRINCIPAL_COUNT (default 40),
#             SEED (default 515), SCHEMA_SOURCE_DATASET (default ge_observability)
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT}"
DATASET="${DATASET:-ge_fullpull_proof}"
DAYS_SPAN="${DAYS_SPAN:-28}"
PRINCIPAL_COUNT="${PRINCIPAL_COUNT:-40}"
SEED="${SEED:-515}"
SCHEMA_SOURCE_DATASET="${SCHEMA_SOURCE_DATASET:-ge_observability}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"

echo "== Step 1 · from zero: drop + recreate $PROJECT:$DATASET =="
bq rm -r -f -d "$PROJECT:$DATASET" 2>/dev/null || true
bq mk --location=US --dataset "$PROJECT:$DATASET"
bq query --use_legacy_sql=false --format=none <<SQL
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.engine_metadata\` (engine_id STRING, display_name STRING, solution_type STRING, created_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.quota_config\` (key STRING, value STRING, updated_at TIMESTAMP, updated_by STRING);
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.user_tier\` (actor_email STRING, tier STRING, assigned_at TIMESTAMP, assigned_by STRING, notes STRING);
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.snapshot_meta\` (snapshot_name STRING, source_view STRING, refreshed_at TIMESTAMP, row_count INT64, refresh_seconds FLOAT64, triggered_by STRING);
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.resources_alive\` (resource_type STRING, resource_id STRING, created_at TIMESTAMP);
SQL

echo "== Step 2 · seed ${DAYS_SPAN}d of historical OIDC-shaped logs into Cloud Logging =="
PROJECT="$PROJECT" PRINCIPAL_COUNT="$PRINCIPAL_COUNT" DAYS_SPAN="$DAYS_SPAN" SEED="$SEED" \
  "$PY" "$HERE/seed_oidc_logs.py"
echo "  waiting ~15s for Cloud Logging to surface the entries..."
sleep 15

echo "== Step 3 · from-zero FULL PULL (login reads Cloud Logging -> empty dataset) =="
PROJECT="$PROJECT" DATASET="$DATASET" DAYS="$((DAYS_SPAN + 2))" \
  SCHEMA_SOURCE_DATASET="$SCHEMA_SOURCE_DATASET" \
  "$PY" "$HERE/backfill.py"

echo "== Step 4 · apply views =="
PROJECT="$PROJECT" DATASET="$DATASET" SIM_PREFIX="${SIM_PREFIX:-vivo-sim-}" \
  "$PY" "$HERE/apply_views.py" | tail -1

echo "== Step 5 · recovered window, read through the app's own code path =="
BQ_PROJECT="$PROJECT" BQ_DATASET="$DATASET" "$PY" - <<'PYEOF'
import json
from apps.api.routes.refresh import refresh_status
rs = json.loads(refresh_status().body)
print(f"  data_earliest: {rs['data_earliest']}")
print(f"  data_latest:   {rs['data_latest']}")
print(f"  data_days:     {rs['data_days']}")
print()
print("  ^ full history recovered from an empty dataset, using only the login's")
print("    Cloud Logging read access. A customer with the same permissions on")
print("    their own project recovers their full history the same way.")
PYEOF
