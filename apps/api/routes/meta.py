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

from apps.api.shared.infrastructure.bq_client import bq as _bq, PROJECT, DATASET
from apps.api.shared.common import VIEWS

router = APIRouter()


@router.get("/api/engines")
def list_engines() -> dict[str, Any]:
    """List all known engines (from engine_metadata table) for the engine selector."""
    rows = list(_bq.query(
        f"SELECT engine_id, display_name, solution_type FROM `{PROJECT}.{DATASET}.engine_metadata` ORDER BY display_name"
    ).result())
    return {"engines": [{"id": r.engine_id, "name": r.display_name, "type": r.solution_type} for r in rows]}


@router.get("/api/resources/alive")
def alive_resources() -> dict[str, Any]:
    rows = list(_bq.query(
        f"SELECT resource_type, COUNT(*) c FROM `{PROJECT}.{DATASET}.resources_alive` GROUP BY resource_type"
    ).result())
    return {r.resource_type: r.c for r in rows}


@router.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "project": PROJECT, "dataset": DATASET}


@router.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "dataset": DATASET,
        "sink_name": "ge-observability-unified",
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }


@router.get("/api/views")
def list_views() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "dataset": DATASET,
        "views": [{"name": n, **v} for n, v in VIEWS.items()],
    }
