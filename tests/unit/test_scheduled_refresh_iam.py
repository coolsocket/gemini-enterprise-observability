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

"""RED test for issue #2 item 1 — DTS TokenCreator grant missing.

Reported by @panliuyang-debug (2026-07-06):

  google_bigquery_data_transfer_config.snapshot_refresh runs as
  ge-observability-sa, but nothing grants the BQ Data Transfer service
  agent permission to mint tokens for it. First run fails with:

    Error code 9 : DTS service agent needs iam.serviceAccounts.getAccessToken
    permission on ge-observability-sa@<project>...

Fix: add a google_service_account_iam_member for
`service-<project_number>@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com`
with roles/iam.serviceAccountTokenCreator on the dashboard SA. Gated by
`enable_scheduled_refresh` (same as the transfer config itself).
"""
from pathlib import Path
import re

MAIN_TF = Path(__file__).resolve().parents[2] / "terraform/main.tf"


def test_dts_service_agent_gets_token_creator() -> None:
    """Terraform MUST include a service_account_iam_member (or equivalent)
    granting the DTS service agent roles/iam.serviceAccountTokenCreator on
    the dashboard SA. Otherwise the very first scheduled refresh fails."""
    src = MAIN_TF.read_text()
    # Accept either of the canonical shapes:
    has_iam_binding = re.search(
        r"resource\s+\"google_service_account_iam_(?:member|binding)\"",
        src,
    ) is not None
    has_token_creator_role = "roles/iam.serviceAccountTokenCreator" in src
    has_dts_agent = "gcp-sa-bigquerydatatransfer" in src
    assert has_iam_binding and has_token_creator_role and has_dts_agent, (
        "terraform/main.tf missing the DTS TokenCreator grant. First "
        "scheduled refresh fails with:\n"
        "  Error code 9 : DTS service agent needs iam.serviceAccounts."
        "getAccessToken permission on ge-observability-sa@<project>...\n"
        "Add a google_service_account_iam_member (gated by "
        "enable_scheduled_refresh) that binds "
        "service-<project_number>@gcp-sa-bigquerydatatransfer.iam."
        "gserviceaccount.com to roles/iam.serviceAccountTokenCreator on "
        "google_service_account.dashboard_sa."
    )
