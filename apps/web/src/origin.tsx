import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import type { Origin } from "./api";

type Ctx = { origin: Origin; setOrigin: (o: Origin) => void };
const OriginContext = createContext<Ctx>({ origin: null, setOrigin: () => {} });

export function OriginProvider({ children }: { children: ReactNode }) {
  const [origin, setOrigin] = useState<Origin>(() => {
    try {
      const saved = localStorage.getItem("ge-origin");
      if (saved === "HUMAN" || saved === "AUTOMATION" || saved === "SIMULATED") return saved;
      // First visit: default to HUMAN so sim noise doesn't pollute view
      if (saved === "ALL") return null;
      return "HUMAN";
    } catch { return "HUMAN"; }
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
