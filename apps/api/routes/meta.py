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

"""Meta / discovery endpoints.

  GET /api/healthz         liveness
  GET /api/meta            project + dataset + view labels
  GET /api/views           list of views (alias of meta.views)
  GET /api/engines         engine catalogue for the selector
  GET /api/resources/alive live resource counts by type
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.api.shared.infrastructure.bq_client import bq as _bq, PROJECT, DATASET
from apps.api.shared.common import VIEWS

router = APIRouter()

# Dashboards refresh on every navigation — intermediate caches / bfcache
# would show stale counts. Applied to every read endpoint except /healthz
# (which really is a stateless ping and safe to cache).
_NO_CACHE = {"Cache-Control": "no-store"}


@router.get("/api/engines")
def list_engines() -> JSONResponse:
    """List all known engines (from engine_metadata table) for the engine selector."""
    rows = list(_bq.query(
        f"SELECT engine_id, display_name, solution_type FROM `{PROJECT}.{DATASET}.engine_metadata` ORDER BY display_name"
    ).result())
    return JSONResponse(
        content={"engines": [{"id": r.engine_id, "name": r.display_name, "type": r.solution_type} for r in rows]},
        headers=_NO_CACHE,
    )


@router.get("/api/resources/alive")
def alive_resources() -> JSONResponse:
    rows = list(_bq.query(
        f"SELECT resource_type, COUNT(*) c FROM `{PROJECT}.{DATASET}.resources_alive` GROUP BY resource_type"
    ).result())
    return JSONResponse(content={r.resource_type: r.c for r in rows}, headers=_NO_CACHE)


@router.get("/api/healthz")
def healthz() -> dict[str, str]:
    # Intentionally NO no-store — healthz is a plain liveness ping,
    # intermediaries may cache the "ok" for a second without harm.
    return {"status": "ok", "project": PROJECT, "dataset": DATASET}


@router.get("/api/meta")
def meta() -> JSONResponse:
    return JSONResponse(content={
        "project": PROJECT,
        "dataset": DATASET,
        "sink_name": "ge-observability-unified",
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }, headers=_NO_CACHE)


@router.get("/api/views")
def list_views() -> JSONResponse:
    return JSONResponse(content={
        "project": PROJECT,
        "dataset": DATASET,
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }, headers=_NO_CACHE)
