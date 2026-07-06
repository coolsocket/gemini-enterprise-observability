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

"""Per-context FastAPI routers.

Each module here is a self-contained slice: it exposes `router =
APIRouter()` plus the endpoints for one bounded slice (meta / observability
/ quota / refresh / spa). `apps/api/main.py` composes them via
`app.include_router(...)`.

Rule: no route module imports from another route module. If two routes
need the same helper, hoist it into `apps/api/shared/common.py`.
"""
