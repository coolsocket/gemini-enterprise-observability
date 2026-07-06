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

import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, DauRow, EngineRow, PersonaRow } from "../api";
import Card, { EmptyState, Panel } from "../components/Card";
import { fmtTs } from "../components/DataTable";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";
import { useI18n } from "../i18n";

const PERSONA_COLOR: Record<string, string> = {
  POWER_USER:      "#4285F4",
  ACTIVE_CONSUMER: "#34A853",
  TRIAL:           "#FBBC04",
  BUILDER:         "#EA4335",
  EXPLORER:        "#9B72CB",
  LURKER:          "#9aa0a6",
  AUTOMATION:      "#5b647a",
};

const PERSONA_LABEL: Record<string, string> = {
  POWER_USER:      "POWER · 7 天≥20 turns",
  ACTIVE_CONSUMER: "ACTIVE · 7 天≥5 turns",
  TRIAL:           "TRIAL · 总 turns 1-4",
  BUILDER:         "BUILDER · 建过资源",
  EXPLORER:        "EXPLORER · 仅浏览",
  LURKER:          "LURKER · 14 天静默",
  AUTOMATION:      "AUTOMATION · 自动化",
};

export default function Overview() {
  const { t } = useI18n();
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const { range } = useRange();
  const summary = useQuery({ queryKey: ["summary", origin, engineId, range], queryFn: () => api.summary(origin, engineId, range) });
  const persona = useQuery({ queryKey: ["v_user_persona", range],            queryFn: () => api.view<PersonaRow>("v_user_persona", null, null, range) });
  const dau     = useQuery({ queryKey: ["v_dau", range],                     queryFn: () => api.view<DauRow>("v_dau", null, null, range) });
  const engines = useQuery({ queryKey: ["v_engine_adoption"],                queryFn: () => api.view<EngineRow>("v_engine_adoption") });
  const alive   = useQuery({ queryKey: ["alive"],                            queryFn: api.aliveResources });

  const s = summary.data;

  // Persona distribution — show ALL personas (HUMAN + AUTOMATION) for clarity
  const personaBuckets = (() => {
    const counts: Record<string, number> = {
      POWER_USER: 0, ACTIVE_CONSUMER: 0, TRIAL: 0,
      BUILDER: 0, EXPLORER: 0, LURKER: 0, AUTOMATION: 0,
    };
    persona.data?.rows.forEach((r) => { counts[r.persona] = (counts[r.persona] || 0) + 1; });
    return Object.entries(counts).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k, value: v }));
  })();

  return (
    <div className="space-y-6">

      {/* Group 1: adoption */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-ink-muted mb-2 pl-1">
          {t("overview.group.adoption")} <span className="text-ink-secondary">{t("overview.group.adoption.note")}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card topAccent accent="gblue"   title={t("overview.kpi.users")}         value={s ? String(s.human_users) : "—"} hint={t("overview.kpi.users.hint")} />
          <Card topAccent accent="ggreen"  title={t("overview.kpi.active")}        value={s ? String(s.power_users + s.active_consumers) : "—"} hint={s ? `POWER ${s.power_users} · ACTIVE ${s.active_consumers}` : undefined} />
          <Card topAccent accent="gyellow" title={t("overview.kpi.chat7d")}        value={s ? String(s.human_chat_turns_7d) : "—"} hint={t("overview.kpi.chat7d.hint")} />
          <Card topAccent accent="gred"    title={t("overview.kpi.conversations")} value={s ? String(s.conversations_captured) : "—"} hint={t("overview.kpi.conversations.hint")} />
        </div>
      </div>

      {/* Group 2: governance */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-ink-muted mb-2 pl-1">
          {t("overview.group.governance")} <span className="text-ink-secondary">{origin ? `(origin=${origin})` : t("overview.group.governance.all")}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card topAccent accent="info"  title={t("overview.kpi.admin")}       value={s ? String(s.admin_actions) : "—"} hint={t("overview.kpi.admin.hint")} />
          <Card topAccent accent="info"  title={t("overview.kpi.chat_total")}  value={s ? String(s.chat_turns_total) : "—"} hint={t("overview.kpi.chat_total.hint")} />
          <Card topAccent accent="info"  title={t("overview.kpi.data_access")} value={s ? String(s.data_access_calls) : "—"} hint={t("overview.kpi.data_access.hint")} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Persona donut */}
        <Panel title={t("overview.persona.title")} className="lg:col-span-1">
          {!persona.data ? <EmptyState title={t("common.loading")} /> : personaBuckets.length === 0 ? (
            <EmptyState title={t("common.empty")} hint={t("overview.persona.empty")} />
          ) : (
            <>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={personaBuckets}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={2}
                      stroke="rgb(var(--bg-surface))"
                      strokeWidth={2}
                    >
                      {personaBuckets.map((p) => (
                        <Cell key={p.name} fill={PERSONA_COLOR[p.name]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "rgb(var(--bg-surface))",
                        border: "1px solid rgb(var(--border-subtle))",
                        borderRadius: 8, fontSize: 12,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-3 space-y-1.5">
                {personaBuckets.map((p) => (
                  <li key={p.name} className="flex items-center text-xs">
                    <span className="w-2.5 h-2.5 rounded-sm mr-2" style={{ background: PERSONA_COLOR[p.name] }} />
                    <span className="text-ink-secondary truncate">{PERSONA_LABEL[p.name] ?? p.name}</span>
                    <span className="ml-auto text-ink-primary font-medium tabular-nums">{p.value}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        {/* DAU */}
        <Panel title={t("overview.dau.title")} className="lg:col-span-2">
          {!dau.data ? <EmptyState title={t("common.loading")} /> : dau.data.rows.length === 0 ? (
            <EmptyState title={t("overview.dau.empty")} />
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={[...dau.data.rows].reverse()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="d" fontSize={11} tickFormatter={(d) => String(d).slice(5)} />
                  <YAxis fontSize={11} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "rgb(var(--bg-surface))",
                      border: "1px solid rgb(var(--border-subtle))",
                      borderRadius: 8, fontSize: 12,
                    }}
                  />
                  <Bar dataKey="dau" name="DAU" fill="#4285F4" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="chat_turns" name="Chat turns" fill="#34A853" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>

      {/* App / Engine overview */}
      <Panel title={t("overview.engines.title")}>
        {!engines.data || !alive.data ? <EmptyState title={t("common.loading")} /> : (
          <div className="space-y-3">
            <div className="text-xs text-ink-muted">{t("overview.engines.alive")}: {alive.data.agent ?? 0} agent · {alive.data.datastore ?? 0} data store · {alive.data.engine ?? 0} engine</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {engines.data.rows.map((e: any) => (
                <div key={e.engine_id} className="bg-subtle/40 border border-border-subtle rounded-lg px-4 py-3">
                  <div className="text-sm font-medium text-ink-primary truncate">{e.engine_display_name ?? e.engine_id}</div>
                  <div className="text-[10px] font-mono text-ink-muted truncate">{e.engine_id}</div>
                  <div className="flex gap-4 mt-2 text-xs">
                    <span><span className="text-ink-muted">users</span> <span className="text-ggreen font-medium">{e.unique_users}</span></span>
                    <span><span className="text-ink-muted">chat</span> <span className="text-gblue">{e.chat_turns}</span></span>
                    <span><span className="text-ink-muted">events</span> <span className="text-ink-primary">{e.total_events}</span></span>
                  </div>
                </div>
              ))}
            </div>
            <div className="text-[11px] text-ink-muted">{t("overview.engines.hint")}</div>
          </div>
        )}
      </Panel>

      {/* Data freshness */}
      <Panel title={t("overview.freshness.title")}>
        {!s ? <EmptyState title={t("common.loading")} /> : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <FreshnessCard label={t("overview.freshness.admin")} ts={s.last_admin_event} />
            <FreshnessCard label={t("overview.freshness.data")}  ts={s.last_data_access_event} />
            <FreshnessCard label={t("overview.freshness.user")}  ts={s.last_user_activity_event} />
          </div>
        )}
      </Panel>
    </div>
  );
}

function FreshnessCard({ label, ts }: { label: string; ts: string | null }) {
  const mins = ts ? Math.round((Date.now() - new Date(ts).getTime()) / 60000) : null;
  const ago = mins == null ? "—" : (mins < 1 ? "<1m" : mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`);
  return (
    <div className="rounded-lg border border-border-subtle bg-subtle/50 px-4 py-3">
      <div className="text-[11px] text-ink-muted uppercase tracking-wider mb-1">{label}</div>
      <div className="text-base font-semibold text-ink-primary">{ago}</div>
      <div className="text-xs text-ink-muted mt-1 font-mono">{fmtTs(ts)}</div>
    </div>
  );
}
