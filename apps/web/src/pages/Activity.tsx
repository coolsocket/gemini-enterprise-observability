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
import { api, AdminActivityRow } from "../api";
import DataTable, { Col, fmtTs } from "../components/DataTable";
import { Panel, EmptyState } from "../components/Card";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useRange } from "../timerange";
import { ORIGIN_TAG } from "../tags";

const ACTION_TONE: Record<string, string> = {
  Create: "bg-ggreen/15 text-ggreen border-ggreen/30",
  Update: "bg-gblue/15  text-gblue  border-gblue/30",
  Delete: "bg-gred/15   text-gred   border-gred/30",
  Get:    "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
  List:   "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
};


function actionTone(action: string): string {
  for (const prefix of ["Create", "Update", "Delete", "Get", "List"]) {
    if (action.startsWith(prefix)) return ACTION_TONE[prefix];
  }
  return "bg-gyellow/15 text-gyellow border-gyellow/30";
}

export default function Activity() {
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const { range } = useRange();
  const q = useQuery({
    queryKey: ["v_admin_activity", origin, engineId, range],
    queryFn: () => api.view<AdminActivityRow>("v_admin_activity", origin, engineId, range),
  });

  const cols: Col<AdminActivityRow>[] = [
    { key: "timestamp", label: "时间", mono: true, render: (r) => fmtTs(r.timestamp), width: "180px" },
    {
      key: "action", label: "操作",
      render: (r) => (
        <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-medium border ${actionTone(r.action)}`}>{r.action}</span>
      ),
    },
    { key: "actor_email", label: "Actor", mono: true },
    {
      key: "origin", label: "Origin",
      render: (r) => (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${ORIGIN_TAG[r.origin ?? "UNKNOWN"]}`}>
          {r.origin ?? "—"}
        </span>
      ),
    },
    { key: "service", label: "Service", mono: true,
      render: (r) => <span className="text-ink-muted text-xs">{r.service}</span> },
    { key: "engine_display_name", label: "Engine",
      render: (r) => r.engine_display_name
        ? <span className="text-ink-secondary text-xs">{r.engine_display_name}</span>
        : <span className="text-ink-muted text-xs">{r.resource_type}/{r.resource_id ?? "—"}</span> },
    { key: "caller_ip", label: "IP", mono: true,
      render: (r) => <span className="text-ink-muted text-xs">{r.caller_ip ?? "—"}</span> },
  ];

  return (
    <div className="space-y-6">
      <Panel title={`管理操作时间线 ${origin ? `· ${origin}` : "· 全部"}`}>
        {!q.data ? <EmptyState title="加载中…" /> : (
          <DataTable rows={q.data.rows} cols={cols} filterKeys={["actor_email", "action", "resource_id", "full_method", "origin"]} />
        )}
      </Panel>
    </div>
  );
}
