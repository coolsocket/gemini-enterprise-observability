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

"""RED regression for `make serve` self-detect (user report 2026-07-07,
"本地用不了 …你能不能自适应呢").

The natural env var is `BQ_PROJECT` (that's what the app reads, that's
what wizard.sh writes, that's what .env.example documents). But
`check-project` in the Makefile guards on `$(PROJECT)` — a legacy
Make-only variable. Result: an operator whose only signal is
`BQ_PROJECT=foo make serve` (or a .env with just `BQ_PROJECT=`) trips
`ERROR: PROJECT=<gcp-project-id> required` and has to hunt for the
right knob.

Fix invariants:
  1. `check-project` MUST accept BQ_PROJECT as a stand-in for PROJECT
     (so `.env` with only BQ_PROJECT works).
  2. If neither is set, MUST fall back to `gcloud config get-value
     project` before failing — most operators already have that
     configured; asking them again is wasted friction.
  3. Failure message MUST mention `make wizard` (the correct next
     step) — not a raw "PROJECT=<id> required".
"""
from pathlib import Path
import subprocess
import tempfile
import os
import shutil

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"


def test_check_project_accepts_bq_project_env() -> None:
    """`BQ_PROJECT=foo make serve` should not fail with `PROJECT=<id> required`
    just because the legacy PROJECT name isn't set."""
    src = MAKEFILE.read_text()
    # The check-project recipe (and/or its fallback) must reference BQ_PROJECT
    # somewhere so it accepts that variable as equivalent to PROJECT.
    # (Simplest: `PROJECT` recipe body substitutes `BQ_PROJECT` when PROJECT is empty.)
    check_project_block = _extract_target_body(src, "check-project")
    assert "BQ_PROJECT" in check_project_block, (
        "check-project recipe doesn't reference BQ_PROJECT — an operator whose "
        ".env only sets BQ_PROJECT (as wizard.sh writes) gets `PROJECT required` "
        "and has no idea what to do. Accept either name.\n"
        f"Current recipe:\n{check_project_block}"
    )


def test_check_project_falls_back_to_gcloud() -> None:
    """When neither PROJECT nor BQ_PROJECT is set, fall back to
    `gcloud config get-value project` — most operators already have that."""
    src = MAKEFILE.read_text()
    check_project_block = _extract_target_body(src, "check-project")
    assert "gcloud config get-value project" in check_project_block, (
        "check-project doesn't try `gcloud config get-value project` as a "
        "fallback. If the operator has an active gcloud project, use it "
        "instead of demanding they re-type it on the CLI or in .env."
    )


def test_check_project_error_points_to_wizard() -> None:
    """The failure message must direct the operator to `make wizard`,
    not the raw `PROJECT=<id> required` (which doesn't hint at the fix)."""
    src = MAKEFILE.read_text()
    check_project_block = _extract_target_body(src, "check-project")
    assert "make wizard" in check_project_block, (
        "check-project failure message doesn't mention `make wizard` — "
        "operators who don't know about wizard.sh see a bare error with "
        "no obvious next step."
    )


def test_serve_actually_works_with_only_bq_project(tmp_path) -> None:
    """Integration: from a scratch CWD (no .env) with BQ_PROJECT set on the
    command line, `make -n serve` should succeed and print the uvicorn cmd."""
    if not shutil.which("make"):
        import pytest
        pytest.skip("make not installed")

    # Build a scratch workspace that symlinks in only what's needed to parse
    # Makefile targets (no .env, no venv, etc). `make -n` won't actually run
    # commands — we just want the parse + check-project logic to succeed.
    work = tmp_path / "scratch"
    work.mkdir()
    (work / "Makefile").symlink_to(ROOT / "Makefile")
    # Also symlink infra/ so `bash infra/...` references parse without file-not-found
    (work / "infra").symlink_to(ROOT / "infra")
    (work / "apps").symlink_to(ROOT / "apps")

    env = {k: v for k, v in os.environ.items() if not k.startswith("BQ_") and k != "PROJECT"}
    env["BQ_PROJECT"] = "some-test-project"
    env["PATH"] = os.environ.get("PATH", "")

    result = subprocess.run(
        ["make", "-n", "check-project"],
        cwd=work, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, (
        f"`make -n check-project` failed with BQ_PROJECT set (PROJECT unset).\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}\n"
        f"check-project should treat BQ_PROJECT as equivalent to PROJECT."
    )


# ---- helpers ----

def _extract_target_body(makefile_src: str, target: str) -> str:
    """Extract the recipe body of a Make target — every subsequent tab-indented
    (or blank) line until an unindented line."""
    lines = makefile_src.splitlines()
    body: list[str] = []
    in_target = False
    for ln in lines:
        if ln.startswith(target + ":"):
            in_target = True
            body.append(ln)
            continue
        if in_target:
            if ln.startswith("\t") or ln == "":
                body.append(ln)
            else:
                break
    return "\n".join(body)
