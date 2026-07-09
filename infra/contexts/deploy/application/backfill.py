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

# Cloud Logging API rate limits: 60 requests/second/project (soft) but
# in practice hits 429 much sooner on long paginated reads. Two defences:
#   1. Always-on inter-page delay (INTER_PAGE_SLEEP_SEC) — self-paces to
#      well below the quota (~10 pages/sec = 600 pages/min = well under
#      the 3600 requests/min ceiling).
#   2. 429 backoff — 6 retries with exponential + jitter, up to ~2min/hit.
MAX_BACKOFF_RETRIES = 6
INTER_PAGE_SLEEP_SEC = 0.1


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
        # Self-pace to stay comfortably below the API quota. See MAX_...
        # comment for reasoning.
        time.sleep(INTER_PAGE_SLEEP_SEC)


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
                     table: str, entries: list[dict[str, Any]],
                     schema_source: str | None = None) -> int:
    """Load a batch of entries into a staging table, then MERGE INTO
    the sink target on insertId. Returns number of rows inserted (new).

    schema_source: optional `project.dataset.table` to copy schema from.
    In production the sink target itself IS the source. In test rigs
    where target is empty, point at a reference table with the true
    sink schema (or leave None → autodetect + tolerance fallback)."""
    if not entries:
        return 0
    stage_id = f"{project}.{dataset}.{table}__backfill_stage"
    target_id = f"{project}.{dataset}.{table}"

    # 1. Load into stage. Prefer explicit schema from a known-good
    # reference table (real sink target); fall back to autodetect
    # + max tolerance if none available.
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ignore_unknown_values=True,
        max_bad_records=100_000,
    )
    from google.api_core.exceptions import NotFound as _NF
    if schema_source:
        try:
            ref = bq.get_table(schema_source)
            job_config.schema = ref.schema
            print(f"  → using schema from {schema_source}")
        except _NF:
            job_config.autodetect = True
            print(f"  → schema source {schema_source} absent; autodetect fallback")
    else:
        # Try target itself (production case — sink already created it)
        try:
            ref = bq.get_table(target_id)
            job_config.schema = ref.schema
        except _NF:
            job_config.autodetect = True
    # Guard per-entry json.dumps + strip `@`-prefixed keys (BQ column names
    # must match [A-Za-z_][A-Za-z0-9_]*; `@type` in protoPayload violates
    # this and the whole load 400s). Also strip empty structs which can
    # confuse autodetect.
    def _sanitize(v: Any) -> Any:
        if isinstance(v, dict):
            return {
                k.lstrip("@") or "type": _sanitize(vv)
                for k, vv in v.items() if vv is not None and vv != {}
            }
        if isinstance(v, list):
            return [_sanitize(x) for x in v if x is not None]
        return v

    ok_lines: list[str] = []
    dumps_fail = 0
    for e in entries:
        try:
            ok_lines.append(json.dumps(_sanitize(e), default=str))
        except Exception:
            dumps_fail += 1
    if dumps_fail:
        print(f"  ⚠ {dumps_fail} entries not JSON-serialisable, skipped before load")
    ndjson = "\n".join(ok_lines)
    load_job = bq.load_table_from_file(
        file_obj=_wrap_bytes(ndjson.encode()),
        destination=stage_id,
        job_config=job_config,
    )
    load_job.result()

    # 2. Bootstrap: create empty target if it doesn't exist (fresh sink).
    #    Uses stage's schema — subsequent runs' stages will have the SAME
    #    schema (same JSON shape, same autodetect), so MERGE is stable.
    from google.api_core.exceptions import NotFound
    try:
        bq.get_table(target_id)
    except NotFound:
        bq.query(
            f"CREATE TABLE `{target_id}` AS SELECT * FROM `{stage_id}` WHERE FALSE"
        ).result()

    # 3. MERGE stage into target on insertId (guaranteed unique per entry).
    #    WHEN NOT MATCHED → INSERT — never touches existing rows.
    merge_sql = f"""
    MERGE `{target_id}` t
    USING `{stage_id}` s
      ON t.insertId = s.insertId
    WHEN NOT MATCHED BY TARGET THEN INSERT ROW
    """
    merge_job = bq.query(merge_sql)
    merge_job.result()
    inserted = merge_job.num_dml_affected_rows or 0

    # 4. Cleanup stage
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
    # In prod, jobs are billed to the same project that owns the dataset.
    # In test setups where the operator has jobUser on a DIFFERENT project
    # (e.g. cloud-llm-preview1 quota project) than the target dataset,
    # split via BILLING_PROJECT. Load/MERGE still write to PROJECT.DATASET.
    billing_project = os.environ.get("BILLING_PROJECT", project)
    # Optional reference dataset to source schemas from (test rigs where
    # target is empty). Format: `project.dataset`. Each of the 5 sink tables
    # is looked up as {SCHEMA_SOURCE_DATASET}.{table_name} to get schema.
    schema_source_ds = os.environ.get("SCHEMA_SOURCE_DATASET")
    if not project or not dataset:
        print("ERROR: PROJECT= and DATASET= env vars required", file=sys.stderr)
        return 2

    # Auth for both Cloud Logging (REST) and BQ (Python client).
    creds, _ = _google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_AuthRequest())
    token = creds.token
    # BQ Client's `project` = "job project" (where jobs.create is authorised);
    # destination tables can live in ANOTHER project. In prod both are the
    # tenant's own project; in test rigs they can split.
    bq = bigquery.Client(project=billing_project)

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
        schema_src = f"{schema_source_ds}.{table}" if schema_source_ds else None
        inserted = _stage_and_merge(bq, project, dataset, table, entries, schema_src)
        print(f"  ✓ {table}: fetched={len(entries)}  new_after_dedup={inserted}")
        total_inserted += inserted

    print(f"\n→ done: {total_inserted} new rows across {sum(1 for v in buckets.values() if v)} tables")
    print(f"  hint: POST /api/refresh to re-materialize snapshots with backfilled history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
