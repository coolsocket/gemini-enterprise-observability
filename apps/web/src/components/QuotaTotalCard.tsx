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

// One "today total" / "window total" card on the Quota page.
// Extracted 2026-07-10 (R3c) — was defined inline in Quota.tsx.
// Owns nothing but its layout: caller supplies label/hint/color via the
// featureMeta prop so the page keeps the FEATURE_META registry local.

export type FeatureMeta = {
  label: string;
  icon: string;
  color: string;
  hint: string;
};

export function QuotaTotalCard({
  featureMeta,
  total,
  used,
  users,
  over_quota_users,
  overall_utilization,
}: {
  featureMeta: FeatureMeta;
  total: number;
  used: number;
  users: number;
  over_quota_users: number;
  overall_utilization: number | null;
}) {
  const util = overall_utilization ?? 0;
  // Color follows utilization: red ≥90%, yellow ≥60%, green otherwise.
  const barColor = util >= 0.9 ? "bg-gred/60"
                 : util >= 0.6 ? "bg-gyellow/60"
                               : "bg-ggreen/60";
  return (
    <div className="rounded-lg border border-border-subtle bg-surface p-3">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-lg">{featureMeta.icon}</span>
        <span className={`text-sm font-semibold ${featureMeta.color}`}>{featureMeta.label}</span>
      </div>
      <div className="text-[10px] text-ink-muted mb-2">{featureMeta.hint}</div>
      <div className="flex items-baseline gap-1.5 mb-1">
        <span className="text-2xl font-semibold text-ink-primary tabular-nums">{used}</span>
        <span className="text-sm text-ink-muted">/ {total}</span>
        <span className="text-[11px] text-ink-muted ml-auto tabular-nums">
          {`${Math.round(util * 100)}%`}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-subtle overflow-hidden">
        <div className={`h-full ${barColor} transition-all`}
             style={{ width: `${Math.min(100, util * 100)}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-ink-muted mt-1.5">
        <span>{users} seats</span>
        {over_quota_users > 0 && <span className="text-gred">{over_quota_users} 超额</span>}
      </div>
    </div>
  );
}
