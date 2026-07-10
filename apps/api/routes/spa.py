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

"""Single-page-app fallback routes.

  GET /            React index (served from ../web/dist)
  GET /{path}      SPA fallback — returns index.html for unknown client-side routes

Wired LAST in main.py because `/{path:path}` is a catch-all that would
otherwise shadow every other route.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# Same computation as apps/api/main.py — kept local so this module has no
# import back-edge into main. If the on-disk layout changes, update both.
WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

# Entry HTML must NEVER be cached — it references content-hashed chunk
# filenames that a subsequent build will invalidate. Cached HTML pointing
# at deleted hashes = white-screen "Failed to fetch dynamically imported
# module" on the next release. Real asset files under /assets/ are
# themselves content-hashed and safe to cache (browser default is fine;
# StaticFiles mount in main.py handles those).
_NO_CACHE_HTML = {"Cache-Control": "no-store"}


@router.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIST / "index.html", headers=_NO_CACHE_HTML)


@router.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/") or path.startswith("assets/"):
        raise HTTPException(status_code=404)
    target = WEB_DIST / path
    if target.is_file():
        # A real static file — favicon, robots.txt, etc. Content-hashed
        # or stable enough that default caching is OK.
        return FileResponse(target)
    # Client-side route (React Router path) — fall through to the SPA
    # entry HTML. Same no-cache rule as index() above.
    return FileResponse(WEB_DIST / "index.html", headers=_NO_CACHE_HTML)
