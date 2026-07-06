#!/usr/bin/env python3
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

"""Render and apply parameterized BQ views.

Usage:
    PROJECT=<gcp-project-id> DATASET=ge_observability python3 apply_views.py

Environment variables:
    PROJECT       GCP project ID (required)
    DATASET       BQ dataset name (default: ge_observability)
    SIM_PATTERN   LIKE pattern that classifies an actor as SIMULATED
                  (default: '__sim_disabled__' — i.e. nothing matches)
                  Set to e.g. 'mycorp-sim-%' if you seeded sim service accounts.
    SIM_PREFIX    Prefix stripped from principal emails at query time so that
                  seed/simulated accounts display as generic actors.
                  (default: 'sim-'). Set to your seed convention, e.g. 'demo-'.
    DRY_RUN       if 'true', print SQL and exit
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = os.environ.get("PROJECT") or os.environ.get("BQ_PROJECT")
DATASET = os.environ.get("DATASET") or os.environ.get("BQ_DATASET", "ge_observability")
SIM_PATTERN = os.environ.get("SIM_PATTERN", "__sim_disabled__")
SIM_PREFIX = os.environ.get("SIM_PREFIX", "sim-")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"

if not PROJECT:
    print("ERROR: PROJECT env var required", file=sys.stderr)
    sys.exit(1)

# Repo layout after Phase 4:
#   infra/sql_templates/views.sql.tmpl
#   infra/contexts/deploy/application/apply_views.py   ← this file
# So four .parent hops from __file__ land on infra/.
template = Path(__file__).resolve().parent.parent.parent.parent / "sql_templates" / "views.sql.tmpl"
sql = template.read_text()
sql = (sql
       .replace("{{PROJECT}}", PROJECT)
       .replace("{{DATASET}}", DATASET)
       .replace("{{SIM_PATTERN}}", SIM_PATTERN)
       .replace("{{SIM_PREFIX}}", SIM_PREFIX))

if DRY_RUN:
    print(sql)
    sys.exit(0)

# Apply via google.cloud.bigquery client
from google.cloud import bigquery
client = bigquery.Client(project=PROJECT)

# BQ doesn't support multi-statement scripts well via Python — split on ;
# (each CREATE OR REPLACE VIEW is independent)
# IMPORTANT: strip `--` line comments BEFORE splitting, otherwise a `;` inside
# a comment slices a statement in half.
import re as _re
sql_no_comments = _re.sub(r"--[^\n]*", "", sql)
raw = [s.strip() for s in sql_no_comments.split(";")]
statements = [s for s in raw if "CREATE OR REPLACE" in s.upper()]


def _view_name(stmt: str) -> str:
    """Extract the target view name from a CREATE OR REPLACE VIEW statement."""
    m = _re.search(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+`?([^`\s(]+)`?", stmt, _re.IGNORECASE)
    return m.group(1).split(".")[-1] if m else "unknown"


def _missing_table(err: str) -> str | None:
    """If a BQ error is a 404-not-found on a specific table, return the table
    name. Otherwise None. Used to distinguish 'waiting for logs to flow' from
    real syntax/permission problems."""
    m = _re.search(r"Not found: Table [^\s]+\.([A-Za-z_][A-Za-z0-9_]*)", err)
    return m.group(1) if m else None


# Tables auto-created by GCP when the first matching log entry flows through
# the sink. On a truly fresh deploy these do not exist yet — that's expected,
# not an error. Categorize them so the summary is actionable.
SINK_TARGETS = {
    "cloudaudit_googleapis_com_activity",
    "cloudaudit_googleapis_com_data_access",
    "cloudaudit_googleapis_com_system_event",
    "discoveryengine_googleapis_com_gemini_enterprise_user_activity",
    "discoveryengine_googleapis_com_gen_ai_choice",
    "discoveryengine_googleapis_com_gen_ai_user_message",
}

# Tables created by `terraform apply` (see terraform/main.tf § 3). If any of
# these are missing, the operator forgot to run tf-apply first — that's a
# real error, but with a specific, well-known fix.
TERRAFORM_TABLES = {
    "engine_metadata",
    "datastore_metadata",
    "resources_alive",
    "quota_config",
    "user_tier",
    "snapshot_meta",
}

ok: list[str] = []
skipped_waiting_logs: list[tuple[str, str]] = []       # (view, missing_table)
skipped_missing_view_dep: list[tuple[str, str]] = []   # (view, missing_view — downstream of above)
skipped_missing_tf_table: list[tuple[str, str]] = []   # (view, missing_metadata_table)
real_errors: list[tuple[str, str]] = []                # everything else

for stmt in statements:
    view = _view_name(stmt)
    try:
        client.query(stmt + ";").result()
        ok.append(view)
    except Exception as e:
        err = str(e)[:400]
        missing = _missing_table(err)
        if missing in SINK_TARGETS:
            skipped_waiting_logs.append((view, missing))
        elif missing in TERRAFORM_TABLES:
            skipped_missing_tf_table.append((view, missing))
        elif missing and missing.startswith("v_"):
            # A downstream view whose dependency also failed — cascade
            skipped_missing_view_dep.append((view, missing))
        else:
            real_errors.append((view, err))

total = len(statements)
print(f"applied {len(ok)}/{total} views")

if skipped_waiting_logs:
    print()
    print(f"⏳ {len(skipped_waiting_logs)} view(s) skipped — waiting for log-sink tables:")
    seen_tables = sorted({t for _, t in skipped_waiting_logs})
    for t in seen_tables:
        print(f"     • {t}")
    print("   These tables are auto-created by BigQuery the first time a matching log")
    print("   entry lands in the sink. Enable GE Console toggles per engine (OpenTelemetry")
    print("   Instrumentation, Prompt & Response Logging), send a bit of traffic, then re-")
    print(f"   run: PROJECT={PROJECT} DATASET={DATASET} python3 infra/contexts/deploy/application/apply_views.py")

if skipped_missing_tf_table:
    print()
    print(f"⚠ {len(skipped_missing_tf_table)} view(s) skipped — Terraform-managed table missing:")
    seen = sorted({t for _, t in skipped_missing_tf_table})
    for t in seen:
        print(f"     • {t}")
    print("   These are created by `terraform apply` (see terraform/main.tf § 3). Run:")
    print(f"     make tf-apply PROJECT={PROJECT} DATASET={DATASET}")
    print("   then re-run this command.")

if skipped_missing_view_dep:
    print()
    print(f"⚠ {len(skipped_missing_view_dep)} view(s) skipped — depend on views above that couldn't be created:")
    for view, dep in skipped_missing_view_dep:
        print(f"     • {view}  (needs {dep})")

if real_errors:
    print()
    print(f"❌ {len(real_errors)} view(s) failed with unexpected errors:")
    for view, err in real_errors:
        print(f"     • {view}: {err}")

# Exit 0 if the only failures are "waiting for logs" — those are expected on
# fresh deploys and the operator should just re-run later. Missing Terraform
# tables and real errors are both exit-1: the operator needs to act.
sys.exit(1 if (real_errors or skipped_missing_tf_table) else 0)
