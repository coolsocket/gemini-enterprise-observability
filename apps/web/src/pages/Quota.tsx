import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api, QuotaOverview } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";

// Inline editable number cell — click to edit, Enter/blur to save, Esc to cancel
function EditableNumber({ value, onSave, saving, accent }: {
  value: string | number;
  onSave: (v: string) => void;
  saving?: boolean;
  accent?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== String(value) && draft.trim() !== "") onSave(draft.trim());
    else setDraft(String(value));
  };
  const cancel = () => { setEditing(false); setDraft(String(value)); };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="number"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") cancel();
        }}
        className="w-16 h-6 px-1.5 rounded bg-info-bg/10 border border-info/60 text-info text-right tabular-nums focus:outline-none"
      />
    );
  }
  return (
    <button
      onClick={() => setEditing(true)}
      disabled={saving}
      className={`px-1.5 h-6 rounded tabular-nums ${accent ?? "text-ink-secondary"} hover:bg-subtle hover:ring-1 hover:ring-info/40 ${saving ? "opacity-50 animate-pulse" : ""}`}
      title="点击编辑"
    >
      {value}
    </button>
  );
}

const FEATURE_META: Record<string, { label: string; icon: string; color: string; hint: string }> = {
  chat:          { label: "Chat", icon: "💬", color: "text-ggreen", hint: "Google 助理查询 · StreamAssist" },
  deep_research: { label: "Deep Research", icon: "🔬", color: "text-info",   hint: "AsyncAssist 提交次数" },
  agent_create:  { label: "Agent 创建", icon: "🔧", color: "text-gyellow", hint: "无代码 agent builder" },
  video_gen:     { label: "视频生成",   icon: "🎬", color: "text-gred",  hint: "启发式 - GE 后端不 emit audit log, 用 StreamAssist prompt 关键词匹配" },
  image_gen:     { label: "图片生成",   icon: "🖼️",  color: "text-gred",  hint: "启发式 - 同上, 关键词如'生成一只青蛙'" },
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
  const setConfig = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.quotaSet(key, value),
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

      {/* NEW: Seat inventory (from real licenseConfigs API) */}
      {d.config.find(c => c.key === "license.total_seats") && (
        <Panel title="已购 Seats (真实 licenseConfigs API)">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-lg border border-info/30 bg-info/5 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-wide text-info/80">已购 seats 总数</div>
              <div className="text-3xl font-semibold text-info tabular-nums mt-0.5">
                {d.config.find(c => c.key === "license.total_seats")?.value ?? "?"}
              </div>
              <div className="text-[10px] text-ink-muted">licenseConfigs API</div>
            </div>
            <div className="rounded-lg border border-ggreen/30 bg-ggreen/5 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-wide text-ggreen/80">已用 seats</div>
              <div className="text-3xl font-semibold text-ggreen tabular-nums mt-0.5">
                {d.tiers.length}
              </div>
              <div className="text-[10px] text-ink-muted">
                历史活跃 actor 数 · {
                  d.config.find(c => c.key === "license.total_seats")?.value
                    ? Math.round(d.tiers.length / Number(d.config.find(c => c.key === "license.total_seats")!.value) * 100)
                    : "?"
                }% 占用
              </div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-wide text-ink-muted">Subscription tier</div>
              <div className="text-sm font-medium text-ink-primary mt-1.5">
                {d.config.find(c => c.key.startsWith("license.seats.SUBSCRIPTION_"))?.key.replace("license.seats.SUBSCRIPTION_TIER_", "").replace(/_/g, " ") ?? "?"}
              </div>
              <div className="text-[10px] text-ink-muted mt-0.5">
                {d.config.find(c => c.key === "license.config_count")?.value ?? "?"} configs
              </div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-wide text-ink-muted">数据源</div>
              <div className="text-[11px] text-ink-secondary mt-1.5 font-mono">
                v1alpha/licenseConfigs
              </div>
              <div className="text-[10px] text-ink-muted mt-0.5">
                每次 bootstrap.py 同步一次
              </div>
            </div>
          </div>
        </Panel>
      )}

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

      {/* Tier schedule — editable */}
      <Panel
        title="Tier 阈值配置"
        action={
          <span className="text-[10px] text-ink-muted">
            {setConfig.isPending ? "保存中…" : "点数字直接编辑 · Enter 保存"}
          </span>
        }
      >
        <div className="text-[10px] text-ink-muted mb-3">
          每天加州 0 点重置。改动立即写入 <code className="bg-subtle px-1 rounded">quota_config</code>，utilization 会自动重算。
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-muted border-b border-border-subtle/40">
              <th className="py-1.5 pr-3 font-normal">Feature</th>
              <th className="py-1.5 pr-3 font-normal text-right w-24">Standard</th>
              <th className="py-1.5 pr-3 font-normal text-right w-24">Plus</th>
              <th className="py-1.5 pr-3 font-normal">说明</th>
            </tr>
          </thead>
          <tbody>
            {FEATURE_ORDER.map(f => {
              const std = d.config.find(c => c.key === `tier.standard.${f}_daily`)?.value ?? "—";
              const plus = d.config.find(c => c.key === `tier.plus.${f}_daily`)?.value ?? "—";
              const meta = FEATURE_META[f];
              return (
                <tr key={f} className="border-b border-border-subtle/20 hover:bg-subtle/20">
                  <td className="py-1 pr-3">{meta.icon} {meta.label}</td>
                  <td className="py-1 pr-3 text-right">
                    <EditableNumber
                      value={std}
                      accent="text-ink-secondary"
                      onSave={v => setConfig.mutate({ key: `tier.standard.${f}_daily`, value: v })}
                      saving={setConfig.isPending && setConfig.variables?.key === `tier.standard.${f}_daily`}
                    />
                  </td>
                  <td className="py-1 pr-3 text-right">
                    <EditableNumber
                      value={plus}
                      accent="text-info font-medium"
                      onSave={v => setConfig.mutate({ key: `tier.plus.${f}_daily`, value: v })}
                      saving={setConfig.isPending && setConfig.variables?.key === `tier.plus.${f}_daily`}
                    />
                  </td>
                  <td className="py-1 pr-3 text-[10px] text-ink-muted">{meta.hint}</td>
                </tr>
              );
            })}
            {/* Storage — not daily, one-time */}
            <tr className="border-b border-border-subtle/20 hover:bg-subtle/20">
              <td className="py-1 pr-3">💾 存储 (GiB)</td>
              <td className="py-1 pr-3 text-right">
                <EditableNumber
                  value={d.config.find(c => c.key === "tier.standard.storage_gib")?.value ?? "0"}
                  accent="text-ink-secondary"
                  onSave={v => setConfig.mutate({ key: "tier.standard.storage_gib", value: v })}
                  saving={setConfig.isPending && setConfig.variables?.key === "tier.standard.storage_gib"}
                />
              </td>
              <td className="py-1 pr-3 text-right">
                <EditableNumber
                  value={d.config.find(c => c.key === "tier.plus.storage_gib")?.value ?? "0"}
                  accent="text-info font-medium"
                  onSave={v => setConfig.mutate({ key: "tier.plus.storage_gib", value: v })}
                  saving={setConfig.isPending && setConfig.variables?.key === "tier.plus.storage_gib"}
                />
              </td>
              <td className="py-1 pr-3 text-[10px] text-ink-muted">Data store 总大小 (未接入 · TODO)</td>
            </tr>
          </tbody>
        </table>

        {/* Bulk actions row */}
        <div className="flex items-center gap-2 mt-4 pt-3 border-t border-border-subtle/40">
          <span className="text-[11px] text-ink-muted mr-2">批量:</span>
          <button
            onClick={() => {
              if (!confirm("把所有 10 个用户改成 plus tier?")) return;
              d.tiers.forEach(t => setTier.mutate({ email: t.actor_email, tier: "plus" }));
            }}
            className="h-7 px-2.5 rounded text-[11px] bg-info/10 text-info border border-info/30 hover:bg-info/20"
          >
            全部改 Plus
          </button>
          <button
            onClick={() => {
              if (!confirm("把所有 10 个用户改成 standard tier?")) return;
              d.tiers.forEach(t => setTier.mutate({ email: t.actor_email, tier: "standard" }));
            }}
            className="h-7 px-2.5 rounded text-[11px] bg-subtle text-ink-secondary border border-border-subtle hover:bg-ink-muted/20"
          >
            全部改 Standard
          </button>
          <span className="text-[10px] text-ink-muted ml-auto">
            {setTier.isPending ? "保存中…" : `默认新用户 tier: ${d.config.find(c => c.key === "quota.default_tier")?.value ?? "?"}`}
          </span>
          {!setTier.isPending && (
            <button
              onClick={() => {
                const v = d.config.find(c => c.key === "quota.default_tier")?.value === "plus" ? "standard" : "plus";
                setConfig.mutate({ key: "quota.default_tier", value: v });
              }}
              className="text-[10px] text-info hover:underline"
            >
              切换默认
            </button>
          )}
        </div>
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
