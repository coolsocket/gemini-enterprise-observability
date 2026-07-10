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

// Compact per-user metric block: big number + label + optional drill-down.
// Extracted 2026-07-10 (R3d) from UserDeepDive.tsx.
// Two drill modes:
//   plain    — timestamps + primary/secondary (e.g. list of AsyncAssist calls)
//   prompts  — timestamps + best-effort reverse-attributed prompt text

import React from "react";
import { fmtTs } from "./DataTable";

export type DrillPlain = {
  kind: "plain";
  rows: Array<{ timestamp: string; primary: string; secondary?: string }>;
};
export type DrillPrompts = {
  kind: "prompts";
  rows: Array<{
    timestamp: string;
    primary: string;
    prompt: string | null;
    delta_sec?: number | null;
  }>;
};
export type DrillData = DrillPlain | DrillPrompts;

export function Metric({
  value, label, sub, accent, icon, drill, open, onToggle,
}: {
  value: number | string;
  label: string;
  sub?: React.ReactNode;
  accent: string;
  icon?: string;
  drill?: DrillData;
  open?: boolean;
  onToggle?: () => void;
}) {
  const clickable = !!onToggle && !!drill;
  return (
    <div className="group">
      <button
        type="button"
        onClick={clickable ? onToggle : undefined}
        disabled={!clickable}
        className={`flex items-baseline gap-3 w-full text-left ${
          clickable ? "hover:opacity-90 cursor-pointer" : "cursor-default"
        }`}
      >
        {icon && <span className="text-xl shrink-0">{icon}</span>}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-semibold tabular-nums ${accent}`}>{value}</span>
            <span className="text-xs text-ink-secondary font-medium uppercase tracking-wide">{label}</span>
            {clickable && (
              <span className="text-[10px] text-ink-muted ml-1">
                {open ? "▾ 收起" : "▸ 看哪几次"}
              </span>
            )}
          </div>
          {sub && <div className="text-[11px] text-ink-muted mt-0.5">{sub}</div>}
        </div>
      </button>
      {clickable && open && drill && (
        <div className="mt-2 ml-9 max-h-[260px] overflow-y-auto border-l-2 border-info/30 pl-3 space-y-1.5">
          {drill.rows.length === 0 ? (
            <div className="text-[11px] text-ink-muted py-1">
              最近事件里没匹配项（可能已过 retention window）
            </div>
          ) : drill.kind === "plain" ? (
            drill.rows.map((r, i) => (
              <div key={`${r.timestamp}-${i}`} className="text-[11px] flex items-baseline gap-2">
                <span className="text-ink-muted font-mono shrink-0">{fmtTs(r.timestamp)}</span>
                <span className="text-ink-secondary font-mono">{r.primary}</span>
                {r.secondary && <span className="text-ink-muted">{r.secondary}</span>}
              </div>
            ))
          ) : (
            drill.rows.map((r, i) => (
              <div key={`${r.timestamp}-${i}`} className="text-[11px]">
                <div className="flex items-baseline gap-2">
                  <span className="text-ink-muted font-mono shrink-0">{fmtTs(r.timestamp)}</span>
                  <span className="text-ink-secondary font-mono text-[10px]">{r.primary}</span>
                </div>
                {r.prompt ? (
                  <div className="ml-3 mt-0.5 text-ink-primary leading-snug">
                    <span className="text-info">"</span>{r.prompt}<span className="text-info">"</span>
                    {r.delta_sec != null && (
                      <span className="text-[9px] text-ink-muted ml-2">±{Math.abs(r.delta_sec)}s</span>
                    )}
                  </div>
                ) : (
                  <div className="ml-3 mt-0.5 text-ink-muted italic">prompt 未找到</div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
