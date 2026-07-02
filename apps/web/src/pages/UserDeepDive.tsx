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
// User picker (landing) — searchable, sortable, filterable directory
// ============================================================
type SortKey = "last" | "chat" | "dr" | "nb" | "agents";
const SORT_LABELS: Record<SortKey, string> = {
  last:   "最近活动",
  chat:   "Chat",
  dr:     "Deep Research",
  nb:     "NotebookLM",
  agents: "Custom agent 访问",
};
const SORT_FNS: Record<SortKey, (u: import("../api").UserListEntry) => number> = {
  last:   u => u.last_access ? new Date(u.last_access).getTime() : 0,
  chat:   u => u.chat_turns,
  dr:     u => u.deep_research_calls,
  nb:     u => u.notebooklm_ops,
  agents: u => u.custom_agent_visits,
};

const ORIGIN_FILTERS: Array<{ key: "ALL" | "HUMAN" | "SIMULATED" | "AUTOMATION"; label: string; cls: string }> = [
  { key: "ALL",        label: "全部",   cls: "" },
  { key: "HUMAN",      label: "真人",   cls: "text-ggreen" },
  { key: "SIMULATED",  label: "模拟",   cls: "text-info" },
  { key: "AUTOMATION", label: "自动",   cls: "text-warn" },
];

function FeaturePill({ icon, value, color }: { icon: string; value: number; color: string }) {
  if (value === 0) return <span className="text-ink-muted opacity-30 tabular-nums w-10 text-right text-[10px]">·</span>;
  return (
    <span className={`tabular-nums text-[11px] font-semibold ${color} w-10 text-right`} title={`${icon} ${value}`}>
      {value}
    </span>
  );
}

function shortenEmail(email: string): string {
  if (email.length <= 38) return email;
  return email.slice(0, 28) + "…" + email.slice(-7);
}

