import { useQuery } from "@tanstack/react-query";
import { api, EngineRow } from "../api";
import DataTable, { Col } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";

export default function Engines() {
  const q = useQuery({ queryKey: ["v_engine_adoption"], queryFn: () => api.view<EngineRow>("v_engine_adoption") });

  const cols: Col<EngineRow>[] = [
    { key: "engine_display_name", label: "Engine", mono: true,
      render: (r) => r.engine_display_name ?? <span className="text-ink-muted">{r.engine_id}</span> },
    { key: "engine_id", label: "ID", mono: true,
      render: (r) => <span className="text-[11px] text-ink-muted">{r.engine_id}</span> },
    { key: "unique_users", label: "独立用户", num: true,
      render: (r) => <span className="text-ggreen font-medium">{r.unique_users}</span> },
    { key: "sessions",     label: "Sessions", num: true },
    { key: "chat_turns",   label: "Chat turns", num: true,
      render: (r) => <span className="text-gblue">{r.chat_turns}</span> },
    { key: "total_events", label: "总事件", num: true,
      render: (r) => <span className="font-semibold">{r.total_events}</span> },
  ];

  return (
    <div className="space-y-4">
      {/* Hint */}
      <div className="text-xs text-ink-muted px-1">
        💡 这个表统计了 <b>每个 GE engine 各自被谁用过、用了多少</b>。<br/>
        Engines 列表来自 admin metadata；这张表只显示有用户聊天活动的 engine（按 unique_users / chat_turns / sessions 排序）。Engine 名字来自 GE 后台。
      </div>

      <Panel title="Engine 使用情况">
        {!q.data ? <EmptyState title="加载中…" /> :
         q.data.rows.length === 0 ? (
          <EmptyState title="暂无 engine 事件" hint="等待 user_activity 日志流入" />
        ) : (
          <DataTable rows={q.data.rows} cols={cols} filterKeys={["engine_id", "engine_display_name"]} />
        )}
      </Panel>
    </div>
  );
}
