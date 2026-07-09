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

"""RED for independent-agent-audit blockers (2026-07-09):
  1. TUTORIAL.md's relative link `docs/DEPLOYMENT.md` resolves to
     `docs/docs/DEPLOYMENT.md` (404) since TUTORIAL itself is in docs/.
  2. `web-build` doesn't depend on `web-install` → fresh Cloud Shell
     tutorial's `make serve` step crashes with `vite: not found` when
     `apps/web/node_modules/` is absent.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_tutorial_deployment_link_is_relative_to_docs() -> None:
    """`docs/TUTORIAL.md` is inside `docs/`, so a link that says
    `docs/DEPLOYMENT.md` resolves to `docs/docs/DEPLOYMENT.md` (404).
    Must be `./DEPLOYMENT.md` or `DEPLOYMENT.md`."""
    for name in ("docs/TUTORIAL.md", "docs/TUTORIAL.zh-CN.md"):
        src = (REPO / name).read_text()
        # Reject any link body that starts with `docs/` (would double-nest)
        bad = re.findall(r"\]\(docs/[^)]+\)", src)
        assert not bad, (
            f"{name} has links that start with `docs/` — will 404 since the "
            f"file itself lives in docs/. Offending: {bad}\n"
            f"Fix: change to `./FILE.md` or just `FILE.md`."
        )


def test_makefile_web_build_depends_on_web_install() -> None:
    """Fresh clones (Cloud Shell tutorial, first-time contributors) have
    no `apps/web/node_modules/`. `web-build` runs `npm run build` which
    invokes `vite` — absent without a prior install → `vite: not found`.
    Make `web-install` a prereq so `make serve` (which depends on
    web-build) self-heals."""
    src = (REPO / "Makefile").read_text()
    # Find the web-build target line and check its prereqs.
    m = re.search(r"^web-build:([^\n]*)$", src, re.MULTILINE)
    assert m, "web-build target not found in Makefile"
    prereqs = m.group(1).strip()
    assert "web-install" in prereqs, (
        f"web-build has no `web-install` prereq (current: `web-build:{prereqs}`). "
        f"On a fresh clone `make serve` crashes with `vite: not found` because "
        f"node_modules doesn't exist. Fix: `web-build: web-install`."
    )


def test_makefile_phony_covers_every_target() -> None:
    """Every non-file-producing target MUST be in .PHONY, otherwise a
    file named after the target on disk would shadow it."""
    src = (REPO / "Makefile").read_text()
    m = re.search(r"^\.PHONY:\s*((?:[^\\\n]|\\\s*\n)+)", src, re.MULTILINE)
    assert m, ".PHONY declaration missing from Makefile"
    phony_body = re.sub(r"\\", " ", m.group(1))
    phony = set(phony_body.split())
    actual = set(re.findall(r"^([a-z][a-z0-9_-]+):", src, re.MULTILINE))
    missing = actual - phony
    assert not missing, (
        f"Makefile targets absent from .PHONY: {sorted(missing)}. "
        f"Add them so a directory/file with the same name won't shadow the target."
    )


def test_repo_has_no_broken_markdown_links() -> None:
    """Every relative markdown link `](path)` must resolve to an existing
    file. Catches typos like double-nesting (`docs/docs/X.md`) and stale
    references to removed dirs."""
    broken: list[str] = []
    for md in REPO.glob("**/*.md"):
        if "node_modules" in str(md) or ".venv" in str(md):
            continue
        text = md.read_text()
        for m in re.finditer(r"\]\(([^)]+)\)", text):
            target = m.group(1).split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if (md.parent / target).resolve().exists():
                continue
            broken.append(f"{md.relative_to(REPO)}: [{target}]")
    assert not broken, (
        f"{len(broken)} broken markdown link(s):\n"
        + "\n".join(f"  {b}" for b in broken)
    )