function relTs(ts: string | null): string {
  if (!ts) return "—";
  const now = Date.now();
  const t = new Date(ts).getTime();
  const diffMin = Math.floor((now - t) / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}m`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 30) return `${diffD}d`;
  return new Date(ts).toISOString().slice(0, 10);
}

function Picker() {
  const navigate = useNavigate();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("last");
  const [originFilter, setOriginFilter] = useState<"ALL" | "HUMAN" | "SIMULATED" | "AUTOMATION">("ALL");

  if (!users.data) return <EmptyState title="加载用户列表…" />;

  const filtered = users.data.users
    .filter(u => originFilter === "ALL" || u.origin === originFilter)
    .filter(u => !search || u.actor_email.toLowerCase().includes(search.toLowerCase()) || (u.persona ?? "").toLowerCase().includes(search.toLowerCase()));
  const sorted = [...filtered].sort((a, b) => SORT_FNS[sortBy](b) - SORT_FNS[sortBy](a));

  return (
    <div className="space-y-4 max-w-[1200px]">
      <Panel title={`员工目录 · ${sorted.length} / ${users.data.count}`}>
        {/* Controls bar */}
        <div className="flex flex-wrap items-center gap-3 mb-3 pb-3 border-b border-border-subtle/40">
          <input
            type="text"
            placeholder="🔍 搜索 email / persona…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 min-w-[180px] h-8 px-3 rounded-md bg-subtle/60 border border-border-subtle text-xs text-ink-primary placeholder:text-ink-muted focus:outline-none focus:border-info/60"
          />
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-ink-muted mr-1">排序:</span>
            {(Object.keys(SORT_LABELS) as SortKey[]).map(k => (
              <button
                key={k}
                onClick={() => setSortBy(k)}
                className={`h-7 px-2.5 rounded ${sortBy === k ? "bg-info/15 text-info border border-info/30" : "text-ink-secondary hover:text-ink-primary"}`}
              >
                {SORT_LABELS[k]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[11px] ml-auto">
            <span className="text-ink-muted mr-1">origin:</span>
            {ORIGIN_FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setOriginFilter(f.key)}
                className={`h-7 px-2.5 rounded ${originFilter === f.key ? "bg-subtle border border-border-subtle" : "text-ink-muted hover:text-ink-secondary"} ${originFilter === f.key ? f.cls : ""}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Header row */}
        <div className="flex items-center gap-3 px-3 py-1.5 text-[10px] uppercase tracking-wide text-ink-muted border-b border-border-subtle/40">
          <div className="flex-1 min-w-0">用户</div>
          <div className="w-20 shrink-0">Persona</div>
          <div className="hidden lg:flex items-center gap-1 shrink-0">
            <span className="w-10 text-right" title="Chat">💬</span>
            <span className="w-10 text-right" title="Deep Research">🔬</span>
            <span className="w-10 text-right" title="NotebookLM">📓</span>
            <span className="w-10 text-right" title="Custom agent visits">🧩</span>
            <span className="w-10 text-right" title="REST Search">🔎</span>
            <span className="w-10 text-right" title="Files">📎</span>
          </div>
          <div className="w-14 text-right shrink-0">最近</div>
        </div>

        {/* User rows */}
        {sorted.length === 0 ? (
          <EmptyState title="没匹配项" hint="改改 search 或 filter" />
        ) : (
          <div>
            {sorted.map(u => (
              <button
                key={u.actor_email}
                onClick={() => navigate(`/user/${encodeURIComponent(u.actor_email)}`)}
                className="w-full flex items-center gap-3 px-3 py-2 text-xs text-left border-b border-border-subtle/20 hover:bg-info-bg/8 hover:border-info/30 transition-colors group"
              >
                {/* Email + origin */}
                <div className="flex-1 min-w-0 flex items-center gap-2">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                    u.origin === "HUMAN" ? "bg-ggreen" :
                    u.origin === "SIMULATED" ? "bg-info" :
                    u.origin === "AUTOMATION" ? "bg-warn" : "bg-ink-muted"
                  }`} />
                  <span className="font-mono text-ink-primary group-hover:text-info truncate" title={u.actor_email}>
                    {shortenEmail(u.actor_email)}
                  </span>
                  {u.engines_touched > 1 && (
                    <span className="text-[9px] text-ink-muted ml-1 shrink-0">×{u.engines_touched} eng</span>
                  )}
                </div>

                {/* Persona tag */}
                <div className="w-20 shrink-0">
                  {u.persona ? (
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium border ${PERSONA_TAG[u.persona] ?? PERSONA_TAG.LURKER}`}>
                      {u.persona.replace("_", " ")}
                    </span>
                  ) : <span className="text-ink-muted">—</span>}
                </div>

                {/* Feature usage pills (hidden on small) */}
                <div className="hidden lg:flex items-center gap-1 shrink-0">
                  <FeaturePill icon="💬" value={u.chat_turns} color="text-ggreen" />
                  <FeaturePill icon="🔬" value={u.deep_research_calls} color="text-info" />
                  <FeaturePill icon="📓" value={u.notebooklm_ops} color="text-gblue" />
                  <FeaturePill icon="🧩" value={u.custom_agent_visits} color="text-ggreen" />
                  <FeaturePill icon="🔎" value={u.programmatic_searches} color="text-gblue" />
                  <FeaturePill icon="📎" value={u.session_files} color="text-ink-secondary" />
                </div>

                {/* Last seen */}
                <div className="w-14 text-right shrink-0 text-[10px] text-ink-muted font-mono">
                  {relTs(u.last_access)}
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Footer hint */}
        <div className="text-[10px] text-ink-muted mt-3 px-1">
          点击进入单用户全部活动详情 · 每个数字可继续 drill down 看具体哪几次
        </div>
      </Panel>
    </div>
  );
}

// ============================================================
// Compact metric block: big number + label + optional sub-line
// Click → expand drill-down panel below.
// Two drill modes: plain (timestamps only) or "prompts" (with reverse-attributed prompt text).
// ============================================================
type DrillPlain = { kind: "plain"; rows: Array<{ timestamp: string; primary: string; secondary?: string }> };
type DrillPrompts = {
  kind: "prompts";
  rows: Array<{ timestamp: string; primary: string; prompt: string | null; delta_sec?: number | null }>;
};
type DrillData = DrillPlain | DrillPrompts;

