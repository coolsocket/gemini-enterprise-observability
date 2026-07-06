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

import { useQuery } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { api, ConversationWithResponseRow } from "../api";
import { EmptyState, Panel } from "../components/Card";
import { fmtTs } from "../components/DataTable";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";

const STATUS_TAG: Record<string, string> = {
  STOP:        "bg-ggreen/15 text-ggreen border-ggreen/30",
  MAX_TOKENS:  "bg-gyellow/15 text-gyellow border-gyellow/30",
  SAFETY:      "bg-gred/15   text-gred   border-gred/30",
  OTHER:       "bg-info/15   text-info   border-info/30",
  UNSPECIFIED: "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
};

const ORIGIN_DOT: Record<string, string> = {
  HUMAN:      "bg-ggreen",
  SIMULATED:  "bg-info",
  AUTOMATION: "bg-warn",
  UNKNOWN:    "bg-ink-muted",
};

type Filter = "all" | "matched" | "prompt_only";

export default function Conversations() {
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const { range } = useRange();
  const q = useQuery({
    queryKey: ["v_conversations_with_response", origin, engineId, range],
    queryFn: () => api.view<ConversationWithResponseRow>("v_conversations_with_response", origin, engineId, range),
  });

  const [filter, setFilter] = useState<Filter>("all");
  const [openSession, setOpenSession] = useState<string | null>(null);
  const [bannerOpen, setBannerOpen] = useState(false);

  // Group rows by session_id
  const sessions = useMemo(() => {
    const rows = q.data?.rows ?? [];
    const bySession: Record<string, ConversationWithResponseRow[]> = {};
    rows.forEach((r) => {
      const key = r.session_id ?? `__no_session_${r.prompt_trace_id}`;
      (bySession[key] ??= []).push(r);
    });
    return Object.entries(bySession)
      .map(([sid, turns]) => ({
        key: sid,
        session_id: sid.startsWith("__no_session") ? null : sid,
        turns: turns.sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
        actor: turns[0].actor_email,
        origin: turns[0].origin,
        engine: turns[0].engine_display_name ?? turns[0].engine_id_raw,
        first: turns[0].timestamp,
        last: turns[turns.length - 1].timestamp,
        // join_status = matched_gen_ai_choice (trace-JOIN) | matched_service_reply
        //   (inline serviceTextReply) | no_response. Treat both matched_* as "has response".
        matched_count: turns.filter((t) => t.join_status?.startsWith("matched")).length,
        no_response_count: turns.filter((t) => t.join_status === "no_response").length,
      }))
      .sort((a, b) => b.last.localeCompare(a.last));
  }, [q.data]);

  const filtered = sessions.filter(s =>
    filter === "all" ? true :
    filter === "matched" ? s.matched_count > 0 :
    s.matched_count === 0
  );

  // Stats for KPI strip
  const totalSessions = sessions.length;
  const matchedSessions = sessions.filter(s => s.matched_count > 0).length;
  const totalTurns = sessions.reduce((a, s) => a + s.turns.length, 0);
  const matchedTurns = sessions.reduce((a, s) => a + s.matched_count, 0);
  const distinctUsers = new Set(sessions.map(s => s.actor)).size;

  // Auto-open most recent session that has a response (better default than empty state)
  useEffect(() => {
    if (openSession || filtered.length === 0) return;
    const preferred = filtered.find(s => s.matched_count > 0) ?? filtered[0];
    setOpenSession(preferred.key);
  }, [filtered, openSession]);

  const selected = filtered.find(s => s.key === openSession);

  return (
    <div className="space-y-3">
      {/* Compact banner — collapsed by default */}
      <div className="rounded-lg border border-border-subtle bg-subtle/40 px-4 py-2 text-xs">
        <button
          onClick={() => setBannerOpen(!bannerOpen)}
          className="flex items-center gap-2 w-full text-left text-ink-secondary hover:text-ink-primary"
        >
          <span className="text-ink-muted">{bannerOpen ? "▾" : "▸"}</span>
          <span>📋 关于"无响应"</span>
          <span className="text-ink-muted">— GE 控制台 UI (v1main) 不写 <code className="bg-subtle px-1 rounded">gen_ai.choice</code> 日志，所以 UI 发起的对话只能看到 prompt</span>
          {!bannerOpen && <span className="ml-auto text-ink-muted">展开 4 条限制</span>}
        </button>
        {bannerOpen && (
          <ul className="text-[11px] text-ink-secondary mt-2 ml-5 space-y-0.5 list-disc list-inside">
            <li><b>无响应原因</b>：(1) 真人通过 GE 控制台 UI 调用走 v1main，该路径不写 gen_ai.choice 日志 → response 永远抓不到；(2) sim SA 通过 REST 调，client 提前断 streaming 会导致 choice log 不完整</li>
            <li><b>多模态</b>：streamAssist API 不接受 inlineData，图片/文件走"先上传 session files → chat 引用 file_id"。看 Data Access 页的 session_files 列</li>
            <li>prompt 和 response 用<b>精确 trace_id JOIN</b>（不是时间窗模糊配对）</li>
            <li>response chunks 已按 trace_id 聚合（STOP 终结）+ 自动拼接 streaming 文本</li>
          </ul>
        )}
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-ink-muted">总会话</div>
          <div className="text-2xl font-semibold text-ink-primary tabular-nums mt-0.5">{totalSessions}</div>
        </div>
        <div className="rounded-lg border border-ggreen/30 bg-ggreen/5 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-ggreen/80">含响应</div>
          <div className="text-2xl font-semibold text-ggreen tabular-nums mt-0.5">{matchedSessions}</div>
          <div className="text-[10px] text-ink-muted">{totalSessions > 0 ? Math.round(matchedSessions / totalSessions * 100) : 0}%</div>
        </div>
        <div className="rounded-lg border border-ink-muted/30 bg-subtle/40 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-ink-muted">仅 prompt</div>
          <div className="text-2xl font-semibold text-ink-secondary tabular-nums mt-0.5">{totalSessions - matchedSessions}</div>
          <div className="text-[10px] text-ink-muted">v1main UI</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-ink-muted">总 turns</div>
          <div className="text-2xl font-semibold text-ink-primary tabular-nums mt-0.5">{totalTurns}</div>
          <div className="text-[10px] text-ink-muted">含响应 {matchedTurns}</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-ink-muted">独立用户</div>
          <div className="text-2xl font-semibold text-ink-primary tabular-nums mt-0.5">{distinctUsers}</div>
        </div>
      </div>

      {/* Two-pane: list + detail */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-3">
        {/* Left: session list */}
        <Panel
          title={`会话 · ${filtered.length}`}
          action={
            <div className="flex items-center gap-1 text-[10px]">
              {(["all", "matched", "prompt_only"] as Filter[]).map(f => (
                <button
                  key={f}
                  onClick={() => { setFilter(f); setOpenSession(null); }}
                  className={`h-6 px-2 rounded ${filter === f ? "bg-info/15 text-info border border-info/30" : "text-ink-muted hover:text-ink-secondary"}`}
                >
                  {f === "all" ? "全部" : f === "matched" ? "✓ 有响应" : "仅 prompt"}
                </button>
              ))}
            </div>
          }
        >
          {q.isLoading ? <EmptyState title="加载中…" /> :
           filtered.length === 0 ? (
            <EmptyState title="没有会话" hint={filter !== "all" ? "改 filter 试试" : "等待 chat 流量"} />
          ) : (
            <ul className="divide-y divide-border-subtle/40 -m-5 max-h-[700px] overflow-y-auto">
              {filtered.map((s) => {
                const isOpen = openSession === s.key;
                const hasResp = s.matched_count > 0;
                return (
                  <li key={s.key}>
                    <button
                      onClick={() => setOpenSession(isOpen ? null : s.key)}
                      className={`w-full text-left px-4 py-2.5 transition-colors ${
                        isOpen ? "bg-info-bg/15 border-l-2 border-info" : "hover:bg-subtle/40 border-l-2 border-transparent"
                      }`}
                    >
                      {/* Row 1: indicator + actor */}
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${ORIGIN_DOT[s.origin ?? "UNKNOWN"]}`} />
                        <span className="text-[11px] text-ink-muted truncate font-mono flex-1" title={s.actor}>
                          {s.actor.length > 36 ? s.actor.slice(0, 28) + "…" : s.actor}
                        </span>
                        {hasResp ? (
                          <span className="text-[9px] text-ggreen shrink-0" title={`${s.matched_count}/${s.turns.length} 有响应`}>
                            ✓ {s.matched_count}/{s.turns.length}
                          </span>
                        ) : (
                          <span className="text-[9px] text-ink-muted shrink-0">prompt-only</span>
                        )}
                      </div>
                      {/* Row 2: prompt prominent */}
                      <div className="text-sm text-ink-primary line-clamp-2 leading-snug">
                        {s.turns[0].prompt}
                      </div>
                      {/* Row 3: meta */}
                      <div className="text-[10px] text-ink-muted mt-1 flex gap-2 items-center">
                        <span>{s.turns.length} turn{s.turns.length > 1 ? "s" : ""}</span>
                        <span>·</span>
                        <span className="truncate flex-1">{s.engine ?? "—"}</span>
                        <span className="shrink-0">{fmtTs(s.last)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        {/* Right: session detail */}
        <Panel
          title={selected ? `Session · ${selected.turns.length} turn${selected.turns.length > 1 ? "s" : ""}` : "选个会话"}
          action={selected && (
            <div className="text-[10px] text-ink-muted font-mono truncate max-w-[300px]" title={selected.session_id ?? ""}>
              {selected.session_id ? selected.session_id.slice(0, 20) + "…" : "no session id"}
            </div>
          )}
        >
          {!selected ? <EmptyState title="左侧点一条" /> : (
            <div className="space-y-3 max-h-[700px] overflow-y-auto pr-1 -mr-1">
              {/* Session header */}
              <div className="text-[11px] text-ink-muted flex flex-wrap gap-2 items-center border-b border-border-subtle/40 pb-2">
                <span className={`inline-block w-1.5 h-1.5 rounded-full ${ORIGIN_DOT[selected.origin ?? "UNKNOWN"]}`} />
                <span className="font-mono text-ink-secondary">{selected.actor}</span>
                <span>·</span>
                <span>{selected.engine ?? "—"}</span>
                <span>·</span>
                <span>{fmtTs(selected.first)}</span>
              </div>

              {/* Turns */}
              {selected.turns.map((turn, i) => (
                <div key={turn.prompt_trace_id} className="rounded-lg border border-border-subtle/60 overflow-hidden">
                  {/* User prompt — chat bubble style */}
                  <div className="px-3 py-2 bg-info-bg/5 border-l-2 border-info/40">
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className="text-[10px] font-semibold text-info uppercase tracking-wide">User</span>
                      <span className="text-[10px] text-ink-muted">turn {i + 1} · {fmtTs(turn.timestamp)}</span>
                    </div>
                    <div className="text-sm text-ink-primary whitespace-pre-wrap break-words leading-snug">{turn.prompt}</div>
                  </div>

                  {/* Model response or no_response note */}
                  {turn.join_status === "no_response" ? (
                    <div className="px-3 py-1.5 text-[11px] text-ink-muted italic flex items-center gap-2 bg-subtle/30">
                      <span className="text-[10px] uppercase tracking-wide text-ink-muted font-semibold not-italic">model</span>
                      <span>· 响应未记录 (v1main UI 路径)</span>
                    </div>
                  ) : (
                    <>
                      {turn.reasoning_text && (
                        <div className="px-3 py-2 border-t border-border-subtle/40 bg-subtle/20">
                          <div className="flex items-baseline gap-2 mb-1">
                            <span className="text-[10px] font-semibold text-gyellow uppercase tracking-wide">Reasoning</span>
                            <span className="text-[10px] text-ink-muted">deep think</span>
                          </div>
                          <div className="text-xs text-ink-muted whitespace-pre-wrap break-words font-mono leading-snug">
                            {turn.reasoning_text}
                          </div>
                        </div>
                      )}
                      <div className="px-3 py-2 border-t border-border-subtle/40 bg-ggreen/5 border-l-2 border-ggreen/40">
                        <div className="flex items-baseline gap-2 mb-1">
                          <span className="text-[10px] font-semibold text-ggreen uppercase tracking-wide">Model</span>
                          {turn.response_status && (
                            <span className={`inline-flex items-center px-1.5 py-px rounded text-[9px] font-medium border ${STATUS_TAG[turn.response_status] ?? STATUS_TAG.UNSPECIFIED}`}>
                              {turn.response_status}
                            </span>
                          )}
                          <span className="text-[10px] text-ink-muted">{turn.chunk_count ?? 0} chunks</span>
                        </div>
                        <div className="text-sm text-ink-secondary whitespace-pre-wrap break-words leading-snug">
                          {turn.response_text ?? "—"}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
