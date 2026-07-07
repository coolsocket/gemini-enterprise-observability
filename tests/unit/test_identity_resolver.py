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

"""RED regression: IdentityResolver — the single source of truth for
who a principal is.

Extensible via rule-list — every IdP (Google Workspace, OIDC/WIF from
any pool, Okta, Microsoft/Azure/Entra, service accounts, sim seeds) is
one rule. Adding a new IdP later = one new rule + one fixture entry
here. SQL views retain COALESCE as physical-layer fallback for cases
that hit BQ Scheduled Query without going through Python.

Verified fixtures sourced from responsive-lens-421108 real data
(/tmp/ge-samples/) plus hypothetical Okta / Azure shapes.
"""
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `apps.api...` imports work under
# pytest without depending on install / pyproject conftest.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.api.contexts.observability.domain.identity import (
    IdentityKind,
    IdentityResolver,
    Identity,
    DEFAULT_RULES,
    ResolverRule,
)


@pytest.fixture
def r() -> IdentityResolver:
    return IdentityResolver()


# ============================================================
# Real shapes verified against responsive-lens-421108 samples
# ============================================================
CASES = [
    # ---- Google Workspace email ----
    ("google email (real: devops@vivo.com)",
        "devops@vivo.com", None,
        IdentityKind.GOOGLE_EMAIL, "devops@vivo.com", True),
    ("google email even if a subject is also present",
        "alice@example.com",
        "principal://iam.googleapis.com/locations/global/workforcePools/x/subject/1",
        IdentityKind.GOOGLE_EMAIL, "alice@example.com", True),

    # ---- Service account (two shapes) ----
    ("SA via email (real: gemini-enterprise-apikey@...)",
        "gemini-enterprise-apikey@responsive-lens-421108.iam.gserviceaccount.com", None,
        IdentityKind.SERVICE_ACCOUNT,
        "gemini-enterprise-apikey@responsive-lens-421108.iam.gserviceaccount.com", False),
    ("SA via principal:// subject (impersonation shape)",
        None, "principal://iam.googleapis.com/projects/-/serviceAccounts/foo@bar.iam.gserviceaccount.com",
        IdentityKind.SERVICE_ACCOUNT, "foo@bar.iam.gserviceaccount.com", False),

    # ---- OIDC / Workforce Identity Federation - vivo real shape ----
    ("OIDC WIF vivo (real: workforcePools/vivo-gemini-enterprise/subject/72202797)",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/vivo-gemini-enterprise/subject/72202797",
        IdentityKind.OIDC_WIF_GENERIC, "72202797", True),

    # ---- Okta (hypothetical — real Okta pools name-contain 'okta') ----
    ("OIDC WIF via Okta pool",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/okta-corp/subject/00u1x2y3z",
        IdentityKind.OIDC_WIF_OKTA, "00u1x2y3z", True),
    ("OIDC WIF via nested Okta pool name",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/prod-okta-federation/subject/abc",
        IdentityKind.OIDC_WIF_OKTA, "abc", True),

    # ---- Microsoft / Azure Entra (hypothetical) ----
    ("OIDC WIF via Azure pool",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/azure-tenant-42/subject/aad-guid-1",
        IdentityKind.OIDC_WIF_AZURE, "aad-guid-1", True),
    ("OIDC WIF via Microsoft pool",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/microsoft-entra-prod/subject/xyz",
        IdentityKind.OIDC_WIF_AZURE, "xyz", True),
    ("OIDC WIF via Entra pool",
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/entra-corp/subject/user-42",
        IdentityKind.OIDC_WIF_AZURE, "user-42", True),

    # ---- Bare numeric OIDC subject (from user_activity.useriamprincipal) ----
    # (this shape appears when GE pre-extracts subject_id upstream)
    ("bare numeric OIDC subject (real: 11135014)",
        "11135014", None,
        IdentityKind.OIDC_SUBJECT, "11135014", True),
    ("bare numeric + full subject both present → subject wins",
        "11135014",
        "principal://iam.googleapis.com/locations/global/workforcePools/vivo-gemini-enterprise/subject/11135014",
        IdentityKind.OIDC_WIF_GENERIC, "11135014", True),

    # ---- Simulated seed accounts ----
    ("simulated (sim- prefix)",
        "sim-alice@example.com", None,
        IdentityKind.SIMULATED, "sim-alice@example.com", False),
    ("simulated with numeric-looking part",
        "sim-12345", None,
        IdentityKind.SIMULATED, "sim-12345", False),

    # ---- Unknown / degenerate ----
    ("both None",         None,           None,           IdentityKind.UNKNOWN, "", False),
    ("both empty strings", "",             "",             IdentityKind.UNKNOWN, "", False),
    ("garbled principal not matching any pattern",
        None, "principal://something/weird-shape-nobody-recognizes",
        IdentityKind.UNKNOWN, "principal://something/weird-shape-nobody-recognizes", False),
    ("empty subject + empty email",
        None, "", IdentityKind.UNKNOWN, "", False),
]


