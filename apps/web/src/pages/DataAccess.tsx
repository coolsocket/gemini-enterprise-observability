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
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, DataAccessRow, DataAccessSummaryRow, AgentDirectoryRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";
import { ORIGIN_TAG } from "../tags";

type DailyRow = { d: string; actor_email: string; feature: string; n: number };
const DAILY_FEATURE_ORDER = ["chat", "deep_research", "notebooklm", "a2a", "agent_create"];
const DAILY_FEATURE_META: Record<string, { label: string; icon: string; color: string }> = {
  chat:          { label: "Chat",         icon: "💬", color: "text-ggreen" },
  deep_research: { label: "Deep Research",icon: "🔬", color: "text-info" },
  notebooklm:    { label: "NotebookLM",   icon: "📓", color: "text-gblue" },
  a2a:           { label: "A2A",          icon: "🧩", color: "text-gyellow" },
  agent_create:  { label: "Agent 创建",   icon: "🔧", color: "text-warn" },
};


export default function DataAccess() {
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const { range } = useRange();
  const summary  = useQuery({
    queryKey: ["v_data_access_summary", origin, engineId, range],
    queryFn: () => api.view<DataAccessSummaryRow>("v_data_access_summary", origin, engineId, range),
  });
  const timeline = useQuery({
    queryKey: ["v_data_access", origin, engineId, range],
    queryFn: () => api.view<DataAccessRow>("v_data_access", origin, engineId, range),
  });
  const daily = useQuery({
    // v_daily_usage_per_user has no origin/engine columns — global daily.
    queryKey: ["v_daily_usage_per_user", range],
    queryFn: () => api.view<DailyRow>("v_daily_usage_per_user", undefined, null, range),
  });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });

  // Pivot daily rows → (day → {feature: n, total: n}) sorted desc by day.
  const dailyPivot = useMemo(() => {
    const byDay: Record<string, Record<string, number>> = {};
    (daily.data?.rows ?? []).forEach(r => {
      if (!byDay[r.d]) byDay[r.d] = {};
      byDay[r.d][r.feature] = (byDay[r.d][r.feature] ?? 0) + r.n;
    });
    return Object.entries(byDay)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([d, feats]) => ({
        d,
        feats,
        total: DAILY_FEATURE_ORDER.reduce((s, f) => s + (feats[f] ?? 0), 0),
      }));
  }, [daily.data?.rows]);

  // Simplified: hide autocomplete (noise) + session_files; surface chat/search/session/feedback
  const summaryCols: Col<DataAccessSummaryRow>[] = [
    { key: "actor_email", label: "Actor", mono: true },
    {
      key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ),
    },
    { key: "engine_display_name", label: "Engine",
      render: (r) => r.engine_display_name ?? <span className="text-ink-muted">—</span> },
    { key: "chat_turns", label: "Chat 回合", num: true,
      render: (r) => <span className={r.chat_turns > 0 ? "text-ggreen font-medium" : "text-ink-muted"}>{r.chat_turns}</span> },
    { key: "deep_research_calls", label: "Deep Research", num: true,
      render: (r) => <span className={r.deep_research_calls > 0 ? "text-info font-medium" : "text-ink-muted"} title="AsyncAssist + ReadAsyncAssist · prompt/response 不被记录，只能看到调用次数">{r.deep_research_calls}</span> },
    { key: "notebooklm_notebook_ops", label: "NotebookLM", num: true,
      render: (r) => {
        const total = r.notebooklm_notebook_ops + r.notebooklm_content_ops + r.notebooklm_audio_ops;
        return <span className={total > 0 ? "text-gblue font-medium" : "text-ink-muted"} title={`notebook ops=${r.notebooklm_notebook_ops} (CRUD + GenerateGuide + DiscoverSources + Account)\ncontent ops=${r.notebooklm_content_ops} (Sources + Notes + Artifacts)\naudio ops=${r.notebooklm_audio_ops} (podcast overviews)`}>{total}</span>;
      } },
    { key: "a2a_invocations", label: "A2A 调用", num: true,
      render: (r) => <span className={r.a2a_invocations > 0 ? "text-ggreen font-medium" : "text-ink-muted"} title="assistants.agents.a2a.v1.* — marketplace 或自建 agent 通过 A2A 协议调用">{r.a2a_invocations}</span> },
    { key: "session_files", label: "文件操作", num: true,
      render: (r) => <span className={r.session_files > 0 ? "text-ink-secondary" : "text-ink-muted"} title="List + Download SessionFile">{r.session_files}</span> },
    { key: "programmatic_searches", label: "Search", num: true,
      render: (r) => <span className={r.programmatic_searches > 0 ? "text-gblue" : "text-ink-muted"}>{r.programmatic_searches}</span> },
    { key: "session_ops", label: "Session 操作", num: true,
      render: (r) => <span className="text-ink-secondary">{r.session_ops}</span> },
    { key: "feedback_events", label: "反馈事件", num: true,
      render: (r) => <span className={r.feedback_events > 0 ? "text-gyellow" : "text-ink-muted"}>{r.feedback_events}</span> },
    { key: "total_data_access", label: "Total", num: true,
      render: (r) => <span className="font-semibold">{r.total_data_access}</span> },
    { key: "last_access", label: "最近", mono: true, render: (r) => fmtTs(r.last_access) },
  ];

  const timelineCols: Col<DataAccessRow>[] = [
    { key: "timestamp", label: "时间", mono: true, render: (r) => fmtTs(r.timestamp), width: "180px" },
    { key: "actor_email", label: "Actor", mono: true },
    {
      key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ),
    },
    { key: "action", label: "动作" },
    { key: "engine_display_name", label: "Engine",
      render: (r) => r.engine_display_name ?? <span className="text-ink-muted text-xs">{r.engine_id_raw ?? "—"}</span> },
    { key: "datastore_id", label: "DataStore", mono: true,
      render: (r) => r.datastore_id ?? <span className="text-ink-muted">—</span> },
    { key: "caller_ip", label: "Caller IP", mono: true,
      render: (r) => <span className="text-ink-muted text-xs">{r.caller_ip ?? "—"}</span> },
  ];

  const [showTimeline, setShowTimeline] = useState(false);

  // Serialise the summary rows as CSV. Escapes commas/quotes/newlines
  // per RFC 4180. Streams a blob to a hidden anchor with `download` attr.
  function downloadCSV(rows: DataAccessSummaryRow[] | undefined, filename: string) {
    if (!rows || rows.length === 0) return;
    const cols = Object.keys(rows[0]);
    const esc = (v: unknown) => {
      const s = v === null || v === undefined ? "" : String(v);
      return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const body = [cols.join(","), ...rows.map(r => cols.map(c => esc((r as Record<string, unknown>)[c])).join(","))].join("\n");
    const blob = new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      {/* Hint */}
      <div className="text-xs text-ink-muted px-1 space-y-1">
        <div>💡 数据面读取统计。Autocomplete（搜索框打字）属于噪音指标已隐藏；如需查看原始逐笔记录展开下方时间线。</div>
        <div>⚠️ <b>Deep Research</b>（AsyncAssist / ReadAsyncAssist）只能看到<b>调用次数</b> — prompt + response 文本不被 gen_ai 日志记录（与 GE UI 路径同源限制）。要看原始 prompt 内容请去 GE 后台的 Deep Research 任务列表。</div>
        <div>🖼️ <b>Image / Video 生成</b>: GE 目前<b>不输出</b> customer audit logs — 生成任务跑在 Google 内部基础设施上,没有 principalEmail / methodName 可挂钩。我们试过按 prompt 关键字("generate an image of…")启发式匹配,误报率高到不可用（"summarize this video" 会被误分类）。等 GE 暴露 per-feature 计数 API 再启用。</div>
      </div>

      {/* Daily × feature panel */}
      <Panel
        title="每日 × feature 使用量"
        action={
          <span className="text-[10px] text-ink-muted">
            来自 v_daily_usage_per_user · 加州日 · 忽略 origin 过滤
          </span>
        }
      >
        {!daily.data ? <EmptyState title="加载中…" /> :
         dailyPivot.length === 0 ? <EmptyState title="无数据" hint="选定时间窗内没有事件" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-muted border-b border-border-subtle/40">
                  <th className="py-1 pr-3 font-normal">日期</th>
                  {DAILY_FEATURE_ORDER.map(f => (
                    <th key={f} className="py-1 pr-3 font-normal text-right"
                        title={DAILY_FEATURE_META[f].label}>
                      {DAILY_FEATURE_META[f].icon} {DAILY_FEATURE_META[f].label}
                    </th>
                  ))}
                  <th className="py-1 pr-3 font-normal text-right">Σ 全天</th>
                </tr>
              </thead>
              <tbody>
                {dailyPivot.map(({ d, feats, total }) => (
                  <tr key={d} className="border-b border-border-subtle/20 hover:bg-subtle/30">
                    <td className="py-1 pr-3 font-mono text-ink-secondary">{d}</td>
                    {DAILY_FEATURE_ORDER.map(f => {
                      const v = feats[f] ?? 0;
                      return (
                        <td key={f} className={`py-1 pr-3 text-right tabular-nums ${v > 0 ? DAILY_FEATURE_META[f].color : "text-ink-muted opacity-40"}`}>
                          {v > 0 ? v : "·"}
                        </td>
                      );
                    })}
                    <td className="py-1 pr-3 text-right tabular-nums font-semibold text-ink-primary">
                      {total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Per-agent panel */}
      <Panel
        title={`Per-agent 明细 · ${agents.data?.count ?? 0} agents`}
        action={
          <span className="text-[10px] text-ink-muted">
            built-in (Deep Research / NotebookLM / A2A) + 自建
          </span>
        }
      >
        {!agents.data ? <EmptyState title="加载中…" /> :
         agents.data.agents.length === 0 ? <EmptyState title="没有 agent" hint="没有 built-in 使用记录,也无自建 agent" /> : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-muted border-b border-border-subtle/40">
                <th className="py-1 pr-3 font-normal">Agent</th>
                <th className="py-1 pr-3 font-normal">类型</th>
                <th className="py-1 pr-3 font-normal text-right">总调用</th>
                <th className="py-1 pr-3 font-normal text-right">unique 用户</th>
                <th className="py-1 pr-3 font-normal">最活跃</th>
                <th className="py-1 pr-3 font-normal">最近</th>
              </tr>
            </thead>
            <tbody>
              {(agents.data.agents as AgentDirectoryRow[])
                .slice() // don't mutate query cache
                .sort((a, b) => b.total - a.total)
                .map(a => (
                <tr key={a.agent_id} className="border-b border-border-subtle/20 hover:bg-subtle/30">
                  <td className="py-1 pr-3">
                    <Link to={`/agent/${encodeURIComponent(a.agent_id)}`}
                          className="text-info hover:underline">{a.agent_name}</Link>
                    <span className="ml-1.5 text-[10px] text-ink-muted font-mono">{a.agent_id}</span>
                  </td>
                  <td className="py-1 pr-3">
                    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border ${
                      a.agent_type === "built-in"
                        ? "bg-info/10 text-info border-info/20"
                        : "bg-gyellow/10 text-gyellow border-gyellow/20"
                    }`}>{a.agent_type}</span>
                    {a.signal_kind === "page_opens" && (
                      <span className="ml-1 text-[9px] text-ink-muted" title="计的是 UI 打开次数,不是真实调用">📖 opens</span>
                    )}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums font-semibold">{a.total}</td>
                  <td className="py-1 pr-3 text-right tabular-nums text-ink-secondary">{a.unique_users}</td>
                  <td className="py-1 pr-3 font-mono text-ink-muted">
                    {a.top_user_email ? (
                      <span title={`共 ${a.top_user_value} 次`}>{a.top_user_email}</span>
                    ) : "—"}
                  </td>
                  <td className="py-1 pr-3 font-mono text-ink-muted">{fmtTs(a.last_activity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title={`谁查了什么 · 汇总 ${origin ? `· ${origin}` : ""}`}
        action={
          <button
            onClick={() => downloadCSV(summary.data?.rows, `data-access-summary-${new Date().toISOString().slice(0,10)}.csv`)}
            disabled={!summary.data?.rows?.length}
            className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary disabled:opacity-40"
            title="Download CSV of current rows (respects your origin/engine/range filters)"
          >
            ⬇ Download CSV
          </button>
        }>
        {!summary.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={summary.data.rows} cols={summaryCols} filterKeys={["actor_email", "engine_display_name", "origin"]} />
        )}
      </Panel>

      <Panel title={`逐笔时间线 ${origin ? `· ${origin}` : ""}`} action={
        <button
          onClick={() => setShowTimeline(!showTimeline)}
          className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary"
        >
          {showTimeline ? "收起" : `展开（${timeline.data?.count ?? "—"} 行）`}
        </button>
      }>
        {!showTimeline ? (
          <div className="text-xs text-ink-muted py-2">展开查看每一笔 Search / StreamAssist / CompletionService 调用</div>
        ) : !timeline.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={timeline.data.rows} cols={timelineCols} filterKeys={["actor_email", "action", "engine_display_name", "origin"]} dense />
        )}
      </Panel>
    </div>
  );
}
