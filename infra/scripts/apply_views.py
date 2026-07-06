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

template = Path(__file__).resolve().parent.parent / "sql_templates" / "views.sql.tmpl"
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
ok = 0
errors: list[tuple[int, str]] = []
for i, stmt in enumerate(statements):
    try:
        client.query(stmt + ";").result()
        ok += 1
    except Exception as e:
        errors.append((i, str(e)[:200]))

print(f"applied {ok}/{len(statements)} statements")
for i, err in errors:
    print(f"  ERR stmt {i}: {err}")
sys.exit(1 if errors else 0)
