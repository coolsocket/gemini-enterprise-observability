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

type Ctx = { engineId: string | null; setEngineId: (id: string | null) => void };
const EngineContext = createContext<Ctx>({ engineId: null, setEngineId: () => {} });

export function EngineProvider({ children }: { children: ReactNode }) {
  const [engineId, setEngineId] = useState<string | null>(() => {
    try { return localStorage.getItem("ge-engine") || null; } catch { return null; }
  });
  useEffect(() => {
    try {
      if (engineId) localStorage.setItem("ge-engine", engineId);
      else localStorage.removeItem("ge-engine");
    } catch {}
  }, [engineId]);
  return <EngineContext.Provider value={{ engineId, setEngineId }}>{children}</EngineContext.Provider>;
}

export function useEngine() {
  return useContext(EngineContext);
}
