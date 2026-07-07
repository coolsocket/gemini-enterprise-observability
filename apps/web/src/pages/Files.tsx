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
import { api, AgentspaceNavSummaryRow, AgentspaceNavRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
// NOTE: session-file and per-agent-usage panels were removed 2026-07-07
// — the underlying views were never defined. If those aggregations
// get built later, restore panels AND add the view definitions.
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";

const SIGNAL_TAG: Record<string, string> = {
  confirmed: "bg-ggreen/15 text-ggreen border-ggreen/30",
  likely:    "bg-gyellow/15 text-gyellow border-gyellow/30",
  unknown:   "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
};

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  SIMULATED:  "bg-info/10 text-info border-info/20",
  AUTOMATION: "bg-warn/10 text-warn border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

export default function Files() {
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const { range } = useRange();
  const navSum = useQuery({
    queryKey: ["v_agentspace_navigation_summary", origin, range],
    queryFn: () => api.view<AgentspaceNavSummaryRow>("v_agentspace_navigation_summary", origin, null, range),
  });
  const navDetail = useQuery({
    queryKey: ["v_agentspace_navigation", origin, engineId, range],
    queryFn: () => api.view<AgentspaceNavRow>("v_agentspace_navigation", origin, engineId, range),
  });

  const navSumCols: Col<AgentspaceNavSummaryRow>[] = [
    { key: "actor_email", label: "用户", mono: true },
    { key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ) },
    { key: "deep_research_visits", label: "Deep Research", num: true,
      render: (r) => <span className={r.deep_research_visits > 0 ? "text-info font-medium" : "text-ink-muted"}>{r.deep_research_visits}</span> },
    { key: "notebooklm_visits", label: "NotebookLM", num: true,
      render: (r) => <span className={r.notebooklm_visits > 0 ? "text-gblue font-medium" : "text-ink-muted"}>{r.notebooklm_visits}</span> },
    { key: "custom_agent_visits", label: "自建 agent", num: true,
      render: (r) => <span className={r.custom_agent_visits > 0 ? "text-ggreen font-medium" : "text-ink-muted"}>{r.custom_agent_visits}</span> },
    { key: "distinct_custom_agents", label: "Distinct", num: true,
      render: (r) => <span className="text-ink-secondary">{r.distinct_custom_agents}</span> },
    { key: "custom_agent_names", label: "Agent 列表",
      render: (r) => <span className="text-xs text-ink-muted">{r.custom_agent_names ?? "—"}</span> },
    { key: "gallery_visits", label: "Gallery 浏览", num: true,
      render: (r) => <span className="text-ink-muted">{r.gallery_visits}</span> },
    { key: "total_navigation_events", label: "总访问", num: true,
      render: (r) => <span className="font-semibold">{r.total_navigation_events}</span> },
    { key: "last_visit", label: "最近访问", mono: true, render: (r) => fmtTs(r.last_visit) },
  ];

  const navDetailCols: Col<AgentspaceNavRow>[] = [
    { key: "actor_email", label: "用户", mono: true },
    { key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ) },
    { key: "page_type", label: "入口类型",
      render: (r) => {
        const colorMap: Record<string, string> = {
          "deep-research": "text-info",
          "notebook-lm":   "text-gblue",
          "agent":         "text-ggreen",
          "agent_gallery": "text-ink-secondary",
          "home":          "text-ink-muted",
        };
        return <span className={`font-mono text-xs ${colorMap[r.page_type] ?? "text-ink-muted"}`}>{r.page_type}</span>;
      } },
    { key: "agent_name", label: "Agent 名",
      render: (r) => r.agent_name ? <span className="text-ink-primary">{r.agent_name}</span> : <span className="text-ink-muted">—</span> },
    { key: "agent_id", label: "Agent ID", mono: true,
      render: (r) => <span className="text-xs text-ink-muted">{r.agent_id ?? "—"}</span> },
    { key: "visits", label: "访问数", num: true,
      render: (r) => <span className="font-semibold">{r.visits}</span> },
    { key: "last_visit", label: "最近", mono: true, render: (r) => fmtTs(r.last_visit) },
  ];

  return (
    <div className="space-y-4">
      {/* Data limit banner */}
      <div className="rounded-xl border border-info/30 bg-info-bg/10 px-5 py-3 text-sm">
        <div className="text-ink-primary font-medium mb-1">📋 关于这两张表</div>
        <ul className="text-xs text-ink-secondary space-y-0.5 list-disc list-inside">
          <li><b>文件活动</b>：GE 不通过审计日志记录文件上传，但能拿到 <code className="bg-subtle px-1 rounded">ListSessionFileMetadata</code>（查看会话文件列表）+ <code className="bg-subtle px-1 rounded">DownloadSessionFile</code>（下载文件）两个间接信号。下载 ≥ 1 → 'confirmed'，list ≥ 3 → 'likely'</li>
          <li><b>Agent 调用</b>：从 <code className="bg-subtle px-1 rounded">gen_ai.choice</code> 表的 <code className="bg-subtle px-1 rounded">resource.labels.agent_id</code> 抽取。同一个 assistant 内可能路由到不同 sub-agent（如 deep_research、core_assistant）。<b>仅当用户用 REST/v1alpha 调用时才有 choice 日志</b>（v1main UI 不写）</li>
          <li>拿不到的：具体文件名、文件大小、上传时间。仅能拿到"该会话有文件交互"的元数据信号</li>
        </ul>
      </div>

      {/* NEW: Agentspace navigation — which special agent did users open? */}
      <Panel title={`Special Agent 入口浏览 · 汇总`}>
        <div className="text-xs text-ink-muted mb-2 px-1">
          💡 从 <code className="bg-subtle px-1 rounded text-[10px]">UserEventService.WriteUserEvent</code> 的 <code className="bg-subtle px-1 rounded text-[10px]">agentspaceinfo.agentspacepagetype</code> 抓的"用户打开 X agent 页面"事件。<b>这是导航不是调用</b>。Deep Research 实际调用看 Data Access 页的 <code className="bg-subtle px-1 rounded text-[10px]">deep_research_calls</code> 列；NotebookLM 实际操作如果走 <code className="bg-subtle px-1 rounded text-[10px]">notebooklm.v1alpha.*</code> 也会进 Data Access。
        </div>
        {!navSum.data ? <EmptyState title="加载中…" /> :
         navSum.data.rows.length === 0 ? (
          <EmptyState title="无入口访问记录" hint="该 origin 下没有用户访问过 home/agent_gallery/deep-research/notebook-lm/agent 页面" />
        ) : (
          <DataTable rows={navSum.data.rows} cols={navSumCols} filterKeys={["actor_email", "custom_agent_names"]} />
        )}
      </Panel>

      <Panel title={`Special Agent 入口浏览 · 逐条`}>
        {!navDetail.data ? <EmptyState title="加载中…" /> :
         navDetail.data.rows.length === 0 ? (
          <EmptyState title="无入口访问记录" hint="该 origin/engine 下没有 agentspace 入口事件" />
        ) : (
          <DataTable rows={navDetail.data.rows} cols={navDetailCols} filterKeys={["actor_email", "page_type", "agent_name", "agent_id"]} dense />
        )}
      </Panel>

    </div>
  );
}
