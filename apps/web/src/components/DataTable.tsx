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

import { useMemo, useState } from "react";

type Col<T> = {
  key: keyof T | string;
  label: string;
  num?: boolean;
  mono?: boolean;
  render?: (row: T) => React.ReactNode;
  width?: string;
};

export function fmtTs(v: unknown): string {
  if (!v) return "—";
  try {
    return new Date(String(v)).toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
  } catch {
    return String(v);
  }
}

export function fmtNum(v: unknown): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString() : String(v);
}

export default function DataTable<T extends Record<string, any>>({
  rows, cols, filterKeys, dense,
}: {
  rows: T[];
  cols: Col<T>[];
  filterKeys?: (keyof T | string)[];
  dense?: boolean;
}) {
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const lo = q.toLowerCase();
    const keys = (filterKeys ?? cols.map((c) => c.key)) as string[];
    return rows.filter((r) => keys.some((k) => String(r[k] ?? "").toLowerCase().includes(lo)));
  }, [rows, q, filterKeys, cols]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const na = Number(av);
      const nb = Number(bv);
      if (!Number.isNaN(na) && !Number.isNaN(nb) && av !== "" && bv !== "") {
        return sortDir === "asc" ? na - nb : nb - na;
      }
      const sa = String(av); const sb = String(bv);
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const click = (k: string) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索..."
          className="flex-1 max-w-xs h-8 px-3 rounded-md bg-subtle border border-border-subtle text-sm placeholder:text-ink-muted focus:outline-none focus:border-border-default"
        />
        <span className="text-xs text-ink-muted">
          {sorted.length} / {rows.length} 行
        </span>
      </div>
      <div className="rounded-xl border border-border-subtle bg-surface overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-subtle">
              {cols.map((c) => (
                <th
                  key={String(c.key)}
                  onClick={() => click(String(c.key))}
                  style={c.width ? { width: c.width } : undefined}
                  className={`px-4 ${dense ? "py-2" : "py-3"} text-left font-medium text-ink-secondary cursor-pointer hover:text-ink-primary select-none border-b border-border-subtle ${c.num ? "text-right" : ""}`}
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="ml-1 text-ink-muted text-xs">{sortDir === "asc" ? "↑" : "↓"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={cols.length} className="px-4 py-10 text-center text-ink-muted text-sm">
                  {q ? "没有匹配项" : "暂无数据"}
                </td>
              </tr>
            ) : (
              sorted.map((r, i) => (
                <tr key={i} className="border-b border-border-subtle/60 last:border-0 hover:bg-subtle/50">
                  {cols.map((c) => (
                    <td
                      key={String(c.key)}
                      className={`px-4 ${dense ? "py-1.5" : "py-2.5"} text-ink-primary ${c.num ? "text-right tabular-nums" : ""} ${c.mono ? "font-mono text-[12px]" : ""}`}
                    >
                      {c.render ? c.render(r) : (r[c.key as string] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export type { Col };
