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
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api.routes import meta, observability, quota, refresh, spa

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ge-obs")

# Additional origins that state-mutating requests may originate from.
# Comma-separated, e.g. "https://ge.internal,https://dash.corp".
# Same-origin requests (Origin/Referer host == request Host) are always
# allowed — this env var is only for the extra cases (CDN in front, dev
# tunnels, admin scripts running from a known host).
_CSRF_EXTRA_ORIGINS = {
    o.strip().rstrip("/")
    for o in os.environ.get("CSRF_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
}


# `@router.on_event` doesn't fire for included routers, and
# `app.add_event_handler(...)` AttributeErrors on some FastAPI/starlette
# combos in the wild (reported 2026-07-07 on responsive-lens-421108).
# The lifespan context manager is the officially supported hook that
# works across every version — kick the seat auto-refresh here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh._start_seat_refresh_loop()
    await refresh._start_snapshot_refresh_loop()
    yield


app = FastAPI(title="GE Observability", version="2.0", lifespan=lifespan)


@app.middleware("http")
async def csrf_same_origin_guard(request: Request, call_next):
    """Reject state-mutating requests whose Origin (or Referer, when Origin
    is absent) doesn't match the request Host. This defeats the passive
    CSRF attack where a foreign page silently POSTs to /api/quota/tier
    using the admin's browser cookies.

    Allow the request through when:
      - method is safe (GET / HEAD / OPTIONS)
      - Origin/Referer host matches Host (same-origin — the SPA case)
      - Origin matches CSRF_ALLOWED_ORIGINS env allow-list (CDN / tunnel)
      - Origin is absent AND Referer is absent AND path is /api/refresh
        (server-to-server internal cron; matches by path prefix, not
        forgeable from a browser). Same for /api/refresh/seats.

    Denials return 403 with a short body so the frontend can diagnose.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)

    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    def _host_of(url):  # type: (Optional[str]) -> Optional[str]
        if not url:
            return None
        try:
            return urlparse(url).netloc
        except Exception:
            return None

    origin_host = _host_of(origin)
    referer_host = _host_of(referer)
    # Consider it "same origin" if either the Origin or the Referer host
    # matches the request Host. Browsers always send at least one for
    # cross-origin state-changing requests.
    same_origin = (origin_host == host) or (referer_host == host)
    in_allow_list = (
        origin and origin.rstrip("/") in _CSRF_EXTRA_ORIGINS
    )
    # Server-to-server allow: no Origin AND no Referer AND path is
    # explicitly server-triggered. Browsers always include one when
    # making a cross-origin POST from a page, so this can't be spoofed
    # via a foreign site.
    server_to_server = (
        origin is None and referer is None
        and request.url.path in ("/api/refresh", "/api/refresh/seats")
    )
    if same_origin or in_allow_list or server_to_server:
        return await call_next(request)

    log.warning("csrf reject: method=%s path=%s host=%s origin=%s referer=%s",
                request.method, request.url.path, host, origin, referer)
    return JSONResponse(
        status_code=403,
        content={"detail": "cross-origin request blocked (CSRF); set "
                            "CSRF_ALLOWED_ORIGINS to include your caller"},
    )


app.include_router(meta.router)
app.include_router(observability.router)
app.include_router(quota.router)
app.include_router(refresh.router)

# Static + SPA LAST — /{path:path} is a catch-all that would shadow /api/*.
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="spa-assets")
app.include_router(spa.router)
