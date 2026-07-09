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

"""RED for the Cloud Shell interactive tutorial (2026-07-09).

Delivery pattern is the vigenair / BulkAiBCD model: README's "Open in
Cloud Shell" button clones the repo into the user's Cloud Shell (their
gcloud auth already there) AND opens an interactive walkthrough panel
that steps them through project selection → API enable → wizard →
deploy → verify.

The old target `docs/DEPLOYMENT.md` was a plain reference doc — Cloud
Shell just rendered the markdown, no step-by-step panel. Proper
tutorial files use walkthrough-* HTML directives that Cloud Shell
recognises to render as interactive UI (project picker widget,
enable-APIs button, spotlight, etc).
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_tutorial_files_exist() -> None:
    for name in ("docs/TUTORIAL.md", "docs/TUTORIAL.zh-CN.md"):
        assert (REPO / name).exists(), (
            f"{name} missing — the Cloud Shell button should point at a proper "
            "tutorial file (walkthrough format), not the DEPLOYMENT reference."
        )


def test_tutorial_uses_walkthrough_project_setup() -> None:
    """Tutorial MUST use <walkthrough-project-setup> — that's what renders
    the interactive project picker widget. Without it, users have to
    manually type their project ID somewhere, defeating the tutorial UX."""
    for name in ("docs/TUTORIAL.md", "docs/TUTORIAL.zh-CN.md"):
        path = REPO / name
        if not path.exists():
            continue  # other test flags absence
        src = path.read_text()
        assert "<walkthrough-project-setup" in src, (
            f"{name} doesn't use <walkthrough-project-setup billing=\"true\"> — "
            "the project picker widget. Without it, this is just a rendered "
            "reference doc, not a Cloud Shell tutorial."
        )


def test_tutorial_uses_walkthrough_enable_apis() -> None:
    """<walkthrough-enable-apis apis="..."> renders as a click-to-enable
    button. Otherwise operators paste 6+ `gcloud services enable` lines."""
    for name in ("docs/TUTORIAL.md", "docs/TUTORIAL.zh-CN.md"):
        path = REPO / name
        if not path.exists():
            continue
        src = path.read_text()
        assert re.search(r"<walkthrough-enable-apis[^>]*apis=", src), (
            f"{name} has no <walkthrough-enable-apis apis=\"...\"> tag. Add "
            "one covering: bigquery, logging, run, cloudbuild, artifactregistry, "
            "discoveryengine, iam, iamcredentials, bigquerydatatransfer."
        )


def test_tutorial_covers_key_deploy_steps() -> None:
    """The tutorial MUST at minimum reference the load-bearing make
    targets in the operator sequence — otherwise it's incomplete."""
    required_targets = ["make wizard", "make deploy-infra",
                        "make deploy-views", "make backfill", "make serve"]
    for name in ("docs/TUTORIAL.md", "docs/TUTORIAL.zh-CN.md"):
        path = REPO / name
        if not path.exists():
            continue
        src = path.read_text()
        missing = [t for t in required_targets if t not in src]
        assert not missing, (
            f"{name} doesn't mention these make targets: {missing}. "
            "The operator needs the complete deploy path in-tutorial, not "
            "buried in a separate reference doc."
        )


def test_readme_button_points_at_tutorial() -> None:
    """Both README variants' Cloud Shell buttons must point at TUTORIAL,
    not the old DEPLOYMENT.md reference doc."""
    for readme in ("README.md", "README.zh-CN.md"):
        src = (REPO / readme).read_text()
        # Find the cloudshell button line
        m = re.search(r"cloudshell_tutorial=([^&]+)", src)
        assert m, f"{readme} missing Open-in-Cloud-Shell button with cloudshell_tutorial"
        target = m.group(1)
        assert "TUTORIAL" in target, (
            f"{readme} button's cloudshell_tutorial points at `{target}`. "
            f"Should be `docs%2FTUTORIAL.md` (or the zh-CN variant) — "
            f"a proper walkthrough file, not the plain reference doc."
        )
