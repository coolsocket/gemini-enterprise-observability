// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api, QuotaOverview } from "../api";
import { Panel, EmptyState } from "../components/Card";
import { fmtTs } from "../components/DataTable";
import { QuotaTotalCard } from "../components/QuotaTotalCard";

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
  chat:          { label: "Chat",         icon: "💬", color: "text-ggreen",  hint: "StreamAssist 调用次数" },
  deep_research: { label: "Deep Research",icon: "🔬", color: "text-info",    hint: "AsyncAssist 提交次数（不含轮询）。⚠ GE 会在普通聊天时也触发 AsyncAssist,此计数可能虚高" },
  notebooklm:    { label: "NotebookLM",   icon: "📓", color: "text-info",    hint: "Create/Update/Delete/Generate 等写入操作 (不含 Get/List 读)" },
  a2a:           { label: "Agent-to-Agent",icon: "🧩", color: "text-gyellow",hint: "assistants.agents.a2a.v1 调用次数" },
  agent_create:  { label: "Agent 创建",   icon: "🔧", color: "text-gyellow", hint: "AgentService.CreateAgent 事件" },
};
// image_gen / video_gen / idea_gen removed 2026-07-06 — GE runs those inside
// Google infra without customer audit logs, so we can only guess from prompt
// keywords, which was inaccurate enough to mislead. Bring back only when GE
// exposes a real per-feature counter.
const FEATURE_ORDER = ["chat", "deep_research", "notebooklm", "a2a", "agent_create"];

const TIER_TAG: Record<string, string> = {
  standard: "bg-ink-muted/15 text-ink-secondary border-ink-muted/30",
  plus:     "bg-info/15 text-info border-info/30",
};

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

// TotalCard moved to components/QuotaTotalCard.tsx (R3c, 2026-07-10).
// FEATURE_META still lives here so the page controls the label taxonomy.
const _DEFAULT_META = { label: "?", icon: "•", color: "text-ink-primary", hint: "" };

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
  const [windowDays, setWindowDays] = useState<1 | 7 | 30>(1);
  const q = useQuery({
    queryKey: ["quota-overview", windowDays],
    queryFn: () => api.quotaOverview(windowDays),
  });
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
  type SortKey = "email" | "tier" | "total" | string; // string = feature key
  const [sortKey, setSortKey] = useState<SortKey>("total");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir(k === "email" ? "asc" : "desc"); }
  };

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
    .sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortKey === "email") return a.email.localeCompare(b.email) * mul;
      if (sortKey === "tier")  return (a.tier === b.tier ? 0 : a.tier === "plus" ? -1 : 1) * mul;
      if (sortKey === "total") return (a.total_used - b.total_used) * mul;
      // feature-key: sort by utilization ratio (used/limit), 0 for missing
      const ratio = (u: typeof a) => {
        const c = u.features[sortKey];
        return c && c.limit > 0 ? c.used / c.limit : 0;
      };
      return (ratio(a) - ratio(b)) * mul;
    });
  const sortArrow = (k: SortKey) => sortKey === k ? (sortDir === "asc" ? " ▲" : " ▼") : "";

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
      <Panel
        title={windowDays === 1 ? "今日全平台使用 vs 总配额" : `最近 ${windowDays} 天全平台使用 vs 总配额`}
        action={
          <div className="flex items-center gap-1 text-[10px]">
            {([1, 7, 30] as const).map(w => (
              <button
                key={w}
                onClick={() => setWindowDays(w)}
                className={`h-6 px-2 rounded ${windowDays === w
                  ? "bg-info/15 text-info border border-info/30 font-medium"
                  : "text-ink-muted hover:text-ink-secondary border border-transparent"}`}
                title={w === 1 ? "今天" : `最近 ${w} 天 (总配额已按 ${w}× seat 单日限额 计算)`}
              >
                {w === 1 ? "今日" : `${w}d`}
              </button>
            ))}
          </div>
        }
      >
        {windowDays > 1 && (
          <div className="text-[10px] text-ink-muted mb-2">
            分母 = 每 seat 单日配额 × {windowDays} 天 × 已购 seats（"这个窗口烧掉了多少预算"的口径）。
            "超额人数" 仅今日口径下才有意义,此窗口下不显示。
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
          {FEATURE_ORDER.map(f => {
            const t = d.totals.find(x => x.feature === f);
            if (!t) return null;
            return (
              <QuotaTotalCard
                key={f}
                featureMeta={FEATURE_META[f] ?? _DEFAULT_META}
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
            {/* Header row — clickable to sort */}
            <div className="flex items-center gap-2 px-2 py-1 text-[10px] uppercase tracking-wide text-ink-muted border-b border-border-subtle/40">
              <button
                onClick={() => toggleSort("email")}
                className={`w-56 shrink-0 text-left hover:text-ink-primary ${sortKey === "email" ? "text-info" : ""}`}
              >用户{sortArrow("email")}</button>
              <button
                onClick={() => toggleSort("tier")}
                className={`w-14 shrink-0 text-center hover:text-ink-primary ${sortKey === "tier" ? "text-info" : ""}`}
              >Tier{sortArrow("tier")}</button>
              {FEATURE_ORDER.map(f => (
                <button
                  key={f}
                  onClick={() => toggleSort(f)}
                  className={`flex-1 text-center hover:text-ink-primary ${sortKey === f ? "text-info" : ""}`}
                  title="按使用率排序"
                >{FEATURE_META[f].icon} {FEATURE_META[f].label}{sortArrow(f)}</button>
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
                {FEATURE_ORDER.map(f => {
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
