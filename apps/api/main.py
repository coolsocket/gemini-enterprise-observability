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

"""GE Observability — FastAPI app composition.

Routes live in apps/api/routes/* and are wired here via `include_router`.
The SPA catch-all MUST be last so it doesn't shadow /api/* endpoints.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.api.routes import meta, observability, quota, refresh, spa

logging.basicConfig(level=logging.INFO)


# `@router.on_event` doesn't fire for included routers, and
# `app.add_event_handler(...)` AttributeErrors on some FastAPI/starlette
# combos in the wild (reported 2026-07-07 on responsive-lens-421108).
# The lifespan context manager is the officially supported hook that
# works across every version — kick the seat auto-refresh here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh._start_seat_refresh_loop()
    yield


app = FastAPI(title="GE Observability", version="2.0", lifespan=lifespan)

app.include_router(meta.router)
app.include_router(observability.router)
app.include_router(quota.router)
app.include_router(refresh.router)

# Static + SPA LAST — /{path:path} is a catch-all that would shadow /api/*.
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="spa-assets")
app.include_router(spa.router)
