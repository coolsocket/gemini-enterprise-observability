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

"""RED tests for two Makefile / packaging gaps.

Reported failure (user, 2026-07-06):

  $ make serve PROJECT=my-project
  ...
  RuntimeError: BQ_PROJECT (or GOOGLE_CLOUD_PROJECT) env var required
  make: *** [serve] Error 1

Root cause: `make serve` (and `make api-run`) launched uvicorn WITHOUT
threading PROJECT / DATASET into the subprocess environment as BQ_PROJECT /
BQ_DATASET. main.py reads those env vars at import time and hard-fails
when they're missing. So `PROJECT=…` on the make command line went into
Make's namespace but never reached the API.

Second gap (previous audit): package.json has no `engines` field, so a
user on Node 14 / 16 / 21 gets confusing esbuild errors instead of an
explicit "Node 18+ required" message.
"""
from pathlib import Path
import json
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
PACKAGE_JSON = ROOT / "apps/web/package.json"


@pytest.fixture(scope="module")
def makefile() -> str:
    return MAKEFILE.read_text()


@pytest.fixture(scope="module")
def package_json() -> dict:
    return json.loads(PACKAGE_JSON.read_text())


def _target_body(makefile: str, target: str) -> str:
    """Return the recipe lines for a Make target (until the next unindented line)."""
    # Match `target:` optionally followed by deps + newline, then indented recipe lines
    pattern = re.compile(
        rf"^{re.escape(target)}:.*?\n((?:\t.*\n)+)",
        re.MULTILINE,
    )
    m = pattern.search(makefile)
    return m.group(1) if m else ""


# -------------------------------------------------------------------
# Bug 1: `make serve` / `make api-run` don't pass BQ_PROJECT to uvicorn
# -------------------------------------------------------------------
def test_serve_target_passes_bq_project(makefile: str) -> None:
    """`make serve PROJECT=my-project` must reach uvicorn with
    BQ_PROJECT=my-project set, otherwise main.py's import-time env check
    raises RuntimeError before the server can start."""
    body = _target_body(makefile, "serve")
    assert body, "Couldn't find `serve` target in Makefile"
    assert "BQ_PROJECT" in body, (
        "`serve` target invokes uvicorn but does NOT thread BQ_PROJECT into "
        "the subprocess env. Fix: prefix the uvicorn line with "
        "`BQ_PROJECT=$(PROJECT) BQ_DATASET=$(DATASET)` (and typically "
        "SIM_PREFIX too if you rely on demo-actor rewriting).\n"
        f"Current recipe body:\n{body}"
    )


def test_api_run_target_passes_bq_project(makefile: str) -> None:
    """Same fix required for the hot-reload dev target `make api-run`."""
    body = _target_body(makefile, "api-run")
    assert body, "Couldn't find `api-run` target in Makefile"
    assert "BQ_PROJECT" in body, (
        "`api-run` target invokes uvicorn but does NOT thread BQ_PROJECT into "
        "the subprocess env. Same fix as `serve`."
    )


# -------------------------------------------------------------------
# Bug 2: package.json lacks `engines` — bad Node version fails cryptically
# -------------------------------------------------------------------
def test_package_json_declares_node_engine(package_json: dict) -> None:
    """Vite 5 needs Node 18+ / 20+ / 22+. Without an `engines.node`
    constraint, users on Node 14/16/21 hit esbuild syntax errors that
    look like bugs in this repo. Declaring the constraint lets npm warn
    (or `npm install --engine-strict` refuse) up-front."""
    engines = package_json.get("engines", {})
    node_constraint = engines.get("node")
    assert node_constraint, (
        "apps/web/package.json has no `engines.node` field. "
        "Vite 5 requires Node 18+; users on older Node get confusing "
        "esbuild errors that look like a repo bug. Add: "
        '`"engines": {"node": ">=18.0.0"}` to package.json.'
    )
    # Sanity: whatever they specified must at least allow Node 18
    # (crude check: literal "18" or higher appears somewhere in the string)
    assert re.search(r"1[89]|[2-9]\d", node_constraint), (
        f"engines.node = {node_constraint!r} — must allow at least Node 18 "
        "for Vite 5 compatibility."
    )
