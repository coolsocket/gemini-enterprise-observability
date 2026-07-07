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

"""RED test for the `AttributeError: 'FastAPI' object has no attribute
'add_event_handler'` reported on responsive-lens-421108 (2026-07-07).

Root cause: main.py used `app.add_event_handler("startup", …)` to wire
the seat-refresh loop after Phase 2. That method exists on Starlette
(and thus on FastAPI) on most versions, but was moved/removed on some
version combinations users hit in the wild. FastAPI's officially
recommended API is the lifespan context manager, which works on every
supported version.

Fix: use `lifespan=…` on the FastAPI constructor + `@asynccontextmanager`
wrapper. That subsumes `on_event("startup")` too.
"""
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[2] / "apps/api/main.py"


def test_main_does_not_use_add_event_handler() -> None:
    """The `add_event_handler` shape has been reported to AttributeError on
    at least one FastAPI/starlette version combo. Prefer lifespan."""
    src = MAIN_PY.read_text()
    # Strip comments before scanning — the docstring / a code comment MAY
    # mention the deprecated symbol for reader context. What we want to
    # forbid is an actual call: `app.add_event_handler(...)`.
    import re
    code_only = re.sub(r"#.*", "", src)
    code_only = re.sub(r'""".*?"""', "", code_only, flags=re.DOTALL)
    assert ".add_event_handler(" not in code_only, (
        "apps/api/main.py still calls `app.add_event_handler(...)`. That "
        "raises AttributeError on some FastAPI/starlette combos in the wild "
        "(reported 2026-07-07). Migrate to the lifespan context manager: "
        "`app = FastAPI(..., lifespan=my_lifespan)` where `my_lifespan` is "
        "an `@asynccontextmanager` that awaits the refresh loop and yields."
    )


def test_main_uses_lifespan() -> None:
    """Positive assertion: startup hook is wired via lifespan."""
    src = MAIN_PY.read_text()
    assert "lifespan" in src, (
        "apps/api/main.py doesn't reference `lifespan`. Even if you're not "
        "starting any background tasks, use FastAPI(lifespan=...) as the "
        "future-proof shape so the seat-refresh loop can hook into it."
    )
