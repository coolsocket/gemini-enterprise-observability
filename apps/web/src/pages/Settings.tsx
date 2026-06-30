import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";

export default function Settings() {
  const qc = useQueryClient();
  const meta   = useQuery({ queryKey: ["meta"],           queryFn: api.meta });
  const quota  = useQuery({ queryKey: ["quota-config"],   queryFn: api.quotaConfig });
  const status = useQuery({ queryKey: ["refresh-status"], queryFn: api.refreshStatus });

  const setQuota = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.quotaSet(key, value),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["quota-config"] }); qc.invalidateQueries({ queryKey: ["summary"] }); },
  });
  const refresh = useMutation({
    mutationFn: api.refreshNow,
    onSuccess: () => qc.invalidateQueries(),
  });

  const [seatsInput, setSeatsInput] = useState<string>("");
  const [windowInput, setWindowInput] = useState<string>("");

  const purchased = quota.data?.purchased_seats?.value ?? "";
  const window = quota.data?.claimed_window_days?.value ?? "";

  return (
    <div className="space-y-4">

      {/* Quota config */}
      <Panel title="Quota / Seat 配置">
        {!quota.data ? <EmptyState title="加载中…" /> : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-ink-muted mb-1">已购 Seats</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="0"
                  defaultValue={purchased}
                  onChange={(e) => setSeatsInput(e.target.value)}
                  className="flex-1 h-9 px-3 rounded-md bg-subtle border border-border-subtle text-sm placeholder:text-ink-muted focus:outline-none focus:border-border-default font-mono"
                  placeholder="50"
                />
                <button
                  onClick={() => setQuota.mutate({ key: "purchased_seats", value: seatsInput || purchased })}
                  disabled={setQuota.isPending}
                  className="h-9 px-4 rounded-md bg-accent text-ink-inverse text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >保存</button>
              </div>
              <div className="text-xs text-ink-muted mt-1.5">
                上次更新：{fmtTs(quota.data.purchased_seats?.updated_at ?? null)} by {quota.data.purchased_seats?.updated_by ?? "—"}
              </div>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-ink-muted mb-1">Claimed 窗口（天）</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="1" max="365"
                  defaultValue={window}
                  onChange={(e) => setWindowInput(e.target.value)}
                  className="flex-1 h-9 px-3 rounded-md bg-subtle border border-border-subtle text-sm placeholder:text-ink-muted focus:outline-none focus:border-border-default font-mono"
                  placeholder="30"
                />
                <button
                  onClick={() => setQuota.mutate({ key: "claimed_window_days", value: windowInput || window })}
                  disabled={setQuota.isPending}
                  className="h-9 px-4 rounded-md bg-accent text-ink-inverse text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >保存</button>
              </div>
              <div className="text-xs text-ink-muted mt-1.5">
                "活跃用户" 算入 claimed 的时间窗
              </div>
            </div>
          </div>
        )}
      </Panel>

      {/* Snapshot status */}
      <Panel title="Snapshot 刷新状态" action={
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="h-8 px-3 rounded-md bg-accent text-ink-inverse text-xs font-medium hover:opacity-90 disabled:opacity-50"
        >
          {refresh.isPending ? "正在物化…" : "立即刷新全部"}
        </button>
      }>
        {!status.data ? <EmptyState title="加载中…" /> : (
          <>
            <div className="text-xs text-ink-muted mb-3">
              最近一次刷新: {fmtTs(status.data.last_refresh)} · 共 {status.data.snapshot_count} 个 snapshot
            </div>
            <div className="rounded-lg border border-border-subtle bg-subtle/30 overflow-hidden">
              <table className="w-full text-xs">
                <thead className="text-ink-muted">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">Snapshot</th>
                    <th className="text-left px-3 py-2 font-medium">Source</th>
                    <th className="text-right px-3 py-2 font-medium">Rows</th>
                    <th className="text-right px-3 py-2 font-medium">Refresh (s)</th>
                    <th className="text-right px-3 py-2 font-medium">刷新时间</th>
                    <th className="text-left px-3 py-2 font-medium">触发</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data.snapshots.map((s) => (
                    <tr key={s.snapshot_name} className="border-t border-border-subtle/60">
                      <td className="px-3 py-1.5 font-mono text-ink-primary">{s.snapshot_name}</td>
                      <td className="px-3 py-1.5 font-mono text-ink-muted">{s.source_view}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{s.row_count}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{s.refresh_seconds.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-ink-muted">{fmtTs(s.refreshed_at)}</td>
                      <td className="px-3 py-1.5 text-ink-muted">{s.triggered_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      {/* Data source */}
      <Panel title="数据源">
        {!meta.data ? <EmptyState title="加载中…" /> : (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-ink-muted">Project</dt>
            <dd className="font-mono text-ink-primary">{meta.data.project}</dd>
            <dt className="text-ink-muted">Dataset</dt>
            <dd className="font-mono text-ink-primary">{meta.data.dataset}</dd>
            <dt className="text-ink-muted">Sink</dt>
            <dd className="font-mono text-ink-primary">{meta.data.sink_name}</dd>
          </dl>
        )}
      </Panel>

      {/* Available views */}
      <Panel title="可用 View / Snapshot">
        {!meta.data ? null : (
          <ul className="divide-y divide-border-subtle">
            {meta.data.views.map((v) => (
              <li key={v.name} className="py-2.5 flex items-baseline justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink-primary">{v.label}</div>
                  <div className="text-xs text-ink-muted">{v.desc}</div>
                </div>
                <div className="text-xs text-ink-secondary shrink-0 font-mono">
                  {v.name} <span className="text-ink-muted">→</span> s_{v.name.slice(2)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* API endpoints */}
      <Panel title="API 端点">
        <ul className="text-sm space-y-1.5 font-mono">
          <li><span className="text-ink-muted">GET </span><a href="/api/healthz" className="text-info hover:underline">/api/healthz</a></li>
          <li><span className="text-ink-muted">GET </span><a href="/api/meta"    className="text-info hover:underline">/api/meta</a></li>
          <li><span className="text-ink-muted">GET </span><a href="/api/summary" className="text-info hover:underline">/api/summary</a> <span className="text-ink-muted text-xs">?origin=HUMAN&amp;live=true</span></li>
          <li><span className="text-ink-muted">GET </span>/api/v/<span className="text-info">{`{view}`}</span> <span className="text-ink-muted text-xs">?origin=...&amp;live=true</span></li>
          <li><span className="text-ink-muted">POST</span> /api/refresh <span className="text-ink-muted text-xs">→ 重新物化所有 snapshot</span></li>
          <li><span className="text-ink-muted">GET </span><a href="/api/refresh/status" className="text-info hover:underline">/api/refresh/status</a></li>
          <li><span className="text-ink-muted">GET </span><a href="/api/quota/config"   className="text-info hover:underline">/api/quota/config</a></li>
          <li><span className="text-ink-muted">POST</span> /api/quota/config <span className="text-ink-muted text-xs">?key=...&amp;value=...</span></li>
          <li><span className="text-ink-muted">GET </span><a href="/docs" className="text-info hover:underline">/docs</a> (Swagger UI)</li>
        </ul>
      </Panel>
    </div>
  );
}
