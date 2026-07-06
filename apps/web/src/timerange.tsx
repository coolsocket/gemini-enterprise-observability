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

import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

// Time range in hours. null = all time.
export type Range = null | 24 | 168 | 720;  // 24h, 7d, 30d, all

const RangeContext = createContext<{ range: Range; setRange: (r: Range) => void }>({
  range: null,
  setRange: () => {},
});

export function RangeProvider({ children }: { children: ReactNode }) {
  const [range, setRange] = useState<Range>(() => {
    try {
      const v = localStorage.getItem("ge-range");
      if (!v) return null;
      const n = Number(v);
      return (n === 24 || n === 168 || n === 720) ? (n as Range) : null;
    } catch { return null; }
  });
  useEffect(() => {
    try {
      if (range === null) localStorage.removeItem("ge-range");
      else localStorage.setItem("ge-range", String(range));
    } catch {}
  }, [range]);
  return <RangeContext.Provider value={{ range, setRange }}>{children}</RangeContext.Provider>;
}

export function useRange() {
  return useContext(RangeContext);
}

// Turn Range → backend `since_hours` query param string
export function rangeToParam(range: Range): string | undefined {
  return range === null ? undefined : String(range);
}
