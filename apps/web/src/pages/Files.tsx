import { useQuery } from "@tanstack/react-query";
import { api, AgentUsageRow, SessionFileRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";

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
  const files  = useQuery({
    queryKey: ["v_session_files", origin, engineId],
    queryFn: () => api.view<SessionFileRow>("v_session_files", origin, engineId),
  });
  const agents = useQuery({
    queryKey: ["v_agent_usage", null, engineId],
    queryFn: () => api.view<AgentUsageRow>("v_agent_usage", null, engineId),
  });

  const fileCols: Col<SessionFileRow>[] = [
    { key: "actor_email", label: "用户", mono: true },
    { key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ) },
    { key: "engine_display_name", label: "Engine",
      render: (r) => <span className="text-xs">{r.engine_display_name ?? r.engine_id_raw}</span> },
    { key: "session_id", label: "Session ID", mono: true,
      render: (r) => <span className="text-xs text-ink-muted">{r.session_id.slice(0, 20)}…</span> },
    { key: "list_calls", label: "List 调用", num: true,
      render: (r) => <span className={r.list_calls > 5 ? "text-gblue font-medium" : "text-ink-secondary"}>{r.list_calls}</span> },
    { key: "download_calls", label: "Download", num: true,
      render: (r) => <span className={r.download_calls > 0 ? "text-ggreen font-medium" : "text-ink-muted"}>{r.download_calls}</span> },
    { key: "file_activity_signal", label: "文件活动信号",
      render: (r) => (
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${SIGNAL_TAG[r.file_activity_signal] ?? SIGNAL_TAG.unknown}`}>
          {r.file_activity_signal}
        </span>
      ) },
    { key: "last_op", label: "最近操作", mono: true, render: (r) => fmtTs(r.last_op) },
  ];

  const agentCols: Col<AgentUsageRow>[] = [
    { key: "agent_id", label: "Agent ID", mono: true,
      render: (r) => <span className="text-gblue font-medium">{r.agent_id}</span> },
    { key: "assistant_id", label: "Assistant", mono: true,
      render: (r) => <span className="text-ink-muted text-xs">{r.assistant_id}</span> },
    { key: "engine_display_name", label: "Engine",
      render: (r) => <span className="text-xs">{r.engine_display_name ?? r.engine_id_raw}</span> },
    { key: "traces", label: "对话数 (traces)", num: true,
      render: (r) => <span className="text-ink-primary font-semibold">{r.traces}</span> },
    { key: "chunks", label: "流式 chunks", num: true,
      render: (r) => <span className="text-ink-secondary">{r.chunks}</span> },
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

      <Panel title={`文件活动 · ${files.data?.count ?? 0} 个 session`}>
        {!files.data ? <EmptyState title="加载中…" /> :
         files.data.rows.length === 0 ? (
          <EmptyState title="无文件活动记录" hint="该 origin/engine 下没有 ListSessionFileMetadata 或 DownloadSessionFile 调用" />
        ) : (
          <DataTable rows={files.data.rows} cols={fileCols} filterKeys={["actor_email", "session_id"]} />
        )}
      </Panel>

      <Panel title={`Agent 调用统计 · ${agents.data?.count ?? 0} 个 agent`}>
        {!agents.data ? <EmptyState title="加载中…" /> :
         agents.data.rows.length === 0 ? (
          <EmptyState title="无 agent 调用数据" hint="需要通过 v1alpha REST API 调 chat 才会生成 gen_ai.choice 日志（GE 控制台 UI 不写）" />
        ) : (
          <DataTable rows={agents.data.rows} cols={agentCols} />
        )}
      </Panel>
    </div>
  );
}
