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

"""RED for R9 (2026-07-11) — totals SQL must not depend on a stateful
`quota.default_tier` config key.

Problem: `v_quota_totals` view reads `quota.default_tier` and if the
key is missing, seat_pool.tier = NULL, JOIN tier_limits fails, totals
returns 0 rows. On read-only tenants (yehao ADC on vivo) we can't
insert the key via lazy-seed, so totals stays empty forever.

Fix: build totals SQL in the route with the COALESCE fallback inlined
(defaults to 'standard' when config key missing). Don't rely on the
view — that way even a truly read-only viewer works.

Move the SQL builder to a pure domain module so it's testable and the
route stays thin.
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_quota_sql_domain_module_exists() -> None:
    path = REPO / "apps/api/contexts/quota/domain/quota_sql.py"
    assert path.exists(), (
        "Missing apps/api/contexts/quota/domain/quota_sql.py — extract "
        "the totals SQL builder from routes/quota.py into a pure domain "
        "module so it's testable + the route stays thin."
    )
    src = path.read_text()
    assert "def render_totals_sql" in src, (
        "quota_sql.py must export a `render_totals_sql(project, dataset, "
        "window_days) -> str` builder."
    )
    # Pure module: no I/O imports
    for banned in ("google.cloud", "fastapi", "urllib.request", "requests"):
        assert banned not in src, (
            f"quota_sql.py should be a pure builder — no {banned}."
        )


def test_totals_sql_has_default_tier_coalesce_fallback() -> None:
    """The generated SQL must COALESCE the default_tier lookup with
    'standard' so tenants missing that config key still get a populated
    dashboard (grants leftover seats a tier so the JOIN works)."""
    from apps.api.contexts.quota.domain.quota_sql import render_totals_sql
    for w in (1, 7, 30):
        sql = render_totals_sql("p", "d", w)
        assert "COALESCE" in sql.upper(), (
            f"render_totals_sql({w}) missing COALESCE — the default_tier "
            f"fallback must be inlined so vivo (no quota.default_tier key) "
            f"still returns rows."
        )
        assert "'standard'" in sql or '"standard"' in sql, (
            f"render_totals_sql({w}) must fall back to 'standard' when "
            f"quota.default_tier is absent — got:\n{sql[:400]}"
        )


def test_totals_sql_does_not_read_v_quota_totals_view() -> None:
    """The whole point of the refactor is to NOT depend on the view
    (which itself depends on quota.default_tier being present).
    Both windows should query base tables (quota_config, user_tier,
    v_daily_usage_per_user) directly."""
    from apps.api.contexts.quota.domain.quota_sql import render_totals_sql
    for w in (1, 7, 30):
        sql = render_totals_sql("p", "d", w)
        assert "v_quota_totals" not in sql, (
            f"render_totals_sql({w}) still references v_quota_totals view "
            f"— that defeats the purpose of moving computation into the "
            f"route (view depends on quota.default_tier which vivo can't "
            f"write)."
        )


def test_route_quota_uses_sql_builder() -> None:
    """apps/api/routes/quota.py should import render_totals_sql from the
    domain module, not build the SQL inline anymore."""
    src = (REPO / "apps/api/routes/quota.py").read_text()
    assert "render_totals_sql" in src, (
        "quota.py should import + call render_totals_sql from the domain "
        "module. Inline SQL construction here means the SQL isn't unit-"
        "testable."
    )
    # And the direct SELECT * FROM v_quota_totals should be gone
    assert "SELECT * FROM `{PROJECT}.{DATASET}.v_quota_totals`" not in src, (
        "quota.py still does `SELECT * FROM v_quota_totals` — replace "
        "with render_totals_sql(PROJECT, DATASET, window_days)."
    )
