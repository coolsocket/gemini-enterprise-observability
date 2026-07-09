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
import { useState } from "react";
import { api, DataAccessRow, DataAccessSummaryRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  AUTOMATION: "bg-warn/10   text-warn   border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
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
      </div>

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
