import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import DataTable, { Col, fmtNum, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";

type ViewMeta = { name: string; label: string; source: "path2" | "path3" | "derived" };

const VIEWS: ViewMeta[] = [
  { name: "v_user_persona",                source: "derived", label: "用户画像" },
  { name: "v_conversations",               source: "path2",   label: "原始对话(prompt)" },
  { name: "v_conversations_with_response", source: "derived", label: "完整对话 (prompt+response 模糊配对)" },
  { name: "v_choices",                     source: "path2",   label: "模型回答 chunks" },
  { name: "v_choices_agg",                 source: "derived", label: "模型回答 (按 trace 聚合)" },
  { name: "v_admin_activity",              source: "path3",   label: "管理操作时间线" },
  { name: "v_builders",                    source: "derived", label: "Builder 排行榜" },
  { name: "v_engine_adoption",             source: "derived", label: "Engine 采纳度" },
  { name: "v_zero_use_seats",              source: "derived", label: "0 使用 seats" },
  { name: "v_dau",                         source: "derived", label: "DAU 趋势" },
  { name: "v_data_access",                 source: "path3",   label: "Data Access 时间线" },
  { name: "v_data_access_summary",         source: "derived", label: "谁查了什么" },
  { name: "v_user_usage",                  source: "path2",   label: "用户 × Engine" },
];

const SOURCE_TAG: Record<string, string> = {
  path2:   "bg-gblue/10 text-gblue border-gblue/20",
  path3:   "bg-gred/10 text-gred border-gred/20",
  derived: "bg-ink-muted/10 text-ink-muted border-ink-muted/20",
};
const SOURCE_LABEL: Record<string, string> = {
  path2:   "Path 2",
  path3:   "Path 3",
  derived: "derived",
};

const NUMERIC_HINT = /count|sessions|turns|created|actions|events|users|seats|search|answer|recommend|access|dau|span|days|size|calls/i;
const TIME_HINT    = /time|seen|access|action|admin|stamp|first|last/i;

export default function Raw() {
  const [active, setActive] = useState(VIEWS[0].name);
  const q = useQuery({ queryKey: [active], queryFn: () => api.view(active) });
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api.meta() });
  const project = meta.data?.project ?? "";

  const cols: Col<Record<string, unknown>>[] = q.data && q.data.rows.length > 0
    ? Object.keys(q.data.rows[0]).map((k) => ({
        key: k,
        label: k,
        num:  NUMERIC_HINT.test(k),
        mono: /id|email|principal|name|resource|method|ip/i.test(k),
        render: (r) => {
          const v = r[k];
          if (v == null || v === "") return <span className="text-ink-muted">—</span>;
          if (TIME_HINT.test(k) && /^\d{4}-/.test(String(v))) return fmtTs(v);
          if (NUMERIC_HINT.test(k)) return fmtNum(v);
          return String(v);
        },
      }))
    : [];

  return (
    <div className="space-y-4">
      {/* Data source banner */}
      <div className="rounded-xl border border-border-subtle bg-surface px-5 py-4 text-sm">
        <div className="text-ink-primary font-medium mb-2">📋 数据来源</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div>
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${SOURCE_TAG.path2}`}>Path 2</span>
            <span className="text-ink-secondary ml-2">Discovery Engine 业务日志</span>
            <div className="text-ink-muted mt-1 font-mono text-[10px]">
              discoveryengine.googleapis.com/<br/>· gemini_enterprise_user_activity<br/>· gen_ai.user.message<br/>· gen_ai.choice
            </div>
          </div>
          <div>
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${SOURCE_TAG.path3}`}>Path 3</span>
            <span className="text-ink-secondary ml-2">Cloud Audit Logs</span>
            <div className="text-ink-muted mt-1 font-mono text-[10px]">
              cloudaudit.googleapis.com/<br/>· activity (admin actions)<br/>· data_access (reads)
            </div>
          </div>
          <div>
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${SOURCE_TAG.derived}`}>derived</span>
            <span className="text-ink-secondary ml-2">基于 Path 2/3 聚合的视图</span>
            <div className="text-ink-muted mt-1">
              JOIN engine_metadata 拿 displayName，GROUP BY trace_id 聚合 streaming，按 origin 分类等
            </div>
          </div>
        </div>
        <div className="text-[11px] text-ink-muted mt-3">
          全部通过 Logs Router sink <code className="bg-subtle px-1 rounded">ge-observability-unified</code> 路由到 BigQuery dataset <code className="bg-subtle px-1 rounded">ge_observability</code>
        </div>
        <div className="mt-3 pt-3 border-t border-border-subtle/60">
          <div className="text-[11px] text-ink-muted mb-1.5">想看更细的？我们还没接入：</div>
          <ul className="text-[11px] text-ink-secondary space-y-1 list-disc list-inside">
            <li><b>Cloud Trace</b> — 单次请求的 step-by-step 时序（model 时延 / connector 时延拆解）{project && <a href={`https://console.cloud.google.com/traces/list?project=${project}`} className="text-info hover:underline ml-1">打开</a>}</li>
            <li><b>Cloud Monitoring</b> — QPS、错误率、延迟分布等 metrics（5 种 discovery engine 指标如 agent_session_count）{project && <a href={`https://console.cloud.google.com/monitoring/metrics-explorer?project=${project}`} className="text-info hover:underline ml-1">打开</a>}</li>
            <li><b>Logs Explorer</b> — 不通过 BQ sink 直接看原始日志 {project && <a href={`https://console.cloud.google.com/logs/query?project=${project}`} className="text-info hover:underline ml-1">打开</a>}</li>
            <li><b>GE OOB Analytics</b> — Console 内置 5-tab dashboard（含 seat-level metrics，6 小时刷新，限 top 500 用户）</li>
          </ul>
          <div className="text-[10px] text-ink-muted mt-1">注：GE 日志侧确认<b>没有</b>更多 log channel（探过 model_armor / safety / system_message 等都不存在）</div>
        </div>
      </div>

      {/* View picker */}
      <div className="flex flex-wrap gap-1.5">
        {VIEWS.map((v) => (
          <button
            key={v.name}
            onClick={() => setActive(v.name)}
            className={`px-3 py-1.5 rounded-md text-xs transition-colors inline-flex items-center gap-1.5 ${
              active === v.name
                ? "bg-accent text-ink-inverse font-medium"
                : "bg-surface text-ink-secondary border border-border-subtle hover:text-ink-primary hover:border-border-default"
            }`}
          >
            <span>{v.label}</span>
            <span className={`text-[9px] px-1 py-0.5 rounded border ${SOURCE_TAG[v.source]}`}>{SOURCE_LABEL[v.source]}</span>
            <span className="opacity-60 font-mono text-[10px]">{v.name}</span>
          </button>
        ))}
      </div>

      <Panel title={active}>
        {!q.data ? <EmptyState title="加载中…" /> :
         q.data.rows.length === 0 ? (
           <EmptyState
             title="暂无行"
             hint={active === "v_zero_use_seats" ? "👍 没有不活跃的 seat" : "等待第一笔事件流入"}
           />
         ) : (
          <DataTable rows={q.data.rows} cols={cols} />
        )}
      </Panel>
    </div>
  );
}
