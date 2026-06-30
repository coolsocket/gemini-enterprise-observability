#!/usr/bin/env python3
"""Bootstrap metadata tables that views depend on.

Idempotent — safe to re-run. Pulls engine_metadata / datastore_metadata via
Discovery Engine API, syncs resources_alive, seeds quota_config defaults.

Usage:
    PROJECT=my-project DATASET=ge_observability python3 bootstrap.py

Env vars:
    PROJECT     GCP project (required)
    DATASET     BQ dataset name (default: ge_observability)
    COLLECTION  Discovery Engine collection ID (default: default_collection)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

PROJECT = os.environ.get("PROJECT") or os.environ.get("BQ_PROJECT")
DATASET = os.environ.get("DATASET") or os.environ.get("BQ_DATASET", "ge_observability")
COLLECTION = os.environ.get("COLLECTION", "default_collection")
PURCHASED_SEATS = os.environ.get("PURCHASED_SEATS", "50")
CLAIMED_WINDOW_DAYS = os.environ.get("CLAIMED_WINDOW_DAYS", "30")

if not PROJECT:
    print("ERROR: PROJECT env var required", file=sys.stderr)
    sys.exit(1)


def _gcloud_token() -> str:
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


def _http(url: str, *, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {_gcloud_token()}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode() or "{}")


def fetch_engines() -> list[dict]:
    url = f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/collections/{COLLECTION}/engines"
    data = _http(url)
    return data.get("engines", [])


def fetch_datastores() -> list[dict]:
    url = f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/collections/{COLLECTION}/dataStores"
    data = _http(url)
    return data.get("dataStores", [])


def fetch_agents_for_engine(engine_id: str) -> list[dict]:
    """Best-effort — only works if assistant is configured."""
    url = (f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT}/locations/global/"
           f"collections/{COLLECTION}/engines/{engine_id}/assistants/default_assistant/agents")
    try:
        data = _http(url)
        return data.get("agents", [])
    except Exception:
        return []


def load_table(table_id: str, rows: list[dict]) -> None:
    """Truncate-and-load via load job (bypasses streaming buffer, idempotent)."""
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)
    table_ref = client.dataset(DATASET).table(table_id)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    if not rows:
        # Empty load to truncate the table
        rows = []
    data = "\n".join(json.dumps(r) for r in rows).encode() or b""
    import io
    job = client.load_table_from_file(io.BytesIO(data), table_ref, job_config=job_config)
    job.result()
    print(f"  loaded {len(rows)} rows into {table_id}")


def seed_quota_config() -> None:
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)
    # MERGE so we only insert if missing (don't overwrite user changes)
    for key, value in [("purchased_seats", PURCHASED_SEATS),
                        ("claimed_window_days", CLAIMED_WINDOW_DAYS)]:
        sql = f"""
        MERGE `{PROJECT}.{DATASET}.quota_config` t
        USING (SELECT '{key}' k, '{value}' v) s
        ON t.key = s.k
        WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
        VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'bootstrap')
        """
        client.query(sql).result()
    print(f"  seeded quota_config (idempotent)")


def main():
    print(f"Bootstrapping {PROJECT}.{DATASET}")
    print(f"  COLLECTION: {COLLECTION}")
    print()

    # 1. engine_metadata
    print("→ engine_metadata")
    engines = fetch_engines()
    engine_rows = [{
        "engine_id":     e["name"].split("/")[-1],
        "display_name":  e.get("displayName", ""),
        "solution_type": e.get("solutionType", ""),
        "data_store_id": (e.get("dataStoreIds") or [""])[0],
        "create_time":   e.get("createTime"),
    } for e in engines]
    load_table("engine_metadata", engine_rows)

    # 2. datastore_metadata
    print("→ datastore_metadata")
    datastores = fetch_datastores()
    ds_rows = [{
        "datastore_id":      d["name"].split("/")[-1],
        "display_name":      d.get("displayName", ""),
        "industry_vertical": d.get("industryVertical", ""),
        "create_time":       d.get("createTime"),
    } for d in datastores]
    load_table("datastore_metadata", ds_rows)

    # 3. resources_alive (engines + datastores + agents)
    print("→ resources_alive")
    alive_rows: list[dict] = []
    for e in engines:
        alive_rows.append({
            "resource_id":   e["name"].split("/")[-1],
            "display_name":  e.get("displayName", ""),
            "resource_type": "engine",
            "state":         "alive",
        })
    for d in datastores:
        alive_rows.append({
            "resource_id":   d["name"].split("/")[-1],
            "display_name":  d.get("displayName", ""),
            "resource_type": "datastore",
            "state":         "alive",
        })
    for e in engines:
        for a in fetch_agents_for_engine(e["name"].split("/")[-1]):
            alive_rows.append({
                "resource_id":   a["name"].split("/")[-1],
                "display_name":  a.get("displayName", ""),
                "resource_type": "agent",
                "state":         "alive",
            })
    load_table("resources_alive", alive_rows)

    # 4. quota_config (idempotent seeding)
    print("→ quota_config")
    seed_quota_config()

    # 5. snapshot_meta — leave empty; populated on first refresh
    print("→ snapshot_meta (left empty; populated on first refresh)")

    print()
    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
