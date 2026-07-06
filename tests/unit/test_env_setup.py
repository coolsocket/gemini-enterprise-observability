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

"""Regression tests for the one-command setup path.

Users kept hitting env-var / dep / version issues:
  - Wrong Python (missing PEP 604 support)
  - Missing BQ_PROJECT / BQ_DATASET at runtime
  - Node too old for Vite 5
  - Cryptic errors from partial installs

Fixes shipped: `make doctor`, `.env` support (auto-include + export),
improved `make install`, `.env.example` template. These tests lock the
setup pattern in so nobody accidentally removes it.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
ENV_EXAMPLE = ROOT / ".env.example"
GITIGNORE = ROOT / ".gitignore"
DOCTOR = ROOT / "infra/contexts/deploy/application/doctor.sh"


@pytest.fixture(scope="module")
def makefile() -> str:
    return MAKEFILE.read_text()


def test_env_example_exists_with_required_keys() -> None:
    """Users copy .env.example → .env once, then never pass BQ_PROJECT= on
    the CLI again. Missing template means new users have nothing to start from."""
    assert ENV_EXAMPLE.exists(), (
        ".env.example missing — new users have no template to `cp .env.example .env` from."
    )
    text = ENV_EXAMPLE.read_text()
    for key in ("BQ_PROJECT", "BQ_DATASET", "REGION", "BQ_LOCATION", "SIM_PREFIX", "PORT"):
        assert f"{key}=" in text, f".env.example missing required key: {key}"


def test_gitignore_excludes_env() -> None:
    """.env holds the operator's real project id and possibly a path to a
    service-account key — must not be committed."""
    text = GITIGNORE.read_text()
    # Match `.env` on its own line (not `.env.example` or `.env.local`)
    lines = [ln.strip() for ln in text.splitlines()]
    assert ".env" in lines, ".gitignore does not ignore .env (regex must match line, not substring)"


def test_makefile_auto_includes_env(makefile: str) -> None:
    """Makefile must `-include .env` (the `-` prefix means non-fatal if missing)
    AND `export` so values reach subprocess environments (uvicorn / terraform)."""
    assert "-include .env" in makefile, (
        "Makefile missing `-include .env` — .env values won't be picked up by "
        "Make. Users would still need to prefix `BQ_PROJECT=... make serve`."
    )
    # export directive on its own line (bare `export` exports every Make var)
    has_bare_export = any(
        ln.strip() == "export" for ln in makefile.splitlines()
    )
    assert has_bare_export, (
        "Makefile missing bare `export` directive. Without it, Make variables "
        "loaded from .env stay in Make's namespace and never reach subprocesses "
        "like uvicorn / terraform / gcloud."
    )


def test_doctor_target_exists(makefile: str) -> None:
    """`make doctor` is the first thing users should run when something feels
    wrong. Regression-guard the target so nobody removes it."""
    # Match `doctor:` as a target line (colon-terminated)
    has_target = any(
        ln.startswith("doctor:") or ln.startswith("doctor ")
        for ln in makefile.splitlines()
    )
    assert has_target, "Makefile missing `doctor` target — env health check is critical UX."
    assert DOCTOR.exists(), "infra/contexts/deploy/application/doctor.sh missing — Makefile target has nothing to run."
    # Should be executable
    assert DOCTOR.stat().st_mode & 0o111, "doctor.sh not executable — chmod +x it."


def test_install_target_bootstraps_env(makefile: str) -> None:
    """`make install` should create .env from .env.example when missing so
    a first-time user has one less step to remember."""
    # Look for `.env.example` reference in the install recipe body
    lines = makefile.splitlines()
    # Find install: line, then next unindented line
    in_install = False
    install_body = []
    for ln in lines:
        if ln.startswith("install:"):
            in_install = True
            continue
        if in_install:
            if ln.startswith("\t") or ln == "":
                install_body.append(ln)
            else:
                break
    body_str = "\n".join(install_body)
    assert ".env.example" in body_str, (
        "`make install` recipe doesn't reference .env.example — users have to "
        "remember to `cp .env.example .env` manually. Add: "
        "`if [ ! -f .env ]; then cp .env.example .env; fi` to the install recipe."
    )
