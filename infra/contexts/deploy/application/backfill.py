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

"""One-shot historical log import.

Pulls Cloud Logging entries that pre-date the sink target tables and
MERGEs them in via `insertId`. Idempotent (re-runs are no-op) and
gap-free (window tail deliberately overlaps sink coverage; MERGE
dedupes the overlap).

Usage:
    PROJECT=<id> DATASET=<name> DAYS=40 python3 backfill.py

Environment:
    PROJECT     required — the GCP project whose logs to backfill
    DATASET     required — the BQ dataset holding sink tables
    DAYS        optional (default 40) — how far back to look

Guarantees (locked by tests/unit/test_backfill.py + INV-deploy-backfill):
    1. filter parity  : SINK_FILTER_TEMPLATE below === terraform sink filter
    2. no dup        : MERGE INTO sink_target USING stage ON insertId
    3. no gap        : window = [NOW-DAYS, MIN(sink_ts) + 1 HOUR overlap]
    4. rate-limit    : Cloud Logging 429 → exponential backoff
    5. idempotent    : re-runs harmless (MERGE + WHEN NOT MATCHED)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

from google.auth import default as _google_auth_default
from google.auth.transport.requests import Request as _AuthRequest
from google.cloud import bigquery


# ============================================================
# Configuration — MUST stay byte-identical (post {project_id}
# substitution) to terraform/main.tf's sink filter. Enforced by
# tests/unit/test_backfill.py::test_backfill_filter_matches_terraform_sink.
# ============================================================
SINK_FILTER_TEMPLATE = """
(logName="projects/{project_id}/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity"
 OR logName="projects/{project_id}/logs/discoveryengine.googleapis.com%2Fgen_ai.user.message"
 OR logName="projects/{project_id}/logs/discoveryengine.googleapis.com%2Fgen_ai.choice")
OR (logName="projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity"
    AND protoPayload.serviceName="discoveryengine.googleapis.com")
OR (logName="projects/{project_id}/logs/cloudaudit.googleapis.com%2Fdata_access"
    AND (protoPayload.serviceName="discoveryengine.googleapis.com"
      OR protoPayload.serviceName="aiplatform.googleapis.com"))
