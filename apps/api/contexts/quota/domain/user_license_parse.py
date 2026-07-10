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

"""Parser for Discovery Engine `userLicenses` responses.

Sister module to license_parse.py — that one aggregates the seat-count
side (`licenseConfigs`), this one aggregates the per-user assignment
side (`userLicenses`). Live-verified on responsive-lens-421108 that
the endpoint returns rows shaped like:

    {
      "userPrincipal": "10935612",                       # numeric OIDC subject for WIF tenants,
                                                          # email for Workspace tenants
      "licenseAssignmentState": "ASSIGNED" | "UNASSIGNED" | ...,
      "licenseConfig": "projects/N/locations/global/licenseConfigs/UUID",
      "createTime":  "2026-06-12T01:51:34Z",
      "updateTime":  "2026-06-12T01:51:34Z",
      "lastLoginTime": "2026-07-09T16:20:23Z"            # absent → never signed in
    }

Pure function: no I/O, no HTTP, no BigQuery — I/O belongs in
routes/refresh.py. Keeping this clean means tests can exercise the
shape without hitting the network.
"""
from __future__ import annotations

from typing import Any


def parse_user_licenses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalise a userLicenses response.

    Args:
        rows: the `userLicenses` array as returned by the DE list endpoint.

    Returns:
        {
          "count":          int,   # len(rows)
          "assigned_count": int,   # licenseAssignmentState == ASSIGNED
          "unseen_count":   int,   # assigned but no lastLoginTime
          "users": [
            { user_principal, state, license_config,
              create_time, update_time, last_login_time }, ...
          ],
        }
    """
    users: list[dict[str, Any]] = []
    assigned_count = 0
    unseen_count = 0
    for r in rows or []:
        state = r.get("licenseAssignmentState") or "UNKNOWN"
        last_login = r.get("lastLoginTime")
        if state == "ASSIGNED":
            assigned_count += 1
            if not last_login:
                unseen_count += 1
        users.append({
            "user_principal":  r.get("userPrincipal") or "",
            "state":           state,
            "license_config":  (r.get("licenseConfig") or "").split("/")[-1] or None,
            "create_time":     r.get("createTime"),
            "update_time":     r.get("updateTime"),
            "last_login_time": last_login,
        })
    return {
        "count":          len(users),
        "assigned_count": assigned_count,
        "unseen_count":   unseen_count,
        "users":          users,
    }
