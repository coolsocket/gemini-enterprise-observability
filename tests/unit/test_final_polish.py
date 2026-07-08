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

"""RED tests for the 3-item final-polish batch (2026-07-08):

  A) `make hotfix` — one command to apply latest view SQL + refresh
     snapshots. Chains `deploy-views` + POST /api/refresh. Does NOT
     auto-run `git pull` (see earlier feedback about not auto-pulling
     from `make resume`).
  B) Frontend renders `identity_kind` badge on user picker rows.
     Backend already returns the field (commit 5846b6b) — this closes
     the loop so the user actually sees Google-email vs OIDC vs SA.
  C) First-visit default origin filter = null (全部), not HUMAN.
     Old default was OK for old tenants with lots of sim/SA noise, but
     for new deployments (esp. OIDC-only) it hides everything unclassified.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"
USER_DEEP_DIVE_TSX = REPO / "apps/web/src/pages/UserDeepDive.tsx"
ORIGIN_TSX = REPO / "apps/web/src/origin.tsx"


# ============================================================
# A) make hotfix
# ============================================================

def test_makefile_has_hotfix_target() -> None:
    """`make hotfix` should exist as a one-command post-pull recipe."""
    text = MAKEFILE.read_text()
    has_target = any(
        ln.startswith("hotfix:") or ln.startswith("hotfix ")
        for ln in text.splitlines()
    )
    assert has_target, (
        "Makefile has no `hotfix:` target. Operators post-`git pull` need "
        "one command to (a) apply latest view SQL and (b) trigger snapshot "
        "refresh — else they see stale data and don't know why."
    )


def test_hotfix_target_applies_views_and_refreshes() -> None:
    """The recipe (target line + body) must reference `views` (apply new
    SQL) AND /api/refresh (materialize snapshots with new definitions)."""
    text = MAKEFILE.read_text()
    lines = text.splitlines()
    # Include the target line itself (for prerequisites like `hotfix: ... views`)
    # plus the body (indented lines) — check both.
    block = []
    in_target = False
    for ln in lines:
        if ln.startswith("hotfix:") or ln.startswith("hotfix "):
            in_target = True
            block.append(ln)
            continue
        if in_target:
            if ln.startswith("\t") or ln == "":
                block.append(ln)
            else:
                break
    block_str = "\n".join(block)
    assert "views" in block_str or "apply_views" in block_str, (
        "hotfix target doesn't invoke view application. Should either "
        "depend on `views` prereq or run `apply_views.py` in the recipe."
    )
    assert "/api/refresh" in block_str or "refresh" in block_str.lower(), (
        "hotfix target doesn't trigger snapshot refresh. Views without "
        "a snapshot refresh still leave dashboards showing old data."
    )


def test_hotfix_does_not_auto_git_pull() -> None:
    """Per earlier operator feedback (`make resume` auto-pull removed):
    hotfix MUST NOT `git pull` on its own. Operator pulls themselves."""
    text = MAKEFILE.read_text()
    lines = text.splitlines()
    body_lines = []
    in_target = False
    for ln in lines:
        if ln.startswith("hotfix:") or ln.startswith("hotfix "):
            in_target = True
            continue
        if in_target:
            if ln.startswith("\t") or ln == "":
                body_lines.append(ln)
            else:
                break
    body_str = "\n".join(body_lines)
    assert "git pull" not in body_str, (
        "hotfix recipe auto-runs `git pull`. Operator explicitly asked "
        "not to auto-pull (see history around `make resume`). Remove it — "
        "operator pulls, then runs hotfix."
    )


# ============================================================
# B) identity_kind badge in frontend
# ============================================================

def test_user_deep_dive_renders_identity_kind_badge() -> None:
    """Backend (/api/users) returns identity_kind — frontend must
    actually render it so users can see the classification."""
    src = USER_DEEP_DIVE_TSX.read_text()
    assert "identity_kind" in src, (
        "UserDeepDive.tsx doesn't reference `identity_kind` — the backend "
        "field is silently dropped. Add a badge/chip near each user row "
        "showing the kind (Google / OIDC / SA / simulated / etc)."
    )


def test_identity_kind_type_in_api() -> None:
    """`UserListEntry` type must declare `identity_kind` so TypeScript
    doesn't strip the field at compile time."""
    api_ts = REPO / "apps/web/src/api.ts"
    src = api_ts.read_text()
    # Find UserListEntry type
    m = re.search(r"(?:type|interface)\s+UserListEntry\s*=?\s*\{[^}]+\}", src, re.DOTALL)
    assert m, "UserListEntry type not found in api.ts"
    body = m.group(0)
    assert "identity_kind" in body, (
        "UserListEntry type missing `identity_kind: string` field. "
        "Backend sends it (see /api/users response), but TS strips it "
        "silently — frontend components can't render what they can't see."
    )


# ============================================================
# C) default origin filter = null on first visit
# ============================================================

def test_default_origin_is_null_on_first_visit() -> None:
    """New tenants (esp. OIDC-only) can have zero users classified as
    HUMAN in the OLD dashboards until view SQL is updated. Default to
    'all' so 'looks empty' means empty, not filtered-empty."""
    src = ORIGIN_TSX.read_text()
    # Look for the initial useState / getter logic. The old code was:
    #   if (saved === "HUMAN" || ...) return saved;
    #   if (saved === "ALL") return null;
    #   return "HUMAN";   // ← this default is what we're changing
    # New behavior should return null when no saved preference (first visit).
    # Cheap heuristic: last uncondional `return "HUMAN"` in the state
    # initializer should be `return null;` or similar.
    initializer = re.search(
        r"useState<Origin>\(\(\)\s*=>\s*\{(.*?)\}\)", src, re.DOTALL,
    )
    assert initializer, "could not parse origin useState initializer"
    body = initializer.group(1)
    # The fallback branch (no saved value) must return null.
    # Find every `return ...;` in this initializer
    returns = re.findall(r"return\s+([^;]+);", body)
    # The LAST return is the fallback. It MUST be `null` (or an
    # expression clearly evaluating to null on first visit).
    assert returns, "no `return` statements in initializer — unexpected shape"
    fallback = returns[-1].strip()
    assert fallback == "null", (
        f"origin useState initializer's fallback returns `{fallback}`, "
        f"not `null`. Change so that first-visit users see 全部 "
        f"(unfiltered) — HUMAN-only filter hides UNKNOWN users on new "
        f"OIDC tenants until they know to click 全部."
    )
