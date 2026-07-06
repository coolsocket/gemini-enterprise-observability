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

"""Pure domain modules for the observability context.

Rules for this layer:
  * No I/O — no `bigquery.Client`, no `google.auth`, no `os.environ`,
    no logging. Callers pass in what they need; we return primitives
    or dataclasses.
  * PROJECT + DATASET are dependency-injected as strings.
  * On bad input, raise ValueError. Route layer maps to HTTPException.
"""
