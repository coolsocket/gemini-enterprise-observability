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

"""RED for the "stale index.html" bug (2026-07-10).

Symptom: after a `npm run build` + uvicorn restart, browsers that had
the previous session loaded fail dynamic-import with:
    Failed to fetch dynamically imported module:
      http://localhost:18003/assets/UserDeepDive-<oldhash>.js

Root cause: `apps/api/routes/spa.py::index` and `spa_fallback` return
`index.html` via `FileResponse` with default headers — the browser is
free to serve the previously-cached HTML on the next navigation, and
that HTML references chunk filenames whose content hashes no longer
exist on disk (Vite rewrote them at build time).

Vite's content-hashed chunks are safe to cache forever (they're
content-addressed). But the entry HTML MUST be no-cache so the browser
always sees the fresh manifest. The R2 test explicitly exempted SPA
paths from the Cache-Control policy — that was wrong.

Fix: both SPA routes must set `Cache-Control: no-store` on the
returned index.html. Real asset files (`/{path}` that maps to a real
file under dist/) can keep default caching since those ARE hashed.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def test_spa_index_route_sets_no_store() -> None:
    src = (REPO / "apps/api/routes/spa.py").read_text()
    m = re.search(r"def index\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)",
                  src, re.DOTALL)
    assert m, "spa.py::index not found"
    body = m.group(0)
    has_no_store = "no-store" in body or "no_store" in body or "_NO_CACHE" in body
    assert has_no_store, (
        "spa.py::index returns index.html without Cache-Control: no-store. "
        "After a rebuild, browsers with cached HTML get 404s on the old "
        "chunk hashes and fail to load. The entry HTML must be no-cache; "
        "chunk files are content-hashed and safe to cache."
    )


def test_spa_fallback_sets_no_store_on_index_html() -> None:
    src = (REPO / "apps/api/routes/spa.py").read_text()
    m = re.search(r"def spa_fallback\([^)]*\)[^:]*:.*?(?=\n@router|\ndef |\Z)",
                  src, re.DOTALL)
    assert m, "spa.py::spa_fallback not found"
    body = m.group(0)
    # When the path doesn't match a real file, this function returns
    # index.html and inherits the same stale-cache risk.
    has_no_store = "no-store" in body or "no_store" in body or "_NO_CACHE" in body
    assert has_no_store, (
        "spa.py::spa_fallback also returns index.html for unknown client-"
        "side routes. Same fix as index — set Cache-Control: no-store."
    )
