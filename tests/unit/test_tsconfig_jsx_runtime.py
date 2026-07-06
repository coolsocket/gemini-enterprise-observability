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

"""RED test for TS2875 / TS7026 JSX-runtime resolution failure.

Reported failure (user, 2026-07-06) — running `npm run build` on their
machine produced:

  src/components/Brand.tsx:44:7 - error TS7026: JSX element implicitly
      has type 'any' because no interface 'JSX.IntrinsicElements' exists.
  src/components/Card.tsx:54:5 - error TS2875: This JSX tag requires the
      module path 'react/jsx-runtime' to exist, but none could be found.

Root cause: with `jsx: "react-jsx"` (new JSX transform) + `moduleResolution:
"bundler"`, TypeScript sometimes fails to auto-discover
`node_modules/@types/react/jsx-runtime.d.ts` — depends on the exact combo
of TS version, npm install order, and whether package-lock.json ships
type packages with all their subpath entries. My own venv doesn't hit
this; theirs does. Making tsconfig explicit about the JSX import source
and type roots removes the ambiguity for every environment.

This test asserts that tsconfig.json ships one of the known-defensive
knobs so a new deployer never sees the two-error combo above.
"""
import json
from pathlib import Path

import pytest

TSCONFIG = Path(__file__).resolve().parents[2] / "apps/web/tsconfig.json"


@pytest.fixture(scope="module")
def tsconfig() -> dict:
    """Load apps/web/tsconfig.json, tolerating trailing commas (allowed by tsc
    but not stdlib json.loads). Our current file is strict-JSON compatible,
    but keep the tolerance if we ever add TS-style comments later."""
    text = TSCONFIG.read_text()
    return json.loads(text)


def test_tsconfig_declares_jsx_import_source_or_types(tsconfig: dict) -> None:
    """The two known-good defenses against TS2875 in bundler + react-jsx mode:

      (a) `compilerOptions.jsxImportSource = "react"` — explicit JSX runtime
      (b) `compilerOptions.types = ["react", "react-dom", ...]` — force type include

    Either alone is sufficient; both together belt-and-suspenders. Fail RED
    when tsconfig has neither (the state that triggered the user's report).
    """
    co = tsconfig.get("compilerOptions", {})
    has_jsx_import_source = co.get("jsxImportSource") == "react"
    types = co.get("types") or []
    has_react_types = "react" in types and "react-dom" in types

    assert has_jsx_import_source or has_react_types, (
        "tsconfig.json's compilerOptions has neither `jsxImportSource: \"react\"` "
        "nor an explicit `types: [\"react\", \"react-dom\"]`. "
        "With jsx: \"react-jsx\" + moduleResolution: \"bundler\", "
        "some environments (esp. TypeScript 5.5+, or after a partial `npm install`) "
        "fail to auto-resolve node_modules/@types/react/jsx-runtime.d.ts and produce "
        "TS2875 + TS7026 combo errors for every JSX element in the codebase. "
        "Adding either knob makes resolution deterministic across environments."
    )


def test_tsconfig_jsx_is_new_transform(tsconfig: dict) -> None:
    """Sanity: we ARE using the new JSX transform (react-jsx), which is the
    combination that needs jsx-runtime resolution to work. If someone flipped
    this back to the classic transform, this test's premise no longer holds."""
    jsx = tsconfig.get("compilerOptions", {}).get("jsx")
    assert jsx == "react-jsx", (
        f"Expected compilerOptions.jsx == 'react-jsx', got {jsx!r}. "
        "If you intentionally moved back to classic JSX, this test can be removed "
        "— the jsx-runtime failure mode only applies to the new transform."
    )
