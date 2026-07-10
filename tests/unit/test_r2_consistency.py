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

"""RED for R2 (2026-07-10) — API consistency polish surfaced by the audit:

  R2a · /api/summary has a well-defined 16-field shape but the route is
        typed `dict[str, Any]` and the frontend uses
        `Summary & Record<string, any>` as an escape hatch. Define a
        Pydantic model so both sides share ONE source of truth.

  R2b · Path naming: `/api/persona/licensed-users` is the only kebab-case
        path in the codebase; everything else is snake_case. Rename to
        `/api/persona/licensed_users` (or keep kebab but document why).
        Picking snake_case since that's the existing majority.

  R2c · Every read endpoint should set `Cache-Control: no-store` — some
        do (view, user, quota/overview) but many don't (agents, users,
        summary, meta, engines, healthz, quota/config, refresh/status,
        persona/licensed-users). Consistent policy: dashboards want
        no-store for user-specific + fresh-every-tick data.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


# --------- R2a · Summary Pydantic model ---------

def test_summary_response_has_pydantic_model() -> None:
    """The /api/summary endpoint should return a typed Pydantic model,
    not `dict[str, Any]`. This forces backend + frontend to agree on
    the field set (currently 16 fields)."""
    src = (REPO / "apps/api/routes/observability.py").read_text()
    # Find the summary function signature line
    m = re.search(r"def summary\([^)]*\)([^:]*):", src)
    assert m, "summary function not found"
    return_ann = m.group(1)
    assert "dict[str, Any]" not in return_ann, (
        "/api/summary is still typed as dict[str, Any]. Define a Pydantic "
        "BaseModel with the 16 fields and use it as the return annotation."
    )
    # Model should exist somewhere reachable — either in this file or
    # a domain module. Grep for a class Summary(BaseModel)-ish shape.
    has_model_here = re.search(r"class\s+\w*Summary\w*\s*\([^)]*BaseModel", src) is not None
    domain = (REPO / "apps/api/contexts/observability/domain/query_builder.py").read_text()
    has_model_domain = re.search(r"class\s+\w*Summary\w*\s*\([^)]*BaseModel", domain) is not None
    assert has_model_here or has_model_domain, (
        "No Pydantic BaseModel matching *Summary* found. Add one to "
        "the observability domain and import it in the route."
    )


def test_frontend_summary_type_is_not_any_escape() -> None:
    """apps/web/src/api.ts should NOT use `Summary & Record<string, any>`
    for the summary response — that's a bypass. Define the fields."""
    api = (REPO / "apps/web/src/api.ts").read_text()
    # Look for the summary helper's return type
    m = re.search(r"summary\s*:.*?get<([^>]+)>", api, re.DOTALL)
    assert m, "summary helper in api.ts not found"
    ret = m.group(1)
    assert "Record<string, any>" not in ret, (
        "apps/web/src/api.ts still types summary as `Summary & "
        "Record<string, any>` — remove the Record escape once the "
        "Summary type covers all 16 fields."
    )


# --------- R2b · Path naming ---------

def test_no_kebab_case_api_paths() -> None:
    """All /api/* paths should use snake_case. `licensed-users` was the
    only kebab; standardize."""
    py_files = list((REPO / "apps/api/routes").glob("*.py"))
    offenders: list[str] = []
    for py in py_files:
        for line_no, line in enumerate(py.read_text().splitlines(), start=1):
            m = re.search(r'@router\.\w+\(\s*[\'"]([^\'"]+)[\'"]', line)
            if not m:
                continue
            path = m.group(1)
            # Split into segments; skip the leading '/' and any {var}
            for seg in path.split("/"):
                if seg.startswith("{") or seg == "":
                    continue
                # Kebab = has a '-'. Allowed only in a comment above? No —
                # we're inspecting the actual route path.
                if "-" in seg:
                    offenders.append(f"{py.name}:{line_no}: {path} (segment: {seg})")
    assert not offenders, (
        "Found kebab-case API paths — standardize to snake_case:\n" +
        "\n".join(offenders)
    )


# --------- R2c · Cache-Control on read endpoints ---------

# Endpoints that are truly public/static and don't need no-store.
# healthz is a liveness ping; SPA paths serve static HTML/JS via
# FileResponse (browser + Vite handle caching) — dashboard freshness
# rules only apply to /api/* data endpoints.
_CACHE_EXEMPT_PATHS = {"/api/healthz", "/", "/{path:path}"}


def test_all_read_endpoints_set_cache_control_no_store() -> None:
    """Every GET route (except healthz) should return with
    Cache-Control: no-store. Dashboards need fresh data every tick;
    silent caching by intermediate proxies would show stale metrics."""
    route_files = list((REPO / "apps/api/routes").glob("*.py"))
    missing: list[str] = []
    for py in route_files:
        src = py.read_text()
        # Find every @router.get(...) block up to the next @router or eof
        for m in re.finditer(
            r'@router\.get\(\s*[\'"]([^\'"]+)[\'"][^)]*\)\s*(?:async\s+)?def\s+(\w+)'
            r'.*?(?=\n@router\.\w+\(|\ndef\s|\Z)',
            src, re.DOTALL,
        ):
            path, fn = m.group(1), m.group(2)
            if path in _CACHE_EXEMPT_PATHS:
                continue
            body = m.group(0)
            # Accept literal "no-store" / "no_store" in body OR the
            # `_NO_CACHE` module constant which is `{"Cache-Control":
            # "no-store"}` centralized at the top of each route file.
            has_no_store = (
                "no-store" in body
                or "no_store" in body
                or "_NO_CACHE" in body
            )
            if not has_no_store:
                missing.append(f"{py.name}::{fn} ({path})")
    assert not missing, (
        "GET endpoints missing `Cache-Control: no-store`:\n" +
        "\n".join(missing) +
        "\nReturn a `JSONResponse(..., headers={\"Cache-Control\": "
        "\"no-store\"})` OR add via `Response` param."
    )
