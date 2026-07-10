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
import { useMemo, useState } from "react";
import { api, PersonaRow, LicensedUser } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";
import { useRange } from "../timerange";
import { ORIGIN_TAG, PERSONA_TAG } from "../tags";



export default function Persona() {
  const { origin } = useOrigin();
  const { range } = useRange();
  const q = useQuery({
    // v_user_persona doesn't have engine_id column, so don't filter by engineId
    queryKey: ["v_user_persona", origin, range],
    queryFn: () => api.view<PersonaRow>("v_user_persona", origin, null, range),
  });
  const licensed = useQuery({
    queryKey: ["persona-licensed-users"],
    queryFn:  () => api.personaLicensedUsers(),
    // Poll rarely — hitting DE for 300+ rows every focus is wasteful.
    staleTime: 5 * 60_000,
  });

  const [licensedFilter, setLicensedFilter] = useState<"all" | "unseen" | "blocked">("all");
  const licensedRows = useMemo(() => {
    const rows = licensed.data?.users ?? [];
    if (licensedFilter === "unseen") {
      return rows.filter(u => u.state === "ASSIGNED" && !u.last_login_time);
    }
    if (licensedFilter === "blocked") {
      // "想用但被挡" — tried to log in, DE returned no-license. This IS
      // a positive demand signal: someone navigated to GE. Higher urgency
      // than "assigned but hasn't logged in yet".
      return rows.filter(u => u.state === "NO_LICENSE_ATTEMPTED_LOGIN")
                 .sort((a, b) => (b.last_login_time ?? "").localeCompare(a.last_login_time ?? ""));
    }
    // "all" — sort: blocked first (demand signal, most actionable),
    // then unseen (paid seat wasted), then most-recently-active desc.
    return [...rows].sort((a, b) => {
      const rank = (u: LicensedUser) => {
        if (u.state === "NO_LICENSE_ATTEMPTED_LOGIN") return 0;
        if (u.state === "ASSIGNED" && !u.last_login_time) return 1;
        return 2;
      };
      const ra = rank(a), rb = rank(b);
      if (ra !== rb) return ra - rb;
      return (b.last_login_time ?? "").localeCompare(a.last_login_time ?? "");
    });
  }, [licensed.data, licensedFilter]);

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

      <Panel title={`用户画像 · 已观察到的活跃用户 ${origin ? `· 只看 ${origin}` : "· 全部 origin"} · ${q.data?.count ?? "…"} 人`}>
        <div className="text-[10px] text-ink-muted mb-2">
          来源: v_user_persona (由 gen_ai / audit 日志推导)。
          只有事件里出现过的用户会在这里。买了 seat 但从没打开 GE 的人在下面 "订阅接口" 面板。
        </div>
        {!q.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={q.data.rows} cols={cols} filterKeys={["user", "persona", "origin"]} />
        )}
      </Panel>

      {/* Licensed roster from Discovery Engine userLicenses API */}
      <Panel
        title={
          licensed.data
            ? `订阅接口 · 全量购买 seat 用户 · ${licensed.data.count}`
              + ` (${licensed.data.assigned_count} 已分配 · ${licensed.data.unseen_count} 未曾登录 · ${licensed.data.blocked_count} 想用但被挡)`
            : "订阅接口 · 全量购买 seat 用户 · 加载中…"
        }
        action={
          licensed.data && licensed.data.count > 0 && (
            <div className="flex items-center gap-1 text-[10px]">
              {(["all", "unseen", "blocked"] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setLicensedFilter(f)}
                  className={`h-6 px-2 rounded ${licensedFilter === f
                    ? "bg-info/15 text-info border border-info/30 font-medium"
                    : "text-ink-muted hover:text-ink-secondary border border-transparent"}`}
                  title={
                    f === "blocked"
                      ? "NO_LICENSE_ATTEMPTED_LOGIN — 用户点开 GE 页面, DE 发现没 license, 拒了并把这次尝试记下来。这是最强的采纳需求信号。"
                      : f === "unseen"
                      ? "ASSIGNED · 无 last_login — 有 seat 但从未打开过。可以推动 onboarding, 或收回 seat 释放给别人。"
                      : "全部行, 排序: 想用但被挡 → 未曾登录 → 最近登录"
                  }
                >
                  {f === "all"     ? "全部" :
                   f === "unseen"  ? `未曾登录 (${licensed.data.unseen_count})` :
                                     `想用但被挡 (${licensed.data.blocked_count})`}
                </button>
              ))}
            </div>
          )
        }
      >
        <div className="text-[10px] text-ink-muted mb-3 space-y-1">
          <div>
            来源: Discovery Engine v1alpha <code className="bg-subtle px-1 rounded">userLicenses</code> API.
            <b>userPrincipal</b> 在 Workspace 租户是邮箱; 在 OIDC/WIF 租户 (如 vivo) 是数字 subject ID.
          </div>
          {licensed.data && licensed.data.blocked_count > 0 && (
            <div className="text-warn">
              ⚠ 有 <b>{licensed.data.blocked_count}</b> 个人打开了 GE 但因为没 license 被挡。他们是<b>最强的采纳需求信号</b> — 优先看这批。
            </div>
          )}
        </div>
        {!licensed.data ? <EmptyState title="加载中…" /> :
         licensed.data.count === 0 ? (
          <EmptyState
            title="没有订阅数据"
            hint={licensed.data.note ?? "此租户 userLicenses API 返回空,或该环境未启用 DE 订阅."}
          />
        ) : licensedRows.length === 0 ? (
          <EmptyState
            title={licensedFilter === "blocked" ? "无想用但被挡的用户 🎉" : "无未曾登录用户 🎉"}
            hint={licensedFilter === "blocked" ? "所有想用的人都有 seat" : "所有 seat 都被至少用了一次"}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-muted border-b border-border-subtle/40">
                  <th className="py-1.5 pr-3 font-normal">User Principal</th>
                  <th className="py-1.5 pr-3 font-normal">状态</th>
                  <th className="py-1.5 pr-3 font-normal">最近登录</th>
                  <th className="py-1.5 pr-3 font-normal">分配时间</th>
                  <th className="py-1.5 pr-3 font-normal">License Config</th>
                </tr>
              </thead>
              <tbody>
                {licensedRows.slice(0, 500).map((u: LicensedUser) => {
                  const unseen = u.state === "ASSIGNED" && !u.last_login_time;
                  const blocked = u.state === "NO_LICENSE_ATTEMPTED_LOGIN";
                  const rowBg = blocked ? "bg-gred/5" : unseen ? "bg-warn/5" : "";
                  const stateTag =
                    u.state === "ASSIGNED"                   ? "bg-ggreen/10 text-ggreen border-ggreen/30" :
                    u.state === "NO_LICENSE_ATTEMPTED_LOGIN" ? "bg-gred/10   text-gred   border-gred/30"   :
                                                                "bg-ink-muted/10 text-ink-muted border-ink-muted/30";
                  return (
                    <tr key={u.user_principal}
                        className={`border-b border-border-subtle/20 hover:bg-subtle/30 ${rowBg}`}>
                      <td className="py-1 pr-3 font-mono text-ink-primary">{u.user_principal || "(空)"}</td>
                      <td className="py-1 pr-3">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border ${stateTag}`}>{u.state}</span>
                        {blocked && (
                          <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border border-gred/40 bg-gred/10 text-gred"
                                title="打开了 GE 页面, 但没被分配 license, 被 DE 拦了。是最强的采纳需求信号 — 考虑给他们分个 seat。">
                            想用但被挡
                          </span>
                        )}
                        {unseen && (
                          <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border border-warn/30 bg-warn/10 text-warn"
                                title="有 seat 但从未登录 — 可以撤销 seat 或推动 onboarding">
                            未曾登录
                          </span>
                        )}
                      </td>
                      <td className="py-1 pr-3 font-mono text-ink-muted">
                        {u.last_login_time ? fmtTs(u.last_login_time) : "—"}
                      </td>
                      <td className="py-1 pr-3 font-mono text-ink-muted">
                        {u.create_time ? fmtTs(u.create_time) : "—"}
                      </td>
                      <td className="py-1 pr-3 font-mono text-ink-muted"
                          title={u.license_config ?? "-"}>
                        {u.license_config ? u.license_config.slice(0, 8) + "…" : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {licensedRows.length > 500 && (
              <div className="text-[10px] text-ink-muted mt-2 text-center">
                显示前 500 / {licensedRows.length} 行 · 用过滤器缩窄
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
