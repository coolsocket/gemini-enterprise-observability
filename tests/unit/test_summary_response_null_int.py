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

"""RED for SummaryResponse strict-int bug (2026-07-14).

Fresh-deploy sim (R14) exposed this: right after apply_views on a
fresh dataset, some sink target tables have zero rows and the CTEs
in render_summary_sql return NULL for the count columns (`a.c`,
`d.chat`, `d.total`). BQ hands us `None`. R2's SummaryResponse Pydantic
model declared these as strict `int` with default 0 — but Pydantic
only uses the default when the field is missing, NOT when the value
is present-and-None. Result: 500 on the summary endpoint until at
least some data exists.

Reproduces on 18001 (ge_first_deploy_sim) right after backfill
completes but before all snapshots refresh.

Fix: accept None → coerce to 0. Either Optional[int] with a
validator or a `mode="before"` normalizer that maps None to the
default for every numeric field.
"""


def test_summary_response_accepts_none_ints() -> None:
    """SummaryResponse must accept None for any numeric field and
    coerce it to 0 (or None-and-ok). Currently strict int rejects."""
    from apps.api.contexts.observability.domain.query_builder import SummaryResponse
    # Simulate a BQ row where several counts are NULL because their
    # source tables are empty (fresh deploy, backfill only covered
    # some log types, etc.)
    row = {
        "human_users": 0,
        "power_users": 0,
        "active_consumers": 0,
        "trial_users": 0,
        "human_builders": 0,
        "explorers": 0,
        "lurkers": 0,
        "human_chat_turns_7d": 0,
        "conversations_captured": 0,
        # These three come from CTEs that CAN return NULL on empty tables:
        "admin_actions": None,
        "chat_turns_total": None,
        "data_access_calls": None,
        "engines_tracked": 0,
        "last_admin_event": None,
        "last_data_access_event": None,
        "last_user_activity_event": None,
    }
    # Must not raise.
    resp = SummaryResponse(**row)
    # And downstream should see integers (or None, but consistently one).
    for f in ("admin_actions", "chat_turns_total", "data_access_calls"):
        v = getattr(resp, f)
        assert v == 0 or v is None, (
            f"{f} should be 0 or None, got {v!r}"
        )
