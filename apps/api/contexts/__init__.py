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

"""Bounded contexts — each subpackage owns a piece of the domain.

Layout per context (loosely DDD, aimed to match the TDDD harness):

    contexts/<name>/
      INVARIANTS.md      # invariants + tests that guard them
      domain/            # pure functions & value objects; no I/O

Route modules (apps/api/routes/*) stay the composition layer — they
import from `contexts/<ctx>/domain/*` to build SQL / parse responses,
then call BigQuery via `apps.api.shared.infrastructure.bq_client`.
"""
