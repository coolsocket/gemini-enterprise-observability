import { useQuery } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api, AgentDeepDive as AgentData } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";

const TYPE_TAG: Record<string, string> = {
  "built-in": "bg-info/15 text-info border-info/30",
  "custom":   "bg-ggreen/15 text-ggreen border-ggreen/30",
};

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  SIMULATED:  "bg-info/10 text-info border-info/20",
  AUTOMATION: "bg-warn/10 text-warn border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

const AGENT_ICON: Record<string, string> = {
  deep_research: "🔬",
  notebooklm:    "📓",
  a2a_protocol:  "🔗",
};

function AgentDirectoryList() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["agents"], queryFn: () => api.agents() });
  if (!q.data) return <EmptyState title="加载 agent 目录…" />;
  if (q.data.agents.length === 0) {
    return <EmptyState title="还没发现任何 agent" hint="需要至少有 1 个用户用过 Deep Research / NotebookLM / 自建 agent" />;
  }
  // Largest first for the bar widths
  const maxTotal = Math.max(...q.data.agents.map(a => a.total));

  return (
    <div className="space-y-4 max-w-[1100px]">
      <Panel title={`已知 agent · ${q.data.count} 个`}>
        <div className="text-xs text-ink-muted mb-3">
          每行一个 agent — built-in 来自 audit log 的 API 调用统计；custom 来自 agentspace 入口点击（不一定每次都触发调用）。点击查看每个 agent 的用户和事件。
        </div>
        <div className="space-y-2.5">
          {q.data.agents.map(a => {
            const pct = (a.total / maxTotal) * 100;
            return (
              <button
                key={a.agent_id}
                onClick={() => navigate(`/agent/${encodeURIComponent(a.agent_id)}`)}
                className="w-full text-left rounded-lg border border-border-subtle bg-subtle/40 hover:border-info/40 hover:bg-info-bg/10 transition-colors p-3 group"
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl shrink-0">{AGENT_ICON[a.agent_id] ?? "🧩"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-semibold text-ink-primary group-hover:text-info">{a.agent_name}</span>
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${TYPE_TAG[a.agent_type]}`}>
                        {a.agent_type}
                      </span>
                      <span className="text-[10px] text-ink-muted font-mono">{a.agent_id}</span>
                    </div>
                    {/* Bar */}
                    <div className="flex items-center gap-2 mb-1">
                      <div className="flex-1 h-1.5 rounded-full bg-subtle overflow-hidden">
                        <div className="h-full bg-info/70 transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xl font-semibold text-ink-primary tabular-nums shrink-0 w-16 text-right">
                        {a.total}
                      </span>
                      <span className="text-[10px] text-ink-muted w-20 shrink-0">
                        {a.signal_kind === "api_calls" ? "API calls" : "page opens"}
                      </span>
                    </div>
                    <div className="text-[11px] text-ink-muted flex items-center gap-3 flex-wrap">
                      <span>{a.unique_users} unique user{a.unique_users > 1 ? "s" : ""}</span>
                      {a.top_user_email && (
                        <span>top: <span className="font-mono text-ink-secondary">{a.top_user_email}</span> ({a.top_user_value})</span>
                      )}
                      <span className="ml-auto">last: {a.last_activity ? fmtTs(a.last_activity) : "—"}</span>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}

function AgentDetail({ agentId }: { agentId: string }) {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["agent", agentId], queryFn: () => api.agent(agentId) });
  if (q.isLoading) return <EmptyState title="加载中…" />;
  if (!q.data) return <EmptyState title="没找到这个 agent" hint={agentId} />;
  const d: AgentData = q.data;
  const dir = d.directory;

  return (
    <div className="space-y-4 max-w-[1100px]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-3xl">{AGENT_ICON[agentId] ?? "🧩"}</span>
          <div className="min-w-0">
            <div className="text-base font-semibold text-ink-primary">{dir?.agent_name ?? agentId}</div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {dir && (
                <>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${TYPE_TAG[dir.agent_type]}`}>
                    {dir.agent_type}
                  </span>
                  <span className="text-[11px] text-ink-muted">
                    {dir.signal_kind === "api_calls" ? "API calls (from audit log)" : "page opens (from navigation events)"}
                  </span>
                </>
              )}
              <span className="text-[11px] text-ink-muted font-mono">{agentId}</span>
            </div>
          </div>
        </div>
        <button
          onClick={() => navigate("/agents")}
          className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary shrink-0"
        >
          ← agent 列表
        </button>
      </div>

      {/* KPIs */}
      {dir && (
        <Panel title="概况">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3 text-sm">
            <div>
              <div className="text-[11px] text-ink-muted uppercase tracking-wide">总{dir.signal_kind === "api_calls" ? "调用数" : "访问数"}</div>
              <div className="text-3xl font-semibold text-ink-primary tabular-nums mt-0.5">{dir.total}</div>
            </div>
            <div>
              <div className="text-[11px] text-ink-muted uppercase tracking-wide">独立用户</div>
              <div className="text-3xl font-semibold text-info tabular-nums mt-0.5">{dir.unique_users}</div>
            </div>
            <div>
              <div className="text-[11px] text-ink-muted uppercase tracking-wide">最重用户</div>
              <div className="text-sm font-mono text-ink-primary mt-1.5 truncate" title={dir.top_user_email ?? ""}>
                {dir.top_user_email ?? "—"}
              </div>
              <div className="text-[11px] text-ink-muted">{dir.top_user_value} 次</div>
            </div>
            <div>
              <div className="text-[11px] text-ink-muted uppercase tracking-wide">最近活动</div>
              <div className="text-sm font-mono text-ink-primary mt-1.5">{dir.last_activity ? fmtTs(dir.last_activity) : "—"}</div>
            </div>
          </div>
        </Panel>
      )}

      {/* Per-user breakdown */}
      <Panel title={`用过这个 agent 的用户 · ${d.users.length} 人`}>
        {d.users.length === 0 ? (
          <EmptyState title="无用户记录" />
        ) : (
          <div className="space-y-1.5">
            {d.users.map(u => {
              const maxCalls = Math.max(...d.users.map(x => x.calls));
              const pct = (u.calls / maxCalls) * 100;
              return (
                <button
                  key={u.actor_email}
                  onClick={() => navigate(`/user/${encodeURIComponent(u.actor_email)}`)}
                  className="w-full text-left p-2 rounded hover:bg-subtle/60 transition-colors group"
                >
                  <div className="flex items-center gap-3 text-xs">
                    <div className="w-64 shrink-0 flex items-center gap-2">
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[u.origin ?? "UNKNOWN"]} shrink-0`}>
                        {u.origin ?? "—"}
                      </span>
                      <span className="font-mono text-ink-primary group-hover:text-info truncate" title={u.actor_email}>
                        {u.actor_email}
                      </span>
                    </div>
                    <div className="flex-1 h-4 rounded-sm bg-subtle relative overflow-hidden">
                      <div className="h-full bg-info/60" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="w-12 text-right font-semibold tabular-nums">{u.calls}</div>
                    <div className="w-32 text-[10px] text-ink-muted text-right">{u.last_seen ? fmtTs(u.last_seen) : "—"}</div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Panel>

      {/* Reverse-attributed prompts — heuristic time-window */}
      {d.prompts && d.prompts.length > 0 && (
        <Panel
          title={`推断的 prompt · ${d.prompts.length} 条`}
          action={<span className="text-[10px] text-ink-muted">时间窗启发式 · 可能有误差</span>}
        >
          <div className="text-[11px] text-ink-muted mb-2">
            {agentId === "deep_research"
              ? "AsyncAssist 事件 ±60s 内的 StreamAssist prompt 视为该次 Deep Research 的原始提问。同一 prompt 会关联到 submit + poll 多个事件。"
              : "用户打开该 agent 后 5 分钟内的 StreamAssist prompt 视为对该 agent 的对话。"}
          </div>
          <div className="space-y-1.5 max-h-[400px] overflow-y-auto pr-1">
            {d.prompts.map((p, i) => (
              <div key={i} className="rounded-md border border-border-subtle/60 bg-subtle/30 px-3 py-2 text-xs">
                <div className="flex items-baseline gap-2 mb-1 text-[10px] text-ink-muted">
                  <span className="font-mono">{fmtTs(p.event_ts)}</span>
                  <span>·</span>
                  <span className="font-mono">{p.actor_email}</span>
                  {p.dr_action && (
                    <>
                      <span>·</span>
                      <span className="text-info">{p.dr_action}</span>
                    </>
                  )}
                  {p.attribution_delta_sec != null && (
                    <span className="ml-auto">±{Math.abs(p.attribution_delta_sec)}s</span>
                  )}
                  {p.elapsed_since_open_sec != null && (
                    <span className="ml-auto">agent 打开后 {p.elapsed_since_open_sec}s</span>
                  )}
                </div>
                <div className="text-ink-primary leading-snug">
                  <span className="text-info">"</span>{p.prompt}<span className="text-info">"</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Event timeline */}
      <Panel title={`最近 ${d.events.length} 个事件`}>
        {d.events.length === 0 ? (
          <EmptyState title="无事件" />
        ) : (
          <div className="max-h-[500px] overflow-y-auto -mx-2">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-surface z-10">
                <tr className="text-left text-ink-muted border-b border-border-subtle/60">
                  <th className="py-1.5 px-2 font-normal">时间</th>
                  <th className="py-1.5 px-2 font-normal">用户</th>
                  <th className="py-1.5 px-2 font-normal">动作</th>
                  <th className="py-1.5 px-2 font-normal">细节</th>
                </tr>
              </thead>
              <tbody>
                {d.events.map((e, i) => (
                  <tr key={i} className="border-b border-border-subtle/30 hover:bg-subtle/40">
                    <td className="py-1 px-2 font-mono text-ink-muted whitespace-nowrap">{fmtTs(e.timestamp)}</td>
                    <td className="py-1 px-2 font-mono text-ink-secondary truncate max-w-[260px]" title={e.actor_email}>{e.actor_email}</td>
                    <td className="py-1 px-2 font-mono text-ink-primary">{e.action}</td>
                    <td className="py-1 px-2 text-ink-muted truncate max-w-[260px]" title={e.full_method ?? e.engine_id_raw ?? ""}>
                      {e.full_method ?? e.engine_id_raw ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

export default function Agents() {
  const { agentId } = useParams<{ agentId: string }>();
  if (!agentId) return <AgentDirectoryList />;
  return <AgentDetail agentId={agentId} />;
}
