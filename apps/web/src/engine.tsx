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