"""


# The 5 sink target tables — same names GCP's Log Router creates.
# Each Cloud Logging entry's logName maps to one of these.
LOG_NAME_TO_TABLE = {
    "discoveryengine.googleapis.com/gemini_enterprise_user_activity":
        "discoveryengine_googleapis_com_gemini_enterprise_user_activity",
    "discoveryengine.googleapis.com/gen_ai.user.message":
        "discoveryengine_googleapis_com_gen_ai_user_message",
    "discoveryengine.googleapis.com/gen_ai.choice":
        "discoveryengine_googleapis_com_gen_ai_choice",
    "cloudaudit.googleapis.com/activity":
        "cloudaudit_googleapis_com_activity",
    "cloudaudit.googleapis.com/data_access":
        "cloudaudit_googleapis_com_data_access",
}


# Deliberate tail overlap with sink coverage — closes the pipeline-latency
# race gap. MERGE-on-insertId handles the resulting dup rows.
OVERLAP_WINDOW = dt.timedelta(hours=1)

# Cloud Logging API rate limits: 60 requests/second/project. Back off with
# a 1s, 2s, 4s, 8s progression on 429 (then give up).
MAX_BACKOFF_RETRIES = 4


# ============================================================
# Cloud Logging read (with pagination + 429 backoff)
# ============================================================
def _read_logging_page(token: str, project: str, filter_expr: str,
                       page_token: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "resourceNames": [f"projects/{project}"],
        "filter": filter_expr,
        "orderBy": "timestamp asc",
        "pageSize": 1000,
    }
    if page_token:
        body["pageToken"] = page_token

    for attempt in range(MAX_BACKOFF_RETRIES + 1):
        req = urllib.request.Request(
            "https://logging.googleapis.com/v2/entries:list",
            method="POST",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_BACKOFF_RETRIES:
                sleep_s = 2 ** attempt
                print(f"  ⚠ rate-limited, backoff {sleep_s}s (attempt {attempt+1}/{MAX_BACKOFF_RETRIES})",
                      file=sys.stderr)
                time.sleep(sleep_s)
                continue
            raise
    raise RuntimeError("unreachable: retry loop exited without return/raise")


def _read_all_entries(token: str, project: str, filter_expr: str) -> Iterable[dict[str, Any]]:
    page_token: str | None = None
    fetched = 0
    while True:
        payload = _read_logging_page(token, project, filter_expr, page_token)
        entries = payload.get("entries", [])
        fetched += len(entries)
        for e in entries:
            yield e
        page_token = payload.get("nextPageToken")
        if not page_token:
            return


# ============================================================
# BQ helpers
# ============================================================
def _sink_min_ts(bq: bigquery.Client, project: str, dataset: str) -> dt.datetime | None:
    """Return the earliest timestamp across all 5 sink target tables. That
    marks when the sink started ingesting; anything earlier is safe to
    backfill without dup risk (still MERGE for safety)."""
    candidates: list[dt.datetime] = []
    for tbl in LOG_NAME_TO_TABLE.values():
        try:
            for row in bq.query(
                f"SELECT MIN(timestamp) AS ts FROM `{project}.{dataset}.{tbl}`"
            ).result():
                if row.ts is not None:
                    candidates.append(row.ts)
        except Exception:
            # Table may not exist yet on fresh deploys — treat as "no sink data"
            continue
    return min(candidates) if candidates else None


def _stage_and_merge(bq: bigquery.Client, project: str, dataset: str,
                     table: str, entries: list[dict[str, Any]]) -> int:
    """Load a batch of entries into a staging table, then MERGE INTO
    the sink target on insertId. Returns number of rows inserted (new)."""
    if not entries:
        return 0
    stage_id = f"{project}.{dataset}.{table}__backfill_stage"
    # bq load JSON with schema autodetect handles nested payload shapes.
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    # Cloud Logging API returns camelCase JSON that bq load can ingest.
    ndjson = "\n".join(json.dumps(e) for e in entries)
    load_job = bq.load_table_from_file(
        file_obj=_wrap_bytes(ndjson.encode()),
        destination=stage_id,
        job_config=job_config,
    )
    load_job.result()

    # MERGE stage into target on insertId (guaranteed unique per entry).
    # WHEN NOT MATCHED → INSERT — never touches existing rows.
    target_id = f"{project}.{dataset}.{table}"
    merge_sql = f"""
    MERGE `{target_id}` t
    USING `{stage_id}` s
      ON t.insertId = s.insertId
    WHEN NOT MATCHED BY TARGET THEN INSERT ROW
    """
    merge_job = bq.query(merge_sql)
    merge_job.result()
    inserted = merge_job.num_dml_affected_rows or 0

    # Cleanup stage
    bq.delete_table(stage_id, not_found_ok=True)
    return inserted


def _wrap_bytes(b: bytes):
    import io
    return io.BytesIO(b)


# ============================================================
# Main
# ============================================================
def main() -> int:
    project = os.environ.get("PROJECT")
    dataset = os.environ.get("DATASET")
    days = int(os.environ.get("DAYS", "40"))
    # Almost always same as PROJECT (that's the whole point — pull the
    # tenant's own historical logs). Overridable via SOURCE_PROJECT for
    # test scenarios where BQ dataset lives in a different project than
    # the log-source project (e.g. sandbox demo mirror).
    source_project = os.environ.get("SOURCE_PROJECT", project)
    if not project or not dataset:
        print("ERROR: PROJECT= and DATASET= env vars required", file=sys.stderr)
        return 2

    # Auth for both Cloud Logging (REST) and BQ (Python client).
    creds, _ = _google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_AuthRequest())
    token = creds.token
    bq = bigquery.Client(project=project)

    # 1. Detect sink cutoff (empirical MIN over target tables).
    sink_min = _sink_min_ts(bq, project, dataset)
    now = dt.datetime.now(dt.timezone.utc)
    window_start = now - dt.timedelta(days=days)
    if sink_min is None:
        window_end = now  # no sink data yet — read up to now, dedupe later
        print(f"→ no sink data yet; window = [{window_start.isoformat()}, now)")
    else:
        window_end = sink_min + OVERLAP_WINDOW  # +1h overlap
        # Ensure sink_min is timezone-aware for isoformat comparison
        print(f"→ sink cutoff = {sink_min.isoformat()},"
              f" window = [{window_start.isoformat()}, {window_end.isoformat()}]"
              f" (=+{OVERLAP_WINDOW} overlap)")

    # 2. Construct filter (must match terraform sink filter bytewise).
    filter_expr = (
        SINK_FILTER_TEMPLATE.format(project_id=source_project).strip()
        + f' AND timestamp>="{window_start.isoformat()}"'
        + f' AND timestamp<"{window_end.isoformat()}"'
    )

    # 3. Read + bucket by logName + stage + MERGE per table.
    print(f"→ fetching from Cloud Logging (source={source_project}) paginated…")
    buckets: dict[str, list[dict[str, Any]]] = {t: [] for t in LOG_NAME_TO_TABLE.values()}
    total_read = 0
    for entry in _read_all_entries(token, source_project, filter_expr):
        # entry.logName is `projects/<id>/logs/<encoded-log-name>`
        raw_name = entry.get("logName", "").split("/logs/", 1)[-1]
        # URL-decode %2F → /
        decoded = raw_name.replace("%2F", "/")
        table = LOG_NAME_TO_TABLE.get(decoded)
        if table is None:
            continue  # Filter should exclude, but defensive
        buckets[table].append(entry)
        total_read += 1
        if total_read % 5000 == 0:
            print(f"  … {total_read} entries buffered")

    print(f"→ fetched {total_read} entries across {sum(1 for v in buckets.values() if v)} tables")

    # 4. MERGE each bucket.
    total_inserted = 0
    for table, entries in buckets.items():
        if not entries:
            continue
        inserted = _stage_and_merge(bq, project, dataset, table, entries)
        print(f"  ✓ {table}: fetched={len(entries)}  new_after_dedup={inserted}")
        total_inserted += inserted

    print(f"\n→ done: {total_inserted} new rows across {sum(1 for v in buckets.values() if v)} tables")
    print(f"  hint: POST /api/refresh to re-materialize snapshots with backfilled history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
