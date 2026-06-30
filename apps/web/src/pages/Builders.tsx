import { useQuery } from "@tanstack/react-query";
import { api, BuilderRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";

const ORIGIN_TAG: Record<string, string> = {
  HUMAN:      "bg-ggreen/10 text-ggreen border-ggreen/20",
  AUTOMATION: "bg-warn/10   text-warn   border-warn/20",
  UNKNOWN:    "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};

export default function Builders() {
  const { origin } = useOrigin();
  const q = useQuery({
    queryKey: ["v_builders", origin],
    queryFn: () => api.view<BuilderRow>("v_builders", origin),
  });

  const resourceCell = (created: number, deleted: number, color: string) => (
    <div className="flex flex-col items-end gap-0">
      <span className={created > 0 ? `${color} font-semibold` : "text-ink-muted"}>
        {created}<span className="text-ink-muted text-[10px] ml-1">c</span>
      </span>
      {deleted > 0 && (
        <span className="text-[10px] text-warn tabular-nums">{deleted} d</span>
      )}
    </div>
  );

  const cols: Col<BuilderRow>[] = [
    { key: "actor_email", label: "Actor", mono: true },
    {
      key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ),
    },
    { key: "agents_created", label: "Agent", num: true,
      render: (r) => resourceCell(r.agents_created, r.agents_deleted, "text-gblue") },
    { key: "engines_created", label: "Engine", num: true,
      render: (r) => resourceCell(r.engines_created, r.engines_deleted, "text-gred") },
    { key: "datastores_created", label: "DataStore", num: true,
      render: (r) => resourceCell(r.datastores_created, r.datastores_deleted, "text-gyellow") },
    { key: "update_actions", label: "Updates", num: true },
    { key: "total_admin_actions", label: "Total ops", num: true,
      render: (r) => <span className="text-ink-primary font-semibold">{r.total_admin_actions}</span> },
    { key: "first_admin_action", label: "First", mono: true, render: (r) => fmtTs(r.first_admin_action) },
    { key: "last_admin_action",  label: "Last",  mono: true, render: (r) => fmtTs(r.last_admin_action) },
  ];

  return (
    <div className="space-y-4">
      <div className="text-xs text-ink-muted px-1">
        💡 <b>c / d</b> = create 事件数 / delete 事件数。<br/>
        delete &gt; create 是正常的：有些资源是 sink 启动前就存在（之前手动建的 agent），后来才被删，所以只看到 delete 事件没看到 create 事件。<br/>
        当前系统里实际还活着多少资源 → 看 Overview 页 "所有 App / Engine" panel（通过 ListAgents API 实时查）。
      </div>
      <Panel title={`Builder 排行 ${origin ? `· ${origin}` : "· 全部"}`}>
        {!q.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={q.data.rows} cols={cols} filterKeys={["actor_email", "origin"]} />
        )}
      </Panel>
    </div>
  );
}
