import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, EngineRow, DataAccessSummaryRow, AgentUsageRow } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";
import { useRange } from "../timerange";

const ORIGIN_DOT: Record<string, string> = {
  HUMAN:      "bg-ggreen",
  SIMULATED:  "bg-info",
  AUTOMATION: "bg-warn",
  UNKNOWN:    "bg-ink-muted",
};

function EngineCard({ engine }: { engine: EngineRow }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const { range } = useRange();

  // Only fetch drill-down data when expanded (lazy)
  const users = useQuery({
    queryKey: ["engine-users", engine.engine_id, range],
    queryFn: () => api.view<DataAccessSummaryRow>("v_data_access_summary", null, engine.engine_id, range),
    enabled: expanded,
  });
  const agents = useQuery({
    queryKey: ["engine-agents", engine.engine_id, range],
    queryFn: () => api.view<AgentUsageRow>("v_agent_usage", null, engine.engine_id, range),
    enabled: expanded,
  });

  const maxTurns = users.data ? Math.max(1, ...users.data.rows.map(u => u.chat_turns)) : 1;

  return (
    <div className="rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4 hover:bg-subtle/30 transition-colors"
      >
        <div className="flex items-start gap-4">
          <span className="text-ink-muted text-xs mt-1 w-3">{expanded ? "▾" : "▸"}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-base font-semibold text-ink-primary">
                {engine.engine_display_name ?? engine.engine_id}
              </span>
              <span className="text-[10px] font-mono text-ink-muted truncate">
                {engine.engine_id}
              </span>
            </div>
            {/* Inline metrics */}
            <div className="flex items-center gap-6 mt-2">
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-semibold text-ggreen tabular-nums">{engine.unique_users}</span>
                <span className="text-[11px] text-ink-muted uppercase tracking-wide">users</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-semibold text-gblue tabular-nums">{engine.chat_turns}</span>
                <span className="text-[11px] text-ink-muted uppercase tracking-wide">chat turns</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-semibold text-info tabular-nums">{engine.sessions}</span>
                <span className="text-[11px] text-ink-muted uppercase tracking-wide">sessions</span>
              </div>
              <div className="flex items-baseline gap-1.5 ml-auto">
                <span className="text-lg font-medium text-ink-secondary tabular-nums">{engine.total_events}</span>
                <span className="text-[11px] text-ink-muted uppercase tracking-wide">events</span>
              </div>
            </div>
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border-subtle/60 p-4 bg-subtle/20 space-y-4">
          {/* Top users */}
          <div>
            <div className="text-[11px] uppercase tracking-wide text-ink-muted mb-2">用户分布</div>
            {!users.data ? (
              <div className="text-xs text-ink-muted">加载中…</div>
            ) : users.data.rows.length === 0 ? (
              <div className="text-xs text-ink-muted italic">无用户活动</div>
            ) : (
              <div className="space-y-1">
                {users.data.rows.slice(0, 10).map(u => {
                  const pct = (u.chat_turns / maxTurns) * 100;
                  return (
                    <button
                      key={u.actor_email}
                      onClick={(e) => { e.stopPropagation(); navigate(`/user/${encodeURIComponent(u.actor_email)}`); }}
                      className="w-full flex items-center gap-3 text-xs hover:bg-info-bg/8 rounded px-2 py-1 group"
                    >
                      <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${ORIGIN_DOT[u.origin ?? "UNKNOWN"]}`} />
                      <span className="font-mono text-ink-secondary group-hover:text-info truncate w-64 text-left">
                        {u.actor_email}
                      </span>
                      <div className="flex-1 h-1.5 rounded-full bg-subtle overflow-hidden">
                        <div className="h-full bg-gblue/60" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-ink-primary font-medium tabular-nums w-10 text-right">{u.chat_turns}</span>
                      <span className="text-[10px] text-ink-muted w-24 text-right">
                        {fmtTs(u.last_access)}
                      </span>
                    </button>
                  );
                })}
                {users.data.rows.length > 10 && (
                  <div className="text-[10px] text-ink-muted px-2 pt-1">
                    + {users.data.rows.length - 10} 更多…
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Related agents */}
          <div>
            <div className="text-[11px] uppercase tracking-wide text-ink-muted mb-2">
              关联的 sub-agents · <span className="text-ink-muted normal-case">(从 gen_ai.choice 抽取)</span>
            </div>
            {!agents.data ? (
              <div className="text-xs text-ink-muted">加载中…</div>
            ) : agents.data.rows.length === 0 ? (
              <div className="text-xs text-ink-muted italic">无 sub-agent 调用（v1alpha REST 才写 gen_ai.choice）</div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {agents.data.rows.map(a => (
                  <button
                    key={a.agent_id}
                    onClick={(e) => { e.stopPropagation(); navigate(`/agent/${encodeURIComponent(a.agent_id)}`); }}
                    className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md border border-border-subtle bg-surface text-xs hover:border-info/50 hover:bg-info-bg/10 transition-colors"
                  >
                    <span className="font-mono text-ink-primary">{a.agent_id}</span>
                    <span className="text-ink-muted text-[10px]">·</span>
                    <span className="text-info tabular-nums">{a.traces}</span>
                    <span className="text-[10px] text-ink-muted">traces</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Quick actions */}
          <div className="flex gap-2 pt-2 border-t border-border-subtle/40 text-[11px]">
            <button
              onClick={(e) => { e.stopPropagation(); navigate(`/data-access?engine=${engine.engine_id}`); }}
              className="text-ink-muted hover:text-info"
            >
              → 在 Data Access 页看
            </button>
            <span className="text-ink-muted">·</span>
            <button
              onClick={(e) => { e.stopPropagation(); navigate(`/conversations`); }}
              className="text-ink-muted hover:text-info"
            >
              → 看对话
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Engines() {
  const { range } = useRange();
  const q = useQuery({
    queryKey: ["v_engine_adoption", range],
    queryFn: () => api.view<EngineRow>("v_engine_adoption", null, null, range),
  });
  const meta = useQuery({ queryKey: ["engines-meta"], queryFn: () => api.engines() });

  const rows = q.data?.rows ?? [];
  const totalEvents = rows.reduce((a, r) => a + r.total_events, 0);
  const totalChat = rows.reduce((a, r) => a + r.chat_turns, 0);
  const totalUsers = rows.reduce((a, r) => a + r.unique_users, 0);
  const totalSessions = rows.reduce((a, r) => a + r.sessions, 0);

  // Engines with zero activity (registered but no chat events)
  const knownIds = new Set(rows.map(r => r.engine_id));
  const inactive = (meta.data?.engines ?? []).filter(e => !knownIds.has(e.id));

  return (
    <div className="space-y-4 max-w-[1100px]">
      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wide text-ink-muted">活跃 engines</div>
          <div className="text-2xl font-semibold text-ink-primary tabular-nums mt-0.5">{rows.length}</div>
          {inactive.length > 0 && (
            <div className="text-[10px] text-ink-muted">+ {inactive.length} 无活动</div>
          )}
        </div>
        <div className="rounded-lg border border-ggreen/30 bg-ggreen/5 px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wide text-ggreen/80">跨 engine 用户</div>
          <div className="text-2xl font-semibold text-ggreen tabular-nums mt-0.5">{totalUsers}</div>
          <div className="text-[10px] text-ink-muted">加总（可能重复）</div>
        </div>
        <div className="rounded-lg border border-gblue/30 bg-gblue/5 px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wide text-gblue/80">总 chat turns</div>
          <div className="text-2xl font-semibold text-gblue tabular-nums mt-0.5">{totalChat}</div>
          <div className="text-[10px] text-ink-muted">StreamAssist</div>
        </div>
        <div className="rounded-lg border border-info/30 bg-info/5 px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wide text-info/80">总 sessions / events</div>
          <div className="text-2xl font-semibold text-info tabular-nums mt-0.5">{totalSessions} / {totalEvents}</div>
        </div>
      </div>

      {/* Engine cards */}
      <Panel title="每个 engine 详情" action={<span className="text-[10px] text-ink-muted">点击展开看用户 + agent</span>}>
        {!q.data ? <EmptyState title="加载中…" /> :
         rows.length === 0 ? (
          <EmptyState title="暂无 engine 事件" hint="等待 user_activity 日志流入" />
        ) : (
          <div className="space-y-2">
            {rows.map(e => <EngineCard key={e.engine_id} engine={e} />)}
          </div>
        )}
      </Panel>

      {/* Inactive engines */}
      {inactive.length > 0 && (
        <Panel title={`已注册但无活动 · ${inactive.length}`}>
          <div className="text-xs text-ink-muted mb-2">
            engine 在 GE 后台创建了但没有产生任何 chat 事件（无用户使用过）
          </div>
          <div className="space-y-1">
            {inactive.map(e => (
              <div key={e.id} className="flex items-baseline gap-3 px-3 py-1.5 rounded text-xs bg-subtle/30">
                <span className="text-ink-primary">{e.name}</span>
                <span className="text-[10px] font-mono text-ink-muted">{e.id}</span>
                <span className="text-[10px] text-ink-muted ml-auto">{e.type ?? "—"}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
