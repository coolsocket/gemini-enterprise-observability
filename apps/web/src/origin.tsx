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
import type { Origin } from "./api";

type Ctx = { origin: Origin; setOrigin: (o: Origin) => void };
const OriginContext = createContext<Ctx>({ origin: null, setOrigin: () => {} });

export function OriginProvider({ children }: { children: ReactNode }) {
  const [origin, setOrigin] = useState<Origin>(() => {
    try {
      const saved = localStorage.getItem("ge-origin");
      if (saved === "HUMAN" || saved === "AUTOMATION" || saved === "SIMULATED") return saved;
      // First visit: default to null (全部). Old default was "HUMAN"
      // which hid every UNKNOWN principal — bad UX for fresh OIDC-only
      // tenants where a stale view SQL might mis-classify everyone as
      // UNKNOWN and the page looks empty. Better default: show all,
      // let the user tighten filter if the mix is noisy.
      return null;
    } catch { return null; }
  });
  useEffect(() => {
    try {
      // store ALL as sentinel for "user explicitly chose 全部"
      localStorage.setItem("ge-origin", origin ?? "ALL");
    } catch {}
  }, [origin]);
  return <OriginContext.Provider value={{ origin, setOrigin }}>{children}</OriginContext.Provider>;
}

export function useOrigin() {
  return useContext(OriginContext);
}
