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

"""Identity resolution — one principal → one Identity object.

Extensible via rule list. Every IdP is one `ResolverRule`; to add
Okta / Azure / Ping / anything new, add one rule + one fixture in
`tests/unit/test_identity_resolver.py`. First matching rule wins,
so put SPECIFIC rules before GENERIC ones (Okta before generic WIF).

Physical invariants this preserves:
  - The `actor_id` returned MUST be the same string across paths for
    the same person — that's what makes v_user_usage (Path 2 numeric
    subject) JOIN cleanly with v_data_access (Path 3 principalSubject).
  - `is_human` is the ONE decision point that downstream aggregators
    should use to filter "real users" — no more scattered string checks.

SQL views retain a COALESCE + REGEXP_EXTRACT fallback for the same
resolution logic (see infra/sql_templates/views.sql.tmpl INV-obs-005)
because BQ Scheduled Queries hit BQ directly without going through
Python. Both layers agree on the actor_id shape so results align.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Sequence

import re


class IdentityKind(str, Enum):
    """Serialize as `.value` — the string form embeds in API responses."""
    GOOGLE_EMAIL     = "google_email"        # alice@example.com — Workspace
    OIDC_WIF_OKTA    = "oidc_wif_okta"       # Workforce Identity Federation via Okta
    OIDC_WIF_AZURE   = "oidc_wif_azure"      # WIF via Microsoft Entra / Azure AD
    OIDC_WIF_GENERIC = "oidc_wif_generic"    # WIF via any other IdP (custom pool)
    OIDC_SUBJECT     = "oidc_subject"        # Bare numeric subject (pre-extracted upstream)
    SERVICE_ACCOUNT  = "service_account"     # @gserviceaccount.com OR principal://.../serviceAccounts/
    SIMULATED        = "simulated"           # sim- prefixed seed accounts
    UNKNOWN          = "unknown"             # Fallback — flag as data-quality signal, not silent HUMAN


@dataclass(frozen=True)
class Identity:
    kind: IdentityKind
    actor_id: str    # Canonical string for JOIN — must match across Paths 2/3 for the same person
    display: str     # Human-facing label (may include IdP hint like "(Okta)")
    is_human: bool


@dataclass(frozen=True)
class ResolverRule:
    kind: IdentityKind
    matches: Callable[[Optional[str], Optional[str]], bool]
    resolve: Callable[[Optional[str], Optional[str]], Identity]


# ============================================================
# Shared regexes
# ============================================================
_SUBJECT_RE       = re.compile(r"subject/([^/]+)$")
_SA_IN_SUBJECT_RE = re.compile(r"serviceAccounts/([^/]+)")
_POOL_RE          = re.compile(r"workforcePools/([^/]+)")
_NUMERIC_RE       = re.compile(r"^\d+$")


def _pool_of(subject: str) -> str:
    m = _POOL_RE.search(subject or "")
    return m.group(1) if m else ""


def _extract_subject(subject: str) -> str:
    m = _SUBJECT_RE.search(subject or "")
    return m.group(1) if m else (subject or "")


# ============================================================
# Rule predicates + resolvers
# Each pair is one branch; order (in DEFAULT_RULES) is the priority.
# ============================================================
def _is_sim(email, subject) -> bool:
    return bool(email and email.startswith("sim-"))
def _resolve_sim(email, subject) -> Identity:
    return Identity(IdentityKind.SIMULATED, email or "", email or "", is_human=False)


def _is_sa_email(email, subject) -> bool:
    return bool(email and email.endswith("gserviceaccount.com"))
def _resolve_sa_email(email, subject) -> Identity:
    return Identity(IdentityKind.SERVICE_ACCOUNT, email, email, is_human=False)


def _is_sa_subject(email, subject) -> bool:
    return bool(subject and _SA_IN_SUBJECT_RE.search(subject))
def _resolve_sa_subject(email, subject) -> Identity:
    sa = _SA_IN_SUBJECT_RE.search(subject).group(1)
    return Identity(IdentityKind.SERVICE_ACCOUNT, sa, sa, is_human=False)


def _is_google_email(email, subject) -> bool:
    return bool(email and "@" in email and not email.endswith("gserviceaccount.com"))
def _resolve_google_email(email, subject) -> Identity:
    return Identity(IdentityKind.GOOGLE_EMAIL, email, email, is_human=True)


def _is_wif_okta(email, subject) -> bool:
    return bool(subject and "workforcePools" in subject
                and "okta" in _pool_of(subject).lower())
def _resolve_wif_okta(email, subject) -> Identity:
    sid = _extract_subject(subject)
    return Identity(IdentityKind.OIDC_WIF_OKTA, sid, f"{sid} (Okta)", is_human=True)


def _is_wif_azure(email, subject) -> bool:
    if not (subject and "workforcePools" in subject):
        return False
    p = _pool_of(subject).lower()
    return any(k in p for k in ("azure", "microsoft", "entra"))
def _resolve_wif_azure(email, subject) -> Identity:
    sid = _extract_subject(subject)
    return Identity(IdentityKind.OIDC_WIF_AZURE, sid, f"{sid} (Microsoft)", is_human=True)


def _is_wif_generic(email, subject) -> bool:
    # Falls through here only if Okta / Azure rules didn't match above.
    return bool(subject and "workforcePools" in subject and _SUBJECT_RE.search(subject))
def _resolve_wif_generic(email, subject) -> Identity:
    sid = _extract_subject(subject)
    pool = _pool_of(subject) or "wif"
    return Identity(IdentityKind.OIDC_WIF_GENERIC, sid, f"{sid} ({pool})", is_human=True)


def _is_numeric_subject(email, subject) -> bool:
    """Path 2 shape: GE pre-extracts subject_id into useriamprincipal."""
    return bool(email and _NUMERIC_RE.match(email))
def _resolve_numeric_subject(email, subject) -> Identity:
    return Identity(IdentityKind.OIDC_SUBJECT, email, f"{email} (OIDC)", is_human=True)


# ============================================================
# Default rule chain — ORDER MATTERS (specific → general)
# ============================================================
DEFAULT_RULES: Sequence[ResolverRule] = (
    # SPECIFIC SHAPES FIRST ----
    ResolverRule(IdentityKind.SIMULATED,        _is_sim,             _resolve_sim),
    ResolverRule(IdentityKind.SERVICE_ACCOUNT,  _is_sa_email,        _resolve_sa_email),
    ResolverRule(IdentityKind.SERVICE_ACCOUNT,  _is_sa_subject,      _resolve_sa_subject),
    # `@`-form Google email is more informative than a WIF subject when both
    # are present — an audit row with principalEmail=alice@... AND
    # principalSubject=<wif...> is the same person; use the email.
    ResolverRule(IdentityKind.GOOGLE_EMAIL,     _is_google_email,    _resolve_google_email),
    # WIF: vendor-specific pool names (Okta / Azure / Entra) first, then generic
    ResolverRule(IdentityKind.OIDC_WIF_OKTA,    _is_wif_okta,        _resolve_wif_okta),
    ResolverRule(IdentityKind.OIDC_WIF_AZURE,   _is_wif_azure,       _resolve_wif_azure),
    ResolverRule(IdentityKind.OIDC_WIF_GENERIC, _is_wif_generic,     _resolve_wif_generic),
    # Bare numeric — Path 2 shape, only reached when there's no WIF subject
    ResolverRule(IdentityKind.OIDC_SUBJECT,     _is_numeric_subject, _resolve_numeric_subject),
)


class IdentityResolver:
    """Resolve `(principalEmail, principalSubject)` → `Identity`.

    Thread-safe (rules are frozen dataclasses + immutable functions);
    a module-level singleton is fine for most callers via `resolve()`.
    """

    def __init__(self, rules: Sequence[ResolverRule] = DEFAULT_RULES):
        self.rules: List[ResolverRule] = list(rules)

    def resolve(self, email: Optional[str], subject: Optional[str] = None) -> Identity:
        # Normalize empty strings to None so predicates read cleanly.
        email = email or None
        subject = subject or None
        for rule in self.rules:
            if rule.matches(email, subject):
                return rule.resolve(email, subject)
        raw = email or subject or ""
        return Identity(IdentityKind.UNKNOWN, raw, raw or "(unknown)", is_human=False)


# ---- Module-level singleton for callers that don't need custom rules ----
_default_resolver = IdentityResolver()


def resolve(email: Optional[str], subject: Optional[str] = None) -> Identity:
    return _default_resolver.resolve(email, subject)
