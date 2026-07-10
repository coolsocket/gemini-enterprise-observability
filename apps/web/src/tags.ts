// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Shared color-tag Tailwind class strings — extracted 2026-07-10 (R3a).
// Every page that renders an origin badge or persona badge should
// import from here so a palette change lands once, not seven times.

export const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  AUTOMATION: "bg-warn/10   text-warn   border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

export const PERSONA_TAG: Record<string, string> = {
  POWER_USER:      "bg-gblue/15   text-gblue   border-gblue/30",
  ACTIVE_CONSUMER: "bg-ggreen/15  text-ggreen  border-ggreen/30",
  TRIAL:           "bg-gyellow/15 text-gyellow border-gyellow/30",
  BUILDER:         "bg-gred/15    text-gred    border-gred/30",
  EXPLORER:        "bg-info/15    text-info    border-info/30",
  LURKER:          "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
  AUTOMATION:      "bg-ink-secondary/10 text-ink-secondary border-ink-secondary/30",
};
