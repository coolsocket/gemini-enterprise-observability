import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { api, QuotaOverview } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";

const FEATURE_META: Record<string, { label: string; icon: string; color: string; hint: string }> = {
  chat:          { label: "Chat", icon: "💬", color: "text-ggreen", hint: "Google 助理查询 · StreamAssist" },
  deep_research: { label: "Deep Research", icon: "🔬", color: "text-info",   hint: "AsyncAssist 提交次数" },
  agent_create:  { label: "Agent 创建", icon: "🔧", color: "text-gyellow", hint: "无代码 agent builder" },
  video_gen:     { label: "视频生成",   icon: "🎬", color: "text-gred",  hint: "待观察 - 现有数据里未捕获 imagen/veo 调用" },
  image_gen:     { label: "图片生成",   icon: "🖼️",  color: "text-gred",  hint: "待观察 - 同上" },
  idea_gen:      { label: "Idea Generation", icon: "💡", color: "text-gblue", hint: "启发式 · GE 走 StreamAssist 混不出来" },
};
const FEATURE_ORDER = ["chat", "deep_research", "agent_create", "video_gen", "image_gen", "idea_gen"];

const TIER_TAG: Record<string, string> = {
  standard: "bg-ink-muted/15 text-ink-secondary border-ink-muted/30",
  plus:     "bg-info/15 text-info border-info/30",
};

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function TotalCard({ feature, total, used, users, over_quota_users, overall_utilization }: {
  feature: string; total: number; used: number; users: number; over_quota_users: number; overall_utilization: number | null;
}) {
  const meta = FEATURE_META[feature] ?? { label: feature, icon: "•", color: "text-ink-primary", hint: "" };
  const util = overall_utilization ?? 0;
  const barColor = util >= 0.9 ? "bg-gred/60" : util >= 0.6 ? "bg-gyellow/60" : "bg-ggreen/60";
  return (
    <div className="rounded-lg border border-border-subtle bg-surface p-3">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-lg">{meta.icon}</span>
        <span className={`text-sm font-semibold ${meta.color}`}>{meta.label}</span>
      </div>
      <div className="text-[10px] text-ink-muted mb-2">{meta.hint}</div>
      <div className="flex items-baseline gap-1.5 mb-1">
        <span className="text-2xl font-semibold text-ink-primary tabular-nums">{used}</span>
        <span className="text-sm text-ink-muted">/ {total}</span>
        <span className="text-[11px] text-ink-muted ml-auto tabular-nums">{pct(util)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-subtle overflow-hidden">
        <div className={`h-full ${barColor} transition-all`} style={{ width: `${Math.min(100, util * 100)}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-ink-muted mt-1.5">
        <span>{users} eligible</span>
        {over_quota_users > 0 && <span className="text-gred">{over_quota_users} 超额</span>}
      </div>
    </div>
  );
}

function UsageBar({ used, limit, over }: { used: number; limit: number; over: boolean }) {
  const util = limit > 0 ? Math.min(1, used / limit) : 0;
  const color = over ? "bg-gred/70" : util >= 0.7 ? "bg-gyellow/60" : "bg-ggreen/50";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-subtle overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${util * 100}%` }} />
      </div>
      <span className={`text-[11px] tabular-nums w-14 text-right ${over ? "text-gred font-semibold" : "text-ink-secondary"}`}>
        {used}/{limit}
      </span>
    </div>
  );
}

export default function Quota() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["quota-overview"], queryFn: () => api.quotaOverview() });
  const setTier = useMutation({
    mutationFn: ({ email, tier }: { email: string; tier: "standard" | "plus" }) =>
      api.quotaSetTier(email, tier),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quota-overview"] }),
  });
  const [filter, setFilter] = useState<"all" | "over" | "active">("active");

  // ⚠ All hooks MUST come before any early return.
  // Guard against undefined data inside memos rather than after them.
  const byUser = useMemo(() => {
    const map: Record<string, { tier: string; features: Record<string, { used: number; limit: number; over: boolean }> }> = {};
    (q.data?.utilization ?? []).forEach(u => {
      if (!map[u.actor_email]) map[u.actor_email] = { tier: u.tier, features: {} };
      map[u.actor_email].features[u.feature] = { used: u.used_today, limit: u.daily_limit, over: u.over_quota };
    });
    return map;
  }, [q.data?.utilization]);

  const recent7d = useMemo(() => {
    const days: Record<string, Record<string, number>> = {};
    (q.data?.recent ?? []).forEach(r => {
      if (!days[r.d]) days[r.d] = {};
      days[r.d][r.feature] = (days[r.d][r.feature] || 0) + r.n;
    });
    return Object.entries(days).sort(([a], [b]) => a.localeCompare(b));
  }, [q.data?.recent]);

  if (!q.data) return <EmptyState title="加载中…" />;
  const d: QuotaOverview = q.data;

  const usersList = Object.entries(byUser).map(([email, x]) => ({
    email,
    tier: x.tier,
    features: x.features,
    total_used: Object.values(x.features).reduce((a, v) => a + v.used, 0),
    any_over: Object.values(x.features).some(v => v.over),
  }));
  const filteredUsers = usersList
    .filter(u => filter === "all" ? true : filter === "over" ? u.any_over : u.total_used > 0)
    .sort((a, b) => b.total_used - a.total_used);

  return (
    <div className="space-y-4 max-w-[1200px]">
      {/* Header: today (CA) + tier stats */}
      <div className="flex items-center gap-3 text-xs text-ink-muted">
        <span>今日 (加州时间): <span className="font-mono text-ink-primary">{d.today_ca}</span></span>
        <span>·</span>
        <span>quota 每天 <span className="text-ink-primary">America/Los_Angeles 00:00</span> 重置</span>
        <span className="ml-auto">
          {d.tiers.filter(t => t.tier === "plus").length} plus / {d.tiers.filter(t => t.tier === "standard").length} standard
        </span>
      </div>

      {/* Per-feature totals grid */}
      <Panel title="今日全平台使用 vs 总配额">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          {FEATURE_ORDER.map(f => {
            const t = d.totals.find(x => x.feature === f);
            if (!t) return null;
            return (
              <TotalCard
                key={f}
                feature={f}
                total={t.total_daily_quota}
                used={t.total_used_today}
                users={t.eligible_users}
                over_quota_users={t.users_over_quota}
                overall_utilization={t.overall_utilization}
              />
            );
          })}
        </div>
      </Panel>

      {/* Recent 7d trend */}
      {recent7d.length > 0 && (
        <Panel title="最近 7 天全平台使用 (加州日)">
          <div className="text-[10px] text-ink-muted mb-2">按天 × feature 加总</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-muted border-b border-border-subtle/40">
                <th className="py-1 pr-3 font-normal">日期</th>
                {FEATURE_ORDER.map(f => (
                  <th key={f} className="py-1 pr-3 font-normal text-right">
                    {FEATURE_META[f]?.icon} {FEATURE_META[f]?.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent7d.map(([day, feats]) => (
                <tr key={day} className="border-b border-border-subtle/20 hover:bg-subtle/30">
                  <td className="py-1 pr-3 font-mono text-ink-secondary">{day}</td>
                  {FEATURE_ORDER.map(f => {
                    const v = feats[f] ?? 0;
                    return (
                      <td key={f} className={`py-1 pr-3 text-right tabular-nums ${v > 0 ? "text-ink-primary" : "text-ink-muted opacity-40"}`}>
                        {v > 0 ? v : "·"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {/* Per-user drill */}
      <Panel
        title={`用户配额使用 · ${filteredUsers.length}`}
        action={
          <div className="flex items-center gap-1 text-[10px]">
            {(["active", "over", "all"] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`h-6 px-2 rounded ${filter === f ? "bg-info/15 text-info border border-info/30" : "text-ink-muted hover:text-ink-secondary"}`}
              >
                {f === "active" ? "今日活跃" : f === "over" ? "超额" : "全部"}
              </button>
            ))}
          </div>
        }
      >
        <div className="text-[10px] text-ink-muted mb-3">
          点用户可跳去 deep dive · 点 tier tag 可切换 tier
        </div>
        {filteredUsers.length === 0 ? (
          <EmptyState title="无匹配用户" hint={filter === "active" ? "今日暂无活动" : filter === "over" ? "无人超额 🎉" : ""} />
        ) : (
          <div className="space-y-1">
            {/* Header row */}
            <div className="flex items-center gap-2 px-2 py-1 text-[10px] uppercase tracking-wide text-ink-muted border-b border-border-subtle/40">
              <div className="w-56 shrink-0">用户</div>
              <div className="w-14 shrink-0 text-center">Tier</div>
              {FEATURE_ORDER.slice(0, 4).map(f => (
                <div key={f} className="flex-1 text-center">{FEATURE_META[f].icon} {FEATURE_META[f].label}</div>
              ))}
            </div>
            {filteredUsers.map(u => (
              <div key={u.email} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-subtle/30 rounded">
                <button
                  onClick={() => navigate(`/user/${encodeURIComponent(u.email)}`)}
                  className="w-56 shrink-0 font-mono text-ink-primary hover:text-info truncate text-left"
                  title={u.email}
                >
                  {u.email.length > 32 ? u.email.slice(0, 24) + "…" + u.email.slice(-7) : u.email}
                </button>
                <button
                  onClick={() => setTier.mutate({ email: u.email, tier: u.tier === "plus" ? "standard" : "plus" })}
                  disabled={setTier.isPending}
                  className={`w-14 shrink-0 text-[9px] px-1.5 py-0.5 rounded border font-medium ${TIER_TAG[u.tier]} hover:opacity-80`}
                  title="点击切换 tier"
                >
                  {u.tier.toUpperCase()}
                </button>
                {FEATURE_ORDER.slice(0, 4).map(f => {
                  const cell = u.features[f];
                  if (!cell) return <div key={f} className="flex-1 text-ink-muted text-center">—</div>;
                  return (
                    <div key={f} className="flex-1">
                      <UsageBar used={cell.used} limit={cell.limit} over={cell.over} />
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Tier schedule reference */}
      <Panel title="Tier 阈值配置">
        <div className="text-[10px] text-ink-muted mb-3">
          从 <code className="bg-subtle px-1 rounded">quota_config</code> 表读；每天加州 0 点重置。改数字直接改 BQ 表即可 (or 通过 <code className="bg-subtle px-1 rounded">POST /api/quota/config</code>)
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-muted border-b border-border-subtle/40">
              <th className="py-1 pr-3 font-normal">Feature</th>
              <th className="py-1 pr-3 font-normal text-right">Standard 每日</th>
              <th className="py-1 pr-3 font-normal text-right">Plus 每日</th>
              <th className="py-1 pr-3 font-normal">注</th>
            </tr>
          </thead>
          <tbody>
            {FEATURE_ORDER.map(f => {
              const std = d.config.find(c => c.key === `tier.standard.${f}_daily`)?.value ?? "—";
              const plus = d.config.find(c => c.key === `tier.plus.${f}_daily`)?.value ?? "—";
              const meta = FEATURE_META[f];
              return (
                <tr key={f} className="border-b border-border-subtle/20">
                  <td className="py-1 pr-3">{meta.icon} {meta.label}</td>
                  <td className="py-1 pr-3 text-right tabular-nums text-ink-secondary">{std}</td>
                  <td className="py-1 pr-3 text-right tabular-nums text-info font-medium">{plus}</td>
                  <td className="py-1 pr-3 text-[10px] text-ink-muted">{meta.hint}</td>
                </tr>
              );
            })}
            {/* Storage — not daily, one-time */}
            <tr className="border-b border-border-subtle/20">
              <td className="py-1 pr-3">💾 存储 (GiB)</td>
              <td className="py-1 pr-3 text-right tabular-nums text-ink-secondary">
                {d.config.find(c => c.key === "tier.standard.storage_gib")?.value ?? "—"}
              </td>
              <td className="py-1 pr-3 text-right tabular-nums text-info font-medium">
                {d.config.find(c => c.key === "tier.plus.storage_gib")?.value ?? "—"}
              </td>
              <td className="py-1 pr-3 text-[10px] text-ink-muted">Data store 总大小 (未接入 · TODO: 调 dataStore.list API)</td>
            </tr>
          </tbody>
        </table>
      </Panel>

      {/* Tier assignments raw */}
      <Panel title={`用户 tier 分配 · ${d.tiers.length}`}>
        <div className="max-h-[300px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface">
              <tr className="text-left text-ink-muted border-b border-border-subtle/40">
                <th className="py-1 pr-3 font-normal">Email</th>
                <th className="py-1 pr-3 font-normal">Tier</th>
                <th className="py-1 pr-3 font-normal">分配时间</th>
                <th className="py-1 pr-3 font-normal">分配者</th>
              </tr>
            </thead>
            <tbody>
              {d.tiers.map(t => (
                <tr key={t.actor_email} className="border-b border-border-subtle/20">
                  <td className="py-1 pr-3 font-mono text-ink-secondary">{t.actor_email}</td>
                  <td className="py-1 pr-3">
                    <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-medium border ${TIER_TAG[t.tier]}`}>
                      {t.tier}
                    </span>
                  </td>
                  <td className="py-1 pr-3 font-mono text-ink-muted">{fmtTs(t.assigned_at)}</td>
                  <td className="py-1 pr-3 text-ink-muted">{t.assigned_by ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
