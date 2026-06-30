import { useQuery } from "@tanstack/react-query";
import { api, PersonaRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";

const PERSONA_TAG: Record<string, string> = {
  POWER_USER:      "bg-gblue/15   text-gblue   border-gblue/30",
  ACTIVE_CONSUMER: "bg-ggreen/15  text-ggreen  border-ggreen/30",
  TRIAL:           "bg-gyellow/15 text-gyellow border-gyellow/30",
  BUILDER:         "bg-gred/15    text-gred    border-gred/30",
  EXPLORER:        "bg-info/15    text-info    border-info/30",
  LURKER:          "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
  AUTOMATION:      "bg-ink-secondary/10 text-ink-secondary border-ink-secondary/30",
};

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  AUTOMATION: "bg-warn/10   text-warn   border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

export default function Persona() {
  const { origin } = useOrigin();
  const q = useQuery({
    // v_user_persona doesn't have engine_id column, so don't filter by engineId
    queryKey: ["v_user_persona", origin],
    queryFn: () => api.view<PersonaRow>("v_user_persona", origin),
  });

  const cols: Col<PersonaRow>[] = [
    {
      key: "user", label: "用户", mono: true,
      render: (r) => <span className="text-ink-primary break-all">{r.user}</span>,
    },
    {
      key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ),
    },
    {
      key: "persona", label: "画像",
      render: (r) => (
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${PERSONA_TAG[r.persona] ?? PERSONA_TAG.LURKER}`}>
          {r.persona}
        </span>
      ),
    },
    { key: "chat_turns_total", label: "Chat", num: true,
      render: (r) => <span className={r.chat_turns_total > 0 ? "text-ggreen font-medium" : "text-ink-muted"}>{r.chat_turns_total}</span> },
    { key: "chat_turns_7d", label: "7d", num: true,
      render: (r) => <span className="text-ink-secondary">{r.chat_turns_7d}</span> },
    {
      key: "resources_created", label: "建过资源", num: true,
      render: (r) => (
        <span
          className={r.resources_created > 0 ? "text-gred font-medium" : "text-ink-muted"}
          title={`agents ${r.agents_created} · engines ${r.engines_created} · datastores ${r.datastores_created}`}
        >
          {r.resources_created}
          {r.resources_created > 0 && (
            <span className="text-ink-muted text-[10px] ml-1">
              ({r.agents_created}a / {r.engines_created}e / {r.datastores_created}d)
            </span>
          )}
        </span>
      ),
    },
    { key: "last_seen", label: "最近活动", mono: true, render: (r) => fmtTs(r.last_seen) },
  ];

  return (
    <div className="space-y-4">
      {/* Legend */}
      <div className="bg-surface border border-border-subtle rounded-xl px-5 py-3">
        <div className="text-[11px] uppercase tracking-wider text-ink-muted mb-2">画像分类规则</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.POWER_USER}`}>POWER_USER</span><span className="text-ink-muted">7d ≥20 turns & ≥3 sessions</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.ACTIVE_CONSUMER}`}>ACTIVE</span><span className="text-ink-muted">7d ≥5 turns</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.TRIAL}`}>TRIAL</span><span className="text-ink-muted">总 1-4 turns</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.BUILDER}`}>BUILDER</span><span className="text-ink-muted">建过任何资源</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.EXPLORER}`}>EXPLORER</span><span className="text-ink-muted">仅浏览未聊天</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.LURKER}`}>LURKER</span><span className="text-ink-muted">14 天静默</span></div>
          <div><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border mr-2 ${PERSONA_TAG.AUTOMATION}`}>AUTOMATION</span><span className="text-ink-muted">service account</span></div>
        </div>
      </div>

      <Panel title={`用户画像 ${origin ? `· 只看 ${origin}` : "· 全部"}`}>
        {!q.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={q.data.rows} cols={cols} filterKeys={["user", "persona", "origin"]} />
        )}
      </Panel>
    </div>
  );
}
