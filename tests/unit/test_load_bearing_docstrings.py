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

"""Load-bearing functions MUST keep their docstrings.

Docstring hygiene isn't a general goal — the cleanliness audit picked out
the specific functions where a maintainer walking into the code cold
would benefit most. This test locks that subset so future refactors
don't accidentally strip them.
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# (module_path_relative_to_repo, function_name) — extend when a new
# critical fn appears that a first-time reader really needs the WHY for.
REQUIRED = [
    ("apps/api/routes/observability.py", "_rows"),
    ("apps/api/routes/observability.py", "view_rows"),
    ("apps/api/routes/quota.py", "quota_config_set"),
    ("apps/api/routes/refresh.py", "_start_seat_refresh_loop"),
]


@pytest.mark.parametrize("mod,func", REQUIRED)
def test_load_bearing_function_has_docstring(mod: str, func: str) -> None:
    tree = ast.parse((REPO / mod).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            doc = ast.get_docstring(node)
            assert doc and len(doc.strip()) > 20, (
                f"{mod}::{func} needs a substantive docstring "
                "(this list is deliberately small; add here only if the fn "
                "would confuse a first-time reader)."
            )
            return
    pytest.fail(f"{mod}::{func} not found — did it get renamed?")
