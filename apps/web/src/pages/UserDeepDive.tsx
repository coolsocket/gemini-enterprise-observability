import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, UserDeepDive as UserData } from "../api";
import { Panel, EmptyState } from "../components/Card";
import DataTable, { Col, fmtTs } from "../components/DataTable";

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  SIMULATED:  "bg-info/10 text-info border-info/20",
  AUTOMATION: "bg-warn/10 text-warn border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

function KpiTile({ label, value, hint, accent }: { label: string; value: number | string; hint?: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${accent ?? "text-ink-primary"}`}>{value}</div>
      {hint && <div className="text-[10px] text-ink-muted mt-0.5">{hint}</div>}
    </div>
  );
}

export default function UserDeepDive() {
  const { email: emailParam } = useParams<{ email: string }>();
  const navigate = useNavigate();
  const [picker, setPicker] = useState("");

  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  const enabled = !!emailParam;
  const dive = useQuery({
    queryKey: ["user", emailParam],
    queryFn: () => api.user(emailParam!),
    enabled,
  });

  // No user selected → show picker only
  if (!emailParam) {
    return (
      <div className="space-y-4">
        <Panel title="选个用户深入看看">
          <div className="space-y-3">
            <div className="text-xs text-ink-muted">单用户全部活动一屏可见：persona / 各种特殊 agent 使用 / NotebookLM 操作 / 对话历史 / Builder 行为 / 完整 audit timeline。</div>
            {!users.data ? <EmptyState title="加载用户列表…" /> : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {users.data.users.map((u) => (
                  <button
                    key={u.actor_email}
                    onClick={() => navigate(`/user/${encodeURIComponent(u.actor_email)}`)}
                    className="text-left px-3 py-2 rounded-lg border border-border-subtle bg-subtle hover:border-info/40 hover:bg-info-bg/5 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-xs text-ink-primary truncate">{u.actor_email}</div>
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[u.origin ?? "UNKNOWN"]}`}>
                        {u.origin ?? "—"}
                      </span>
                    </div>
                    <div className="flex gap-3 text-[11px] text-ink-muted mt-1">
                      <span>chat <b className="text-ink-secondary">{u.chat_turns}</b></span>
                      <span>DR <b className="text-info">{u.deep_research_calls}</b></span>
                      <span>NB <b className="text-gblue">{u.notebooklm_ops}</b></span>
                      <span>total <b>{u.total_data_access}</b></span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Panel>
      </div>
    );
  }

  if (dive.isLoading) return <EmptyState title="加载中…" />;
  if (!dive.data) return <EmptyState title="该用户没有任何活动记录" hint={emailParam} />;

  const d: UserData = dive.data;
  const persona = d.persona[0];
  const navSum = d.agentspace_summary[0];
  const builder = d.builder[0];

  // Aggregate totals across engines for the KPI tiles
  const totalChat = d.data_access_summary.reduce((a, r) => a + r.chat_turns, 0);
  const totalDR   = d.data_access_summary.reduce((a, r) => a + r.deep_research_calls, 0);
  const totalNB   = d.data_access_summary.reduce((a, r) => a + r.notebooklm_notebook_ops + r.notebooklm_content_ops + r.notebooklm_audio_ops, 0);
  const totalA2A  = d.data_access_summary.reduce((a, r) => a + r.a2a_invocations, 0);
  const totalSearch = d.data_access_summary.reduce((a, r) => a + r.programmatic_searches, 0);
  const totalFiles  = d.data_access_summary.reduce((a, r) => a + r.session_files, 0);
  const totalAudit  = d.data_access_summary.reduce((a, r) => a + r.total_data_access, 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ink-primary font-mono">{d.actor_email}</h2>
          {persona && (
            <div className="flex items-center gap-2 mt-1">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${ORIGIN_TAG[persona.origin ?? "UNKNOWN"]}`}>
                {persona.origin}
              </span>
              <span className="text-xs text-ink-secondary">persona = <b>{persona.persona}</b></span>
              <span className="text-xs text-ink-muted">· last seen {fmtTs(persona.last_seen)}</span>
            </div>
          )}
        </div>
        <button
          onClick={() => navigate("/user")}
          className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary"
        >
          ← 换个用户
        </button>
      </div>

      {/* KPI grid */}
      <Panel title="活动总览（跨 engine 合计）">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
          <KpiTile label="Chat" value={totalChat} hint="StreamAssist turns" accent="text-ggreen" />
          <KpiTile label="Deep Research" value={totalDR} hint="AsyncAssist + Read" accent="text-info" />
          <KpiTile label="NotebookLM" value={totalNB} hint="notebook+content+audio" accent="text-gblue" />
          <KpiTile label="A2A" value={totalA2A} hint="agent-to-agent" accent="text-ggreen" />
          <KpiTile label="Search" value={totalSearch} accent="text-gblue" />
          <KpiTile label="文件操作" value={totalFiles} hint="List + Download" />
          <KpiTile label="Audit total" value={totalAudit} accent="text-ink-primary" />
        </div>
      </Panel>

      {/* NotebookLM breakdown if any */}
      {totalNB > 0 && (
        <Panel title="NotebookLM 操作明细">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <KpiTile
              label="Notebook 生命周期"
              value={d.data_access_summary.reduce((a, r) => a + r.notebooklm_notebook_ops, 0)}
              hint="NotebookService + AccountService"
              accent="text-gblue"
            />
            <KpiTile
              label="Content 操作"
              value={d.data_access_summary.reduce((a, r) => a + r.notebooklm_content_ops, 0)}
              hint="Sources + Notes + Artifacts"
              accent="text-info"
            />
            <KpiTile
              label="Audio Overview"
              value={d.data_access_summary.reduce((a, r) => a + r.notebooklm_audio_ops, 0)}
              hint="podcast generation"
              accent="text-ggreen"
            />
          </div>
        </Panel>
      )}

      {/* Special Agent navigation */}
      {navSum && navSum.total_navigation_events > 0 && (
        <Panel title="Special Agent 入口浏览（点开过哪些 agent）">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
            <KpiTile label="Home" value={navSum.home_visits} />
            <KpiTile label="Gallery" value={navSum.gallery_visits} />
            <KpiTile label="Deep Research" value={navSum.deep_research_visits} accent="text-info" />
            <KpiTile label="NotebookLM" value={navSum.notebooklm_visits} accent="text-gblue" />
            <KpiTile
              label="自建 agent 访问"
              value={navSum.custom_agent_visits}
              hint={`distinct = ${navSum.distinct_custom_agents}`}
              accent="text-ggreen"
            />
          </div>
          {navSum.custom_agent_names && (
            <div className="text-xs text-ink-secondary px-1">
              <span className="text-ink-muted">访问过的 custom agent：</span>{" "}
              <span className="font-mono text-ggreen">{navSum.custom_agent_names}</span>
            </div>
          )}
          {d.agentspace_detail.length > 0 && (
            <div className="mt-3">
              <DataTable
                rows={d.agentspace_detail}
                dense
                cols={[
                  { key: "page_type", label: "入口类型",
                    render: (r) => <span className="font-mono text-xs">{r.page_type}</span> },
                  { key: "agent_name", label: "Agent",
                    render: (r) => r.agent_name ?? <span className="text-ink-muted">—</span> },
                  { key: "agent_id", label: "Agent ID", mono: true,
                    render: (r) => <span className="text-xs text-ink-muted">{r.agent_id ?? "—"}</span> },
                  { key: "visits", label: "次数", num: true,
                    render: (r) => <span className="font-semibold">{r.visits}</span> },
                  { key: "last_visit", label: "最近", mono: true, render: (r) => fmtTs(r.last_visit) },
                ]}
              />
            </div>
          )}
        </Panel>
      )}

      {/* Builder activity */}
      {builder && (
        <Panel title="Builder 行为（管理操作）">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <KpiTile label="Agent c/d" value={`${builder.agents_created} / ${builder.agents_deleted}`} />
            <KpiTile label="Engine c/d" value={`${builder.engines_created} / ${builder.engines_deleted}`} />
            <KpiTile label="DataStore c/d" value={`${builder.datastores_created} / ${builder.datastores_deleted}`} />
            <KpiTile label="Update 操作" value={builder.update_actions} />
            <KpiTile label="Total" value={builder.total_admin_actions} accent="text-ink-primary" />
          </div>
        </Panel>
      )}

      {/* Recent conversations */}
      <Panel title={`最近 ${d.conversations.length} 条对话`}>
        {d.conversations.length === 0 ? (
          <EmptyState title="无对话记录" hint="该用户没产生过任何 chat 或者 prompt 没被 logging 抓到" />
        ) : (
          <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
            {d.conversations.map((c, i) => (
              <div key={i} className="rounded-md border border-border-subtle bg-surface px-3 py-2 text-xs">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-ink-muted font-mono">{fmtTs(c.timestamp)}</span>
                  <span className="text-ink-muted">·</span>
                  <span className="text-ink-secondary">{c.engine_display_name ?? "—"}</span>
                  {c.join_status === "no_response" && (
                    <span className="inline-block px-1.5 py-0.5 rounded bg-warn/10 text-warn text-[9px] border border-warn/20">no response</span>
                  )}
                </div>
                <div className="text-ink-primary line-clamp-2">{c.prompt}</div>
                {c.response_text && (
                  <div className="text-ink-secondary mt-1 line-clamp-2 pl-3 border-l border-info/40">
                    ↳ {c.response_text}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Data access full timeline */}
      <Panel title={`完整 audit 时间线 · 最近 ${d.data_access_events.length} 条`}>
        {d.data_access_events.length === 0 ? <EmptyState title="无审计事件" /> : (
          <DataTable
            rows={d.data_access_events}
            dense
            cols={[
              { key: "timestamp", label: "时间", mono: true, render: (r) => fmtTs(r.timestamp), width: "160px" },
              { key: "service", label: "Service",
                render: (r) => <span className="text-xs text-ink-secondary">{r.service ?? "—"}</span> },
              { key: "action", label: "Action",
                render: (r) => <span className="font-mono text-xs">{r.action}</span> },
              { key: "engine_id_raw", label: "Engine",
                render: (r) => <span className="text-xs text-ink-muted">{r.engine_id_raw ?? "—"}</span> },
              { key: "full_method", label: "Full method",
                render: (r) => <span className="font-mono text-[10px] text-ink-muted">{r.full_method}</span> },
            ]}
          />
        )}
      </Panel>
    </div>
  );
}