@pytest.mark.parametrize("label,email,subject,kind,actor_id,is_human", CASES)
def test_identity_resolver(r: IdentityResolver, label, email, subject, kind, actor_id, is_human):
    got = r.resolve(email, subject)
    assert got.kind == kind, f"{label}: kind {got.kind} != {kind}"
    assert got.actor_id == actor_id, f"{label}: actor_id {got.actor_id!r} != {actor_id!r}"
    assert got.is_human == is_human, f"{label}: is_human {got.is_human} != {is_human}"


def test_kind_is_string_enum_serializable() -> None:
    """API responses embed identity_kind — must serialize to a stable
    string so the frontend can switch on it."""
    import json
    assert IdentityKind.GOOGLE_EMAIL.value == "google_email"
    assert IdentityKind.OIDC_WIF_OKTA.value == "oidc_wif_okta"
    # JSON round-trip via the .value
    payload = {"kind": IdentityKind.OIDC_WIF_GENERIC.value}
    assert json.loads(json.dumps(payload))["kind"] == "oidc_wif_generic"


def test_extensible_via_custom_rules(r: IdentityResolver) -> None:
    """Adding a new IdP (say, Ping Identity) MUST be one new rule —
    no changes required to core Identity / IdentityKind machinery.
    Verifies the extensibility contract."""
    import re
    ping_re = re.compile(r"workforcePools/[^/]*ping[^/]*/subject/([^/]+)$", re.IGNORECASE)

    def matches(email, subject) -> bool:
        return bool(subject and ping_re.search(subject))

    def resolve(email, subject) -> Identity:
        sid = ping_re.search(subject).group(1)
        # Reuse OIDC_WIF_GENERIC kind for now — real extension would add
        # OIDC_WIF_PING to the IdentityKind enum too.
        return Identity(IdentityKind.OIDC_WIF_GENERIC, sid, f"{sid} (Ping)", True)

    # Prepend so it wins over the generic WIF matcher
    custom = IdentityResolver(
        rules=[ResolverRule(IdentityKind.OIDC_WIF_GENERIC, matches, resolve)] + list(DEFAULT_RULES)
    )
    got = custom.resolve(
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/ping-corp/subject/pingUser1",
    )
    assert got.actor_id == "pingUser1"
    assert "Ping" in got.display


def test_actor_id_matches_across_paths() -> None:
    """Path 2 (user_activity.useriamprincipal = '72202797') and Path 3
    (audit.principalSubject = '...workforcePools/.../subject/72202797')
    MUST resolve to the SAME actor_id so downstream JOINs unify them.
    This is the load-bearing invariant that makes cross-path aggregation
    correct."""
    r = IdentityResolver()
    path2 = r.resolve("72202797", None)
    path3 = r.resolve(
        None,
        "principal://iam.googleapis.com/locations/global/workforcePools/vivo-gemini-enterprise/subject/72202797",
    )
    assert path2.actor_id == path3.actor_id == "72202797", (
        f"Path 2 actor_id={path2.actor_id!r} vs Path 3 actor_id={path3.actor_id!r} — "
        "must match for cross-path JOINs (v_user_usage ↔ v_data_access) to unify."
    )
