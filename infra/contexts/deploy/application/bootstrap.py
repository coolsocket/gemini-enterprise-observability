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
import sys
import urllib.request

import google.auth
import google.auth.transport.requests

PROJECT = os.environ.get("PROJECT") or os.environ.get("BQ_PROJECT")
DATASET = os.environ.get("DATASET") or os.environ.get("BQ_DATASET", "ge_observability")
COLLECTION = os.environ.get("COLLECTION", "default_collection")
PURCHASED_SEATS = os.environ.get("PURCHASED_SEATS", "50")
CLAIMED_WINDOW_DAYS = os.environ.get("CLAIMED_WINDOW_DAYS", "30")

if not PROJECT:
    print("ERROR: PROJECT env var required", file=sys.stderr)
    sys.exit(1)


_creds = None


def _access_token() -> str:
    """Get an OAuth token via ADC (works in containers, CI, and locally).

    Uses google.auth.default() so it matches how google-cloud-bigquery picks
    its identity — no shell-out to `gcloud`, no requirement that the CLI is
    on PATH. Refreshes the cached credential when the token expires.
    """
    global _creds
    if _creds is None:
        _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _creds.valid:
        _creds.refresh(google.auth.transport.requests.Request())
    return _creds.token


def _http(url: str, *, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {_access_token()}")
    req.add_header("x-goog-user-project", PROJECT)
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


def fetch_license_configs() -> list[dict]:
    """Pull real GE seat count + subscription tier. This IS a documented API despite
    older guides claiming otherwise. Returns list of licenseConfig objects."""
    url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT}/locations/global/licenseConfigs"
    try:
        data = _http(url)
        return data.get("licenseConfigs", [])
    except Exception as e:
        print(f"  warn: could not fetch licenseConfigs ({e})")
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


def enable_engine_observability(engines: list[dict]) -> None:
    """PATCH each engine to turn on observabilityConfig.

    Discovered 2026-07-06 (thanks issue #1 from panliuyang-debug): Engine
    carries an `observabilityConfig` field in v1/v1beta/v1alpha with:
      - observabilityEnabled     ↔ OpenTelemetry Instrumentation toggle
      - sensitiveLoggingEnabled  ↔ Prompt & Response Logging toggle
    Previously documented as "no API — must click in GE Admin Console".
    This function flips both to `true` for every engine, removing the
    manual step. Only 'Enable Feedback' still has no API and stays manual.

    Set env var SKIP_OBSERVABILITY=true to skip (e.g. if the operator wants
    to leave the toggles alone for some engines).
    """
    if os.environ.get("SKIP_OBSERVABILITY", "").lower() == "true":
        print("  SKIP_OBSERVABILITY=true — leaving observabilityConfig alone")
        return
    ok = 0
    failed: list[tuple[str, str]] = []
    for e in engines:
        engine_full = e["name"]  # projects/…/engines/<id>
        url = (f"https://discoveryengine.googleapis.com/v1alpha/{engine_full}"
               f"?updateMask=observabilityConfig")
        body = {"observabilityConfig": {
            "observabilityEnabled": True,
            "sensitiveLoggingEnabled": True,
        }}
        try:
            _http(url, method="PATCH", body=body)
            ok += 1
        except Exception as ex:
            failed.append((engine_full.split("/")[-1], str(ex)[:200]))
    total = len(engines)
    print(f"  observabilityConfig: enabled on {ok}/{total} engine(s)")
    for eid, err in failed:
        print(f"     ✗ {eid}: {err}")
    if ok:
        print("     (observabilityEnabled=OpenTelemetry, sensitiveLoggingEnabled=Prompt&Response Logging)")
        print("     ⚠ 'Enable Feedback' still has no API — flip manually in GE Admin Console if needed.")


def seed_quota_config() -> None:
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)

    # 1) Static seeds (only if missing, don't overwrite user changes).
    # Tier defaults surface in Quota.tsx as editable numbers — admins
    # tune them via the UI (POST /api/quota/config). Bootstrap only
    # sets them if absent so re-runs are idempotent and don't clobber
    # admin edits. Values are starting points, all editable in-app.
    TIER_DEFAULTS = [
        # standard tier (baseline license)
        ("tier.standard.chat_daily",           "50"),   # ~10 sessions/day
        ("tier.standard.deep_research_daily",   "3"),
        ("tier.standard.agent_create_daily",    "1"),
        ("tier.standard.storage_gib",          "10"),
        # plus tier (SUBSCRIPTION_TIER_SEARCH_AND_ASSISTANT)
        ("tier.plus.chat_daily",              "300"),
        ("tier.plus.deep_research_daily",      "20"),
        ("tier.plus.agent_create_daily",       "10"),
        ("tier.plus.storage_gib",             "100"),
    ]
    for key, value in ([("purchased_seats", PURCHASED_SEATS),
                        ("claimed_window_days", CLAIMED_WINDOW_DAYS)]
                       + TIER_DEFAULTS):
        sql = f"""
        MERGE `{PROJECT}.{DATASET}.quota_config` t
        USING (SELECT '{key}' k, '{value}' v) s
        ON t.key = s.k
        WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
        VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'bootstrap')
        """
        client.query(sql).result()

    # 2) Dynamic: sync from live licenseConfigs API (overwrite — this is source of truth)
    configs = fetch_license_configs()
    if configs:
        total = 0
        by_tier: dict[str, int] = {}
        for c in configs:
            cnt = int(c.get("licenseCount", "0"))
            total += cnt
            tier = c.get("subscriptionTier", "UNKNOWN")
            by_tier[tier] = by_tier.get(tier, 0) + cnt
        # Write authoritative seat count from API
        for k, v in [
            ("license.total_seats", str(total)),
            ("license.config_count", str(len(configs))),
            ("license.raw", json.dumps(configs)),  # keep full data for debug
        ]:
            client.query(f"""
                MERGE `{PROJECT}.{DATASET}.quota_config` t
                USING (SELECT '{k}' k, @v v) s
                ON t.key = s.k
                WHEN MATCHED THEN UPDATE SET value = s.v, updated_at = CURRENT_TIMESTAMP(), updated_by = 'bootstrap-license-api'
                WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
                  VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'bootstrap-license-api')
            """, job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("v", "STRING", v)]
            )).result()
        for tier, cnt in by_tier.items():
            client.query(f"""
                MERGE `{PROJECT}.{DATASET}.quota_config` t
                USING (SELECT 'license.seats.{tier}' k, '{cnt}' v) s
                ON t.key = s.k
                WHEN MATCHED THEN UPDATE SET value = s.v, updated_at = CURRENT_TIMESTAMP(), updated_by = 'bootstrap-license-api'
                WHEN NOT MATCHED THEN INSERT (key, value, updated_at, updated_by)
                  VALUES (s.k, s.v, CURRENT_TIMESTAMP(), 'bootstrap-license-api')
            """).result()
        print(f"  seeded quota_config (licenseCount={total}, tiers={list(by_tier.keys())})")
    else:
        print("  seeded quota_config (no licenseConfigs found — using PURCHASED_SEATS env)")


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

    # 6. Turn on per-engine observabilityConfig (replaces the old manual step).
    #    See docs/GE_CONSOLE_SETUP.md for what this maps to in the UI.
    print("→ engine observabilityConfig")
    enable_engine_observability(engines)

    print()
    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
