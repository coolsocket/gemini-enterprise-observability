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

"""Full outer join of log-derived personas and subscription licenses.

Purpose: "全量方案" — one row per unique user_principal across BOTH
sources. Each row is tagged with a `cohort` label so the frontend
can filter to actionable buckets:

  matched        both sources have this user (has a seat AND generated
                 events) — the healthy adoption case
  licensed_only  paid for a seat but never generated observable events
                 within the log-retention window (candidates for
                 onboarding push or seat reclaim)
  log_only       events attributed to this principal but no matching
                 license entry (rare: license was revoked mid-history,
                 or a simulated/service user surfaced in logs)

Pure module: takes list-of-dicts in, returns dict out. No I/O,
no framework imports. The I/O is done by routes/refresh.py which
fans out to _fetch_user_licenses + v_user_persona in parallel and
hands the payloads here.

Join key: both `v_user_persona.user` and `userLicenses.userPrincipal`
are OIDC subject strings on WIF tenants (e.g. "11113722"). On
Workspace tenants both would be emails — same equality works.
"""
from __future__ import annotations

from typing import Any


def persona_join_licenses(
    persona_rows: list[dict[str, Any]],
    licensed_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Full outer join persona ⋈ licenses on user identity.

    Args:
      persona_rows: rows from `v_user_persona` — must have `user` key,
        may have persona / chat_turns_total / last_seen / origin /
        resources_created / builders columns.
      licensed_rows: rows from parse_user_licenses.users — must have
        `user_principal`, `state`, `last_login_time`, `license_config`,
        `create_time`.

    Returns:
      {
        "users": [
          {
            "user_principal": str,
            "cohort":         "matched" | "licensed_only" | "log_only",
            # persona-side fields (None if this user is licensed_only)
            "persona":            str | None,
            "chat_turns_total":   int,
            "chat_turns_7d":      int,
            "resources_created":  int,
            "last_seen":          str | None,
            "origin":             str | None,
            # license-side fields (None if this user is log_only)
            "license_state":      str | None,
            "last_login_time":    str | None,
            "license_config":     str | None,
            "create_time":        str | None,
          }, ...
        ],
        "counts": {
          "total":         int,   # len(users)
          "matched":       int,
          "licensed_only": int,
          "log_only":      int,
        },
      }
    """
    persona_by_id = {r["user"]: r for r in (persona_rows or []) if r.get("user")}
    licensed_by_id = {r["user_principal"]: r for r in (licensed_rows or []) if r.get("user_principal")}

    all_ids = set(persona_by_id) | set(licensed_by_id)
    users: list[dict[str, Any]] = []
    matched = licensed_only = log_only = 0

    for uid in all_ids:
        p = persona_by_id.get(uid)
        l = licensed_by_id.get(uid)
        if p and l:
            cohort = "matched"; matched += 1
        elif l:
            cohort = "licensed_only"; licensed_only += 1
        else:
            cohort = "log_only"; log_only += 1

        users.append({
            "user_principal":     uid,
            "cohort":             cohort,
            # persona-side (defaults keep numeric cols numeric so
            # frontend doesn't have to null-check every metric)
            "persona":            p.get("persona") if p else None,
            "chat_turns_total":   int(p.get("chat_turns_total") or 0) if p else 0,
            "chat_turns_7d":      int(p.get("chat_turns_7d") or 0) if p else 0,
            "resources_created":  int(p.get("resources_created") or 0) if p else 0,
            "last_seen":          p.get("last_seen") if p else None,
            "origin":             p.get("origin") if p else None,
            # license-side
            "license_state":      l.get("state") if l else None,
            "last_login_time":    l.get("last_login_time") if l else None,
            "license_config":     l.get("license_config") if l else None,
            "create_time":        l.get("create_time") if l else None,
        })

    return {
        "users": users,
        "counts": {
            "total":         len(users),
            "matched":       matched,
            "licensed_only": licensed_only,
            "log_only":      log_only,
        },
    }
