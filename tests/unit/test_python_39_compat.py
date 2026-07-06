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

"""RED test for Python 3.9 incompatibility in FastAPI endpoint signatures.

Reported (user on Python 3.9.6, macOS system Python):

  TypeError: Unable to evaluate type annotation 'str | None'. If you are
  making use of the new typing syntax (unions using `|` since Python 3.10 …),
  you should either replace the use of new syntax with the existing `typing`
  constructs or install the `eval_type_backport` package.

Root cause is subtle: `from __future__ import annotations` makes ALL
annotations into deferred strings, which fixes runtime evaluation for
most code. But FastAPI's route registration explicitly re-evaluates each
endpoint signature at import time via `evaluate_forwardref(...)` — that
call runs `eval('str | None', globals, locals)` in the actual interpreter,
and on Python 3.9 that raises TypeError because the `X | Y` union syntax
is 3.10+.

So `from __future__ import annotations` is NOT sufficient for FastAPI on
3.9. Endpoints must use `Optional[str]` (or `Union[str, None]`) from
`typing`. This test asserts every parameter annotation in main.py that
uses the `|` union syntax gets caught and rewritten.
"""
import ast
from pathlib import Path

import pytest

# Was `apps/api/main.py` before the routes/ split (Phase 2, 2026-07-06).
# Now glob every module under apps/api/ so newly-added route files stay
# covered by the same PEP 604 gate.
API_ROOT = Path(__file__).resolve().parents[2] / "apps/api"
API_PY_FILES = sorted(API_ROOT.rglob("*.py"))
# Kept for backwards compat (unused directly but kept in case downstream tools grep for it)
MAIN_PY = API_ROOT / "main.py"


def _union_pipe_annotations(source: str) -> list[tuple[int, str]]:
    """Return (line_no, snippet) for every `X | Y` union used as an
    annotation on a function parameter or return type. This is the shape
    FastAPI cannot eval on Python 3.9."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []

    def is_bin_or(node: ast.AST) -> bool:
        return isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)

    def snippet(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return "<unparseable>"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check each parameter's annotation
            for arg in (list(node.args.args) + list(node.args.kwonlyargs)
                        + ([node.args.vararg] if node.args.vararg else [])
                        + ([node.args.kwarg] if node.args.kwarg else [])):
                if arg and arg.annotation and is_bin_or(arg.annotation):
                    hits.append((arg.annotation.lineno, snippet(arg.annotation)))
            # Return annotation
            if node.returns and is_bin_or(node.returns):
                hits.append((node.returns.lineno, snippet(node.returns)))
    return hits


def test_pyproject_declares_python_version() -> None:
    """Prevent regression: pyproject.toml must declare requires-python so
    `pip install` / IDE / pyenv warns users on unsupported Python up-front.
    Without it, users on 3.7/3.8 hit cryptic errors deep in dep imports."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    assert pyproject_path.exists(), (
        "pyproject.toml is missing. Declare `requires-python = \">=3.9\"` "
        "(or newer) so pip / IDE / pyenv warn users on unsupported Python."
    )
    # Cheap parse — no dep on tomllib/tomli, just regex
    text = pyproject_path.read_text()
    import re
    m = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    assert m, "pyproject.toml [project] section missing `requires-python`."
    req = m.group(1)
    assert "3." in req, f"requires-python looks wrong: {req!r}"


def test_no_pep604_unions_in_fastapi_endpoints() -> None:
    """Fail if any apps/api/**/*.py has `X | Y` union syntax in a function
    signature — FastAPI can't evaluate those on Python 3.9.

    Fix: rewrite to `Optional[X]` (imported from typing).
    """
    all_hits: list[tuple[Path, int, str]] = []
    for py in API_PY_FILES:
        source = py.read_text()
        for ln, snip in _union_pipe_annotations(source):
            all_hits.append((py, ln, snip))
    assert not all_hits, (
        f"Found {len(all_hits)} function-signature `X | Y` union(s) under apps/api/:\n"
        + "\n".join(f"  {p.relative_to(API_ROOT.parent.parent)}:{ln}: {snip}" for p, ln, snip in all_hits)
        + "\nFastAPI's route registration calls evaluate_forwardref() at import "
        "time, which real-eval's these annotations even under "
        "`from __future__ import annotations`. On Python 3.9 that raises "
        "TypeError. Rewrite each `X | None` as `Optional[X]` and each "
        "`A | B` as `Union[A, B]` from `typing`."
    )