function Metric({ value, label, sub, accent, icon, drill, open, onToggle }: {
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
        className={`flex items-baseline gap-3 w-full text-left ${clickable ? "hover:opacity-90 cursor-pointer" : "cursor-default"}`}
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
            <div className="text-[11px] text-ink-muted py-1">最近事件里没匹配项（可能已过 retention window）</div>
          ) : drill.kind === "plain" ? (
            drill.rows.map((r, i) => (
              <div key={i} className="text-[11px] flex items-baseline gap-2">
                <span className="text-ink-muted font-mono shrink-0">{fmtTs(r.timestamp)}</span>
                <span className="text-ink-secondary font-mono">{r.primary}</span>
                {r.secondary && <span className="text-ink-muted">{r.secondary}</span>}
              </div>
            ))
          ) : (
            drill.rows.map((r, i) => (
              <div key={i} className="text-[11px]">
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

// Horizontal bar — one row, label left, count right, bar in between
// Click to expand and show drill-down rows
function Bar({ label, value, max, color, hint, sublabel, drillRows, open, onToggle }: {
  label: string;
  value: number;
  max: number;
  color: string;
  hint?: string;
  sublabel?: string;
  drillRows?: string[];
  open?: boolean;
  onToggle?: () => void;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  const clickable = !!onToggle && !!drillRows;
  return (
    <div>
      <button
        type="button"
        onClick={clickable ? onToggle : undefined}
        disabled={!clickable}
        className={`w-full text-left ${clickable ? "hover:bg-subtle/40 rounded-sm transition-colors" : ""}`}
      >
        <div className="flex items-center gap-3 text-xs">
          <div className="w-32 shrink-0">
            <div className="text-ink-primary font-medium truncate" title={label}>
              {clickable && <span className="text-ink-muted mr-1">{open ? "▾" : "▸"}</span>}
              {label}
            </div>
            {sublabel && <div className="text-[10px] text-ink-muted truncate">{sublabel}</div>}
          </div>
          <div className="flex-1 h-5 rounded-sm bg-subtle relative overflow-hidden">
            <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
          </div>
          <div className="w-14 text-right tabular-nums font-semibold text-ink-primary shrink-0">{value}</div>
          {hint && <div className="w-20 text-[10px] text-ink-muted shrink-0 truncate" title={hint}>{hint}</div>}
        </div>
      </button>
      {clickable && open && drillRows && (
        <div className="mt-1.5 ml-32 max-h-[200px] overflow-y-auto border-l-2 border-info/30 pl-3 space-y-0.5">
          {drillRows.length === 0 ? (
            <div className="text-[10px] text-ink-muted py-1">最近 200 条事件里没有匹配项</div>
          ) : drillRows.map((ts, i) => (
            <div key={i} className="text-[10px] text-ink-muted font-mono">{fmtTs(ts)}</div>
          ))}
        </div>
      )}
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

  // Track which metric/bar is currently expanded for drill-down
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const [openBar, setOpenBar] = useState<string | null>(null);

  if (!emailParam) return <Picker />;
  if (dive.isLoading) return <EmptyState title="加载中…" />;
  if (!dive.data) return <EmptyState title="该用户没有任何活动记录" hint={emailParam} />;

  const d: UserData = dive.data;
  const persona = d.persona[0];
  const navSum = d.agentspace_summary[0];
  const builder = d.builder[0];

  // Drill-down rows: prefer per-feature arrays from backend (no autocomplete-noise truncation).
  // Fall back to filtering data_access_events for Search/Files (no dedicated endpoint for those).
  const mapEvents = (rows: Array<{ timestamp: string; action: string; full_method: string }>): DrillData =>
    ({ kind: "plain", rows: rows.map(e => ({ timestamp: e.timestamp, primary: e.action, secondary: e.full_method.split(".").slice(-2, -1)[0] })) });

  const filterAuditByPattern = (pattern: RegExp): DrillData => ({
    kind: "plain",
    rows: d.data_access_events
      .filter(e => pattern.test(e.full_method))
      .map(e => ({ timestamp: e.timestamp, primary: e.action, secondary: e.full_method.split(".").slice(-2, -1)[0] })),
  });

  // Deep Research: use reverse-attributed prompts (heuristic ±60s window)
  const drillDR: DrillData = {
    kind: "prompts",
    rows: (d.dr_prompts ?? []).map(r => ({
      timestamp: r.dr_ts,
      primary: r.dr_action,
      prompt: r.attributed_prompt,
      delta_sec: r.attribution_delta_sec,
    })),
  };

  const drillChat = mapEvents(d.chat_events ?? []);
  const drillNB   = mapEvents(d.notebooklm_events ?? []);
  const drillA2A  = mapEvents(d.a2a_events ?? []);
  const drillSearch = filterAuditByPattern(/SearchService\.Search$/);
  const drillFiles  = filterAuditByPattern(/(ListSessionFileMetadata|DownloadSessionFile)$/);

  // Navigation drill: filter agentspace_events by page_type or agent_id
  const navEventsBy = (pageType: string, agentId?: string) =>
    (d.agentspace_events ?? [])
      .filter(e => e.page_type === pageType && (!agentId || e.agent_id === agentId))
      .map(e => e.timestamp);

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
  const navItems: Array<{ key: string; label: string; value: number; sublabel?: string; color: string; hint?: string; drillRows: string[] }> = [];
  if (navSum) {
    if (navSum.custom_agent_visits > 0) {
      // Break out per-custom-agent if we have the detail
      d.agentspace_detail
        .filter(x => x.page_type === "agent")
        .forEach(x => navItems.push({
          key: `agent:${x.agent_id ?? x.agent_name ?? "?"}`,
          label: x.agent_name ?? x.agent_id ?? "?",
          value: x.visits,
          sublabel: "custom agent",
          color: "bg-ggreen/70",
          hint: fmtTs(x.last_visit) as unknown as string,
          drillRows: navEventsBy("agent", x.agent_id ?? undefined),
        }));
    }
    if (navSum.deep_research_visits > 0) navItems.push({
      key: "page:deep-research",
      label: "Deep Research", value: navSum.deep_research_visits, sublabel: "入口页", color: "bg-info/70",
      drillRows: navEventsBy("deep-research"),
    });
    if (navSum.notebooklm_visits > 0) navItems.push({
      key: "page:notebook-lm",
      label: "NotebookLM", value: navSum.notebooklm_visits, sublabel: "入口页", color: "bg-gblue/70",
      drillRows: navEventsBy("notebook-lm"),
    });
    if (navSum.gallery_visits > 0) navItems.push({
      key: "page:gallery",
      label: "Agent Gallery", value: navSum.gallery_visits, sublabel: "浏览", color: "bg-ink-secondary/40",
      drillRows: navEventsBy("agent_gallery"),
    });
    if (navSum.home_visits > 0) navItems.push({
      key: "page:home",
      label: "Home", value: navSum.home_visits, sublabel: "登录页", color: "bg-ink-muted/40",
      drillRows: navEventsBy("home"),
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
              sub={<>StreamAssist · 跨 {enginesTouched} 个 engine</>}
              drill={drillChat} open={openMetric === "chat"} onToggle={() => setOpenMetric(openMetric === "chat" ? null : "chat")} />
          )}
          {totalDR > 0 && (
            <Metric icon="🔬" value={totalDR} label="Deep Research" accent="text-info"
              sub={<>AsyncAssist + Read · <span className="text-warn">prompt/response 不可见</span></>}
              drill={drillDR} open={openMetric === "dr"} onToggle={() => setOpenMetric(openMetric === "dr" ? null : "dr")} />
          )}
          {totalNB > 0 && (
            <Metric icon="📓" value={totalNB} label="NotebookLM ops" accent="text-gblue"
              sub={<>{nbNotebook} 生命周期 · {nbContent} 内容 · {nbAudio} 音频</>}
              drill={drillNB} open={openMetric === "nb"} onToggle={() => setOpenMetric(openMetric === "nb" ? null : "nb")} />
          )}
          {totalA2A > 0 && (
            <Metric icon="🔗" value={totalA2A} label="A2A 调用" accent="text-ggreen"
              sub="marketplace + custom agent 通过 A2A 协议"
              drill={drillA2A} open={openMetric === "a2a"} onToggle={() => setOpenMetric(openMetric === "a2a" ? null : "a2a")} />
          )}
          {totalSearch > 0 && (
            <Metric icon="🔎" value={totalSearch} label="REST Search" accent="text-gblue"
              sub="SearchService.Search (程序化)"
              drill={drillSearch} open={openMetric === "search"} onToggle={() => setOpenMetric(openMetric === "search" ? null : "search")} />
          )}
          {totalFiles > 0 && (
            <Metric icon="📎" value={totalFiles} label="文件操作" accent="text-ink-secondary"
              sub="List + Download SessionFile"
              drill={drillFiles} open={openMetric === "files"} onToggle={() => setOpenMetric(openMetric === "files" ? null : "files")} />
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
            {navItems.map((item) => (
              <Bar
                key={item.key}
                label={item.label}
                value={item.value}
                max={navMax}
                color={item.color}
                hint={item.hint}
                sublabel={item.sublabel}
                drillRows={item.drillRows}
                open={openBar === item.key}
                onToggle={() => setOpenBar(openBar === item.key ? null : item.key)}
              />
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
