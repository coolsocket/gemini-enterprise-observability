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

"""RED (2026-07-15) — snapshots never auto-refresh, so the dashboard
freezes at the last manual `POST /api/refresh`.

Reporter symptom: vivo shows only 7.6–7.9 data. Diagnosis:
  * sink raw tables run 7.6 → today (live, incremental) ✅
  * snapshots (s_*) frozen at 2026-07-09 09:05 — the last manual refresh ❌

The code comment claims "Snapshots are refreshed by BQ Scheduled Query",
but no such scheduled query exists in terraform, and there is no
in-process fallback loop (unlike the seat/license loop). So on any
deployment where nobody wires a cron, snapshots go stale the moment
the first manual refresh ages out — the dashboard's upper bound sticks
at whenever refresh last ran.

Fix: mirror the existing seat auto-refresh loop for snapshots.
  * SNAPSHOT_REFRESH_INTERVAL_SEC config (default > 0; 0 disables)
  * _start_snapshot_refresh_loop() background task
  * wired into main.py lifespan alongside the seat loop
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_snapshot_refresh_interval_config_exists() -> None:
    src = (REPO / "apps/api/shared/common.py").read_text()
    assert "SNAPSHOT_REFRESH_INTERVAL_SEC" in src, (
        "common.py must define SNAPSHOT_REFRESH_INTERVAL_SEC (seconds "
        "between automatic snapshot re-materializations; 0 disables). "
        "Without an auto-refresh cadence, snapshots freeze at the last "
        "manual POST /api/refresh — the vivo 7.9 upper-bound bug."
    )
    # It should read from the environment with a sane non-zero default.
    m = re.search(
        r"SNAPSHOT_REFRESH_INTERVAL_SEC\s*=\s*int\(\s*os\.environ\.get\(",
        src,
    )
    assert m, (
        "SNAPSHOT_REFRESH_INTERVAL_SEC should be an env-overridable int, "
        "mirroring LICENSE_REFRESH_INTERVAL_SEC."
    )


def test_snapshot_refresh_loop_exists() -> None:
    src = (REPO / "apps/api/routes/refresh.py").read_text()
    assert "def _start_snapshot_refresh_loop" in src, (
        "refresh.py must define _start_snapshot_refresh_loop() — a "
        "background asyncio loop that periodically calls refresh_now(), "
        "mirroring _start_seat_refresh_loop(). This is the in-process "
        "guarantee that snapshots stay current on every deploy target "
        "(Cloud Run, VM, local), independent of any BQ Scheduled Query."
    )
    # The loop body must actually re-materialize snapshots.
    m = re.search(
        r"def _start_snapshot_refresh_loop.*?(?=\nasync def |\ndef |\Z)",
        src, re.DOTALL,
    )
    assert m, "could not isolate _start_snapshot_refresh_loop body"
    body = m.group(0)
    assert "refresh_now" in body, (
        "_start_snapshot_refresh_loop must call refresh_now() to actually "
        "re-materialize the snapshot tables."
    )
    assert "SNAPSHOT_REFRESH_INTERVAL_SEC" in body, (
        "the loop must gate on / sleep by SNAPSHOT_REFRESH_INTERVAL_SEC."
    )


def test_snapshot_loop_wired_in_main() -> None:
    src = (REPO / "apps/api/main.py").read_text()
    assert "_start_snapshot_refresh_loop" in src, (
        "main.py lifespan must start the snapshot refresh loop alongside "
        "_start_seat_refresh_loop(), or it never runs."
    )
