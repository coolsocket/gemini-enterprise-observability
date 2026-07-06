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


@router.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIST / "index.html")


@router.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/") or path.startswith("assets/"):
        raise HTTPException(status_code=404)
    target = WEB_DIST / path
    if target.is_file():
        return FileResponse(target)
    return FileResponse(WEB_DIST / "index.html")
