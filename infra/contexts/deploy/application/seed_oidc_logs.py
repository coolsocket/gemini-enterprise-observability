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

"""One-shot CLI · seed OIDC-shaped log entries into Cloud Logging.

Usage:
  PROJECT=my-website-417013 PRINCIPAL_COUNT=50 DAYS_SPAN=20 SEED=42 \
    python3 seed_oidc_logs.py

Result: N * 10 entries land in Cloud Logging (5 activity + 3 gen_ai +
2 audit per principal). If the terraform sink is set up, they auto-
flow into BQ sink tables. Otherwise, `backfill.py` picks them up on
next run.

This runner is thin: it only does the POST. The generator
(`oidc_log_seed.build_oidc_entries`) is a pure module unit-tested in
tests/unit/test_r15_oidc_sim_seed.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from google.auth import default as _google_auth_default
from google.auth.transport.requests import Request as _AuthRequest

# Support running as a script (not as a module) — resolve the sibling.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oidc_log_seed import build_oidc_entries  # noqa: E402


BATCH_SIZE = 200  # entries per POST (Cloud Logging limit is 1000, stay well under)


def main() -> int:
    project = os.environ.get("PROJECT")
    if not project:
        print("ERROR: PROJECT env var required", file=sys.stderr)
        return 2

    n_principals = int(os.environ.get("PRINCIPAL_COUNT", "50"))
    days_span    = int(os.environ.get("DAYS_SPAN", "20"))
    seed         = int(os.environ.get("SEED", "42"))

    print(f"→ building {n_principals} principals × 10 entries ({n_principals*10} total) "
          f"spread across last {days_span} days, seed={seed}")
    entries = build_oidc_entries(n_principals, days_span, seed)
    # Every entry's logName already contains project id (embedded via
    # the builder). Double-check they target the requested project so
    # a copy-paste doesn't leak into someone else's logs.
    for e in entries:
        if project not in e["logName"]:
            print(f"ERROR: entry logName {e['logName']} doesn't target {project}", file=sys.stderr)
            return 3

    # Auth
    creds, _ = _google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_AuthRequest())
    token = creds.token

    # POST in batches
    url = "https://logging.googleapis.com/v2/entries:write"
    total_written = 0
    for i in range(0, len(entries), BATCH_SIZE):
        chunk = entries[i:i + BATCH_SIZE]
        body = {"entries": chunk, "partialSuccess": True}
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read() or "{}")
            errors = resp.get("partialErrors", {})
            written = len(chunk) - len(errors)
            total_written += written
            print(f"  · batch {i // BATCH_SIZE}: {written}/{len(chunk)} written")
            if errors:
                # Print the first couple of errors verbatim for triage.
                first = list(errors.items())[:2]
                print(f"    partial errors: {first}", file=sys.stderr)
        except urllib.error.HTTPError as e:
            print(f"ERROR: HTTP {e.code}: {e.read().decode(errors='replace')[:500]}", file=sys.stderr)
            return 4
        time.sleep(0.2)

    print(f"→ done: {total_written}/{len(entries)} entries written")
    print(f"  hint: Cloud Logging usually surfaces new entries within ~10s. "
          f"Then run `PROJECT={project} DATASET=ge_oidc_sim DAYS={days_span+1} "
          f"SCHEMA_SOURCE_DATASET=ge_observability python3 backfill.py` to pull them into BQ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
