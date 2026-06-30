import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, UserDeepDive as UserData } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  SIMULATED:  "bg-info/10 text-info border-info/20",
  AUTOMATION: "bg-warn/10 text-warn border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

const PERSONA_TAG: Record<string, string> = {
  POWER_USER:      "bg-info/15 text-info border-info/30",
  ACTIVE_CONSUMER: "bg-ggreen/15 text-ggreen border-ggreen/30",
  BUILDER:         "bg-gred/15 text-gred border-gred/30",
  TRIAL:           "bg-gyellow/15 text-gyellow border-gyellow/30",
  EXPLORER:        "bg-gblue/15 text-gblue border-gblue/30",
  LURKER:          "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
  AUTOMATION:      "bg-warn/15 text-warn border-warn/30",
  SIMULATED:       "bg-info/15 text-info border-info/30",
};

// ============================================================
// User picker (landing)
// ============================================================
function Picker() {
  const navigate = useNavigate();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  if (!users.data) return <EmptyState title="加载用户列表…" />;
  return (
    <div className="space-y-4">
      <Panel title="选个用户深入看看">
        <div className="text-xs text-ink-muted mb-3">
          单用户全部活动一屏可见：persona · 各种 special agent · NotebookLM 明细 · custom agent 访问 · 对话 · 完整 audit。
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {users.data.users.map((u) => (
            <button
              key={u.actor_email}
              onClick={() => navigate(`/user/${encodeURIComponent(u.actor_email)}`)}
              className="text-left px-3 py-2.5 rounded-lg border border-border-subtle bg-subtle hover:border-info/50 hover:bg-info-bg/10 transition-colors group"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="font-mono text-xs text-ink-primary truncate group-hover:text-info">
                  {u.actor_email}
                </div>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[u.origin ?? "UNKNOWN"]} ml-2 shrink-0`}>
                  {u.origin ?? "—"}
                </span>
              </div>
              <div className="flex gap-3 text-[11px] text-ink-muted">
                <span>chat <b className="text-ink-secondary">{u.chat_turns}</b></span>
                {u.deep_research_calls > 0 && <span>DR <b className="text-info">{u.deep_research_calls}</b></span>}
                {u.notebooklm_ops > 0 && <span>NB <b className="text-gblue">{u.notebooklm_ops}</b></span>}
                <span className="text-ink-muted ml-auto">{u.last_access ? new Date(u.last_access).toISOString().slice(5, 16).replace("T", " ") : "—"}</span>
              </div>
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}

// ============================================================
// Compact metric block: big number + label + optional sub-line
// ============================================================
function Metric({ value, label, sub, accent, icon }: {
  value: number | string;
  label: string;
  sub?: React.ReactNode;
  accent: string;
  icon?: string;
}) {
  return (
    <div className="flex items-baseline gap-3">
      {icon && <span className="text-xl shrink-0">{icon}</span>}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className={`text-3xl font-semibold tabular-nums ${accent}`}>{value}</span>
          <span className="text-xs text-ink-secondary font-medium uppercase tracking-wide">{label}</span>
        </div>
        {sub && <div className="text-[11px] text-ink-muted mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

// Horizontal bar — one row, label left, count right, bar in between
function Bar({ label, value, max, color, hint, sublabel }: {
  label: string;
  value: number;
  max: number;
  color: string;
  hint?: string;
  sublabel?: string;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="group">
      <div className="flex items-center gap-3 text-xs">
        <div className="w-32 shrink-0">
          <div className="text-ink-primary font-medium truncate" title={label}>{label}</div>
          {sublabel && <div className="text-[10px] text-ink-muted truncate">{sublabel}</div>}
        </div>
        <div className="flex-1 h-5 rounded-sm bg-subtle relative overflow-hidden">
          <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <div className="w-14 text-right tabular-nums font-semibold text-ink-primary shrink-0">{value}</div>
        {hint && <div className="w-20 text-[10px] text-ink-muted shrink-0 truncate" title={hint}>{hint}</div>}
      </div>
    </div>
  );
}

// ============================================================
// Per-user detail view
// ============================================================
export default function UserDeepDive() {
  const { email: emailParam } = useParams<{ email: string }>();
  const navigate = useNavigate();
  const [auditOpen, setAuditOpen] = useState(false);

  const enabled = !!emailParam;
  const dive = useQuery({
    queryKey: ["user", emailParam],
    queryFn: () => api.user(emailParam!),
    enabled,
  });

  if (!emailParam) return <Picker />;
  if (dive.isLoading) return <EmptyState title="加载中…" />;
  if (!dive.data) return <EmptyState title="该用户没有任何活动记录" hint={emailParam} />;

  const d: UserData = dive.data;
  const persona = d.persona[0];
  const navSum = d.agentspace_summary[0];
  const builder = d.builder[0];

  // Aggregate totals
  const totalChat = d.data_access_summary.reduce((a, r) => a + r.chat_turns, 0);
  const totalDR   = d.data_access_summary.reduce((a, r) => a + r.deep_research_calls, 0);
  const nbNotebook = d.data_access_summary.reduce((a, r) => a + r.notebooklm_notebook_ops, 0);
  const nbContent  = d.data_access_summary.reduce((a, r) => a + r.notebooklm_content_ops, 0);
  const nbAudio    = d.data_access_summary.reduce((a, r) => a + r.notebooklm_audio_ops, 0);
  const totalNB   = nbNotebook + nbContent + nbAudio;
  const totalA2A  = d.data_access_summary.reduce((a, r) => a + r.a2a_invocations, 0);
  const totalSearch = d.data_access_summary.reduce((a, r) => a + r.programmatic_searches, 0);
  const totalFiles  = d.data_access_summary.reduce((a, r) => a + r.session_files, 0);
  const enginesTouched = d.data_access_summary.filter(r => r.engine_id).length;

  // Build agent-usage list for the bar chart (combine navigation + custom agent visits)
  const navItems: Array<{ label: string; value: number; sublabel?: string; color: string; hint?: string }> = [];
  if (navSum) {
    if (navSum.custom_agent_visits > 0) {
      // Break out per-custom-agent if we have the detail
      d.agentspace_detail
        .filter(x => x.page_type === "agent")
        .forEach(x => navItems.push({
          label: x.agent_name ?? x.agent_id ?? "?",
          value: x.visits,
          sublabel: "custom agent",
          color: "bg-ggreen/70",
          hint: fmtTs(x.last_visit) as unknown as string,
        }));
    }
    if (navSum.deep_research_visits > 0) navItems.push({
      label: "Deep Research", value: navSum.deep_research_visits, sublabel: "入口页", color: "bg-info/70"
    });
    if (navSum.notebooklm_visits > 0) navItems.push({
      label: "NotebookLM", value: navSum.notebooklm_visits, sublabel: "入口页", color: "bg-gblue/70"
    });
    if (navSum.gallery_visits > 0) navItems.push({
      label: "Agent Gallery", value: navSum.gallery_visits, sublabel: "浏览", color: "bg-ink-secondary/40"
    });
    if (navSum.home_visits > 0) navItems.push({
      label: "Home", value: navSum.home_visits, sublabel: "登录页", color: "bg-ink-muted/40"
    });
  }
  const navMax = Math.max(1, ...navItems.map(x => x.value));

  // "Things they DIDN'T use" — useful negative signal
  const unused: string[] = [];
  if (totalDR === 0) unused.push("Deep Research");
  if (totalNB === 0) unused.push("NotebookLM");
  if (totalA2A === 0) unused.push("A2A");
  if (totalSearch === 0) unused.push("REST Search");
  if (totalFiles === 0) unused.push("文件上传/下载");

  const hasBuilderActivity = builder && (
    builder.agents_created || builder.engines_created || builder.datastores_created ||
    builder.agents_deleted || builder.engines_deleted || builder.datastores_deleted ||
    builder.update_actions
  );

  return (
    <div className="space-y-4 max-w-[1200px]">
      {/* Hero */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="font-mono text-base text-ink-primary truncate">{d.actor_email}</div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {persona && (
              <>
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${ORIGIN_TAG[persona.origin ?? "UNKNOWN"]}`}>
                  {persona.origin}
                </span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${PERSONA_TAG[persona.persona] ?? PERSONA_TAG.LURKER}`}>
                  {persona.persona}
                </span>
                <span className="text-[11px] text-ink-muted">
                  · last seen {fmtTs(persona.last_seen)}
                  {enginesTouched > 0 && <> · {enginesTouched} engine{enginesTouched > 1 ? "s" : ""}</>}
                </span>
              </>
            )}
          </div>
        </div>
        <button
          onClick={() => navigate("/user")}
          className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary shrink-0"
        >
          ← 换用户
        </button>
      </div>

      {/* PRIMARY: what they actually USED. Big metrics, only non-zero rendered prominently. */}
      <Panel title="实际用了什么">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
          {totalChat > 0 && (
            <Metric icon="💬" value={totalChat} label="Chat turns" accent="text-ggreen"
              sub={<>StreamAssist · 跨 {enginesTouched} 个 engine</>} />
          )}
          {totalDR > 0 && (
            <Metric icon="🔬" value={totalDR} label="Deep Research" accent="text-info"
              sub={<>AsyncAssist + Read · <span className="text-warn">prompt/response 不可见</span></>} />
          )}
          {totalNB > 0 && (
            <Metric icon="📓" value={totalNB} label="NotebookLM ops" accent="text-gblue"
              sub={<>{nbNotebook} 生命周期 · {nbContent} 内容 · {nbAudio} 音频</>} />
          )}
          {totalA2A > 0 && (
            <Metric icon="🔗" value={totalA2A} label="A2A 调用" accent="text-ggreen"
              sub="marketplace + custom agent 通过 A2A 协议" />
          )}
          {totalSearch > 0 && (
            <Metric icon="🔎" value={totalSearch} label="REST Search" accent="text-gblue"
              sub="SearchService.Search (程序化)" />
          )}
          {totalFiles > 0 && (
            <Metric icon="📎" value={totalFiles} label="文件操作" accent="text-ink-secondary"
              sub="List + Download SessionFile" />
          )}
        </div>

        {totalChat === 0 && totalDR === 0 && totalNB === 0 && totalA2A === 0 && totalSearch === 0 && totalFiles === 0 && (
          <EmptyState title="该用户没有任何 data-access 调用" hint="只有 admin 操作或 navigation，没用过实际功能" />
        )}

        {unused.length > 0 && (totalChat + totalDR + totalNB + totalA2A + totalSearch + totalFiles > 0) && (
          <div className="mt-5 pt-4 border-t border-border-subtle/50">
            <div className="text-[11px] text-ink-muted">
              <span className="mr-2">💤 没用过：</span>
              {unused.map((u, i) => (
                <span key={i} className="inline-block mr-1.5 mb-1 px-1.5 py-0.5 rounded bg-subtle/60 text-ink-muted text-[10px]">{u}</span>
              ))}
            </div>
          </div>
        )}
      </Panel>

      {/* Agent gallery — visual bar chart */}
      {navItems.length > 0 && (
        <Panel title="探索过哪些 Agent / 页面"
          action={<span className="text-[10px] text-ink-muted">navigation events · 不一定每次都触发调用</span>}>
          <div className="space-y-2">
            {navItems.map((item, i) => (
              <Bar key={i} {...item} max={navMax} />
            ))}
          </div>
          {navSum && navSum.custom_agent_names && (
            <div className="mt-3 pt-3 border-t border-border-subtle/50 text-[11px]">
              <span className="text-ink-muted">访问过的 custom agent 名单：</span>{" "}
              <span className="font-mono text-ggreen">{navSum.custom_agent_names}</span>
            </div>
          )}
        </Panel>
      )}

      {/* Builder activity — only if they actually built something */}
      {hasBuilderActivity && (
        <Panel title="管理 / Builder 行为">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-4 text-sm">
            {(builder.agents_created > 0 || builder.agents_deleted > 0) && (
              <div>
                <div className="text-[11px] text-ink-muted uppercase tracking-wide mb-0.5">Agent</div>
                <div className="text-ink-primary"><span className="text-ggreen font-semibold">+{builder.agents_created}</span> / <span className="text-gred font-semibold">−{builder.agents_deleted}</span></div>
              </div>
            )}
            {(builder.engines_created > 0 || builder.engines_deleted > 0) && (
              <div>
                <div className="text-[11px] text-ink-muted uppercase tracking-wide mb-0.5">Engine</div>
                <div className="text-ink-primary"><span className="text-ggreen font-semibold">+{builder.engines_created}</span> / <span className="text-gred font-semibold">−{builder.engines_deleted}</span></div>
              </div>
            )}
            {(builder.datastores_created > 0 || builder.datastores_deleted > 0) && (
              <div>
                <div className="text-[11px] text-ink-muted uppercase tracking-wide mb-0.5">DataStore</div>
                <div className="text-ink-primary"><span className="text-ggreen font-semibold">+{builder.datastores_created}</span> / <span className="text-gred font-semibold">−{builder.datastores_deleted}</span></div>
              </div>
            )}
            {builder.update_actions > 0 && (
              <div>
                <div className="text-[11px] text-ink-muted uppercase tracking-wide mb-0.5">Update 操作</div>
                <div className="text-ink-primary font-semibold">{builder.update_actions}</div>
              </div>
            )}
          </div>
        </Panel>
      )}

      {/* Conversations — card feed */}
      {d.conversations.length > 0 && (
        <Panel title={`最近 ${d.conversations.length} 条对话`}>
          <div className="space-y-1.5 max-h-[440px] overflow-y-auto pr-1 -mr-1">
            {d.conversations.map((c, i) => (
              <div key={i} className="rounded-md border border-border-subtle/60 bg-subtle/40 hover:bg-subtle/70 transition-colors px-3 py-2 text-xs">
                <div className="flex items-center gap-2 mb-1 text-[10px]">
                  <span className="text-ink-muted font-mono">{fmtTs(c.timestamp)}</span>
                  {c.engine_display_name && (
                    <>
                      <span className="text-ink-muted">·</span>
                      <span className="text-ink-secondary truncate" title={c.engine_display_name}>{c.engine_display_name}</span>
                    </>
                  )}
                  {c.join_status === "no_response" && (
                    <span className="inline-block px-1.5 py-px rounded bg-warn/15 text-warn text-[9px] border border-warn/30 shrink-0">no response</span>
                  )}
                </div>
                <div className="text-ink-primary line-clamp-2 leading-snug">{c.prompt}</div>
                {c.response_text && (
                  <div className="text-ink-muted mt-1 line-clamp-2 pl-2.5 border-l-2 border-info/30 italic">
                    {c.response_text}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Audit timeline — collapsed by default */}
      {d.data_access_events.length > 0 && (
        <Panel
          title={`完整 audit 时间线`}
          action={
            <button
              onClick={() => setAuditOpen(!auditOpen)}
              className="h-7 px-3 rounded-md bg-subtle border border-border-subtle text-xs text-ink-secondary hover:text-ink-primary"
            >
              {auditOpen ? "收起" : `展开 ${d.data_access_events.length} 行`}
            </button>
          }
        >
          {!auditOpen ? (
            <div className="text-xs text-ink-muted py-1">
              最近 {d.data_access_events.length} 个 audit 事件。展开看每一行的 service / method / engine。
            </div>
          ) : (
            <div className="max-h-[500px] overflow-y-auto -mx-2">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-surface z-10">
                  <tr className="text-left text-ink-muted border-b border-border-subtle/60">
                    <th className="py-1.5 px-2 font-normal">时间</th>
                    <th className="py-1.5 px-2 font-normal">Service</th>
                    <th className="py-1.5 px-2 font-normal">Action</th>
                    <th className="py-1.5 px-2 font-normal">Engine</th>
                  </tr>
                </thead>
                <tbody>
                  {d.data_access_events.map((e, i) => (
                    <tr key={i} className="border-b border-border-subtle/30 hover:bg-subtle/40">
                      <td className="py-1 px-2 font-mono text-ink-muted whitespace-nowrap">{fmtTs(e.timestamp)}</td>
                      <td className="py-1 px-2 text-ink-secondary truncate max-w-[160px]" title={e.service ?? ""}>{e.service ?? "—"}</td>
                      <td className="py-1 px-2 font-mono text-ink-primary">{e.action}</td>
                      <td className="py-1 px-2 text-ink-muted truncate max-w-[200px]" title={e.engine_id_raw ?? ""}>{e.engine_id_raw ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
