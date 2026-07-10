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

// Thin fetch wrapper around /api/*

export type ViewMeta = { name: string; label: string; desc: string };

export type Meta = {
  project: string;
  dataset: string;
  sink_name: string;
  views: ViewMeta[];
};

export type Summary = {
  // 采纳与质量（HUMAN + SIMULATED）
  human_users: number;
  power_users: number;
  active_consumers: number;
  trial_users: number;
  human_builders: number;
  explorers: number;
  lurkers: number;
  human_chat_turns_7d: number;
  conversations_captured: number;
  // 治理与审计
  admin_actions: number;
  chat_turns_total: number;
  data_access_calls: number;
  engines_tracked: number;
  // 数据新鲜度
  last_admin_event: string | null;
  last_data_access_event: string | null;
  last_user_activity_event: string | null;
};

export type ConversationWithResponseRow = {
  timestamp: string;
  actor_email: string;
  origin: Origin;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  prompt: string;
  session_id: string | null;
  prompt_trace_id: string;
  response_trace_id: string | null;
  response_text: string | null;
  reasoning_text: string | null;
  response_status: string | null;
  chunk_count: number | null;
  join_status: "matched" | "no_response";
};

export type ViewResponse<T = Record<string, unknown>> = {
  view: string;
  rows: T[];
  count: number;
};

export type PersonaRow = {
  user: string;
  origin: Origin;
  persona: Persona;
  chat_turns_total: number;
  chat_turns_7d: number;
  sessions_total: number;
  resources_created: number;
  agents_created: number;
  engines_created: number;
  datastores_created: number;
  first_seen: string | null;
  last_seen: string | null;
};

export type AdminActivityRow = {
  timestamp: string;
  actor_email: string;
  origin: Origin;
  action: string;
  service: string;
  resource_type: string | null;
  resource_id: string | null;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  full_resource: string;
  full_method: string;
  caller_ip: string | null;
  receiveTimestamp: string | null;
};

export type BuilderRow = {
  actor_email: string;
  origin: Origin;
  agents_created: number;
  agents_deleted: number;
  agents_alive: number;
  engines_created: number;
  engines_deleted: number;
  engines_alive: number;
  datastores_created: number;
  datastores_deleted: number;
  datastores_alive: number;
  update_actions: number;
  total_admin_actions: number;
  first_admin_action: string;
  last_admin_action: string;
};

export type EngineRow = {
  engine_id: string;
  engine_display_name: string | null;
  unique_users: number;
  chat_turns: number;
  sessions: number;
  total_events: number;
};

export type DauRow = {
  d: string;
  dau: number;
  total_events: number;
  turns: number;
};

export type DataAccessRow = {
  timestamp: string;
  actor_email: string;
  origin: Origin;
  action: string;
  service: string;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  datastore_id: string | null;
  full_resource: string;
  full_method: string;
  caller_ip: string | null;
};

export type DataAccessSummaryRow = {
  actor_email: string;
  origin: Origin;
  engine_id: string | null;
  engine_display_name: string | null;
  chat_turns: number;
  deep_research_calls: number;
  notebooklm_notebook_ops: number;
  notebooklm_content_ops: number;
  notebooklm_audio_ops: number;
  a2a_invocations: number;
  autocomplete_calls: number;
  session_ops: number;
  feedback_events: number;
  programmatic_searches: number;
  session_files: number;
  canned_queries: number;
  other: number;
  total_data_access: number;
  first_access: string;
  last_access: string;
};

export type AgentspaceNavRow = {
  actor_email: string;
  origin: Origin;
  page_type: "home" | "agent_gallery" | "agent" | "deep-research" | "notebook-lm";
  agent_id: string | null;
  agent_name: string | null;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  visits: number;
  first_visit: string;
  last_visit: string;
};

export type AgentspaceNavSummaryRow = {
  actor_email: string;
  origin: Origin;
  home_visits: number;
  gallery_visits: number;
  deep_research_visits: number;
  notebooklm_visits: number;
  custom_agent_visits: number;
  distinct_custom_agents: number;
  custom_agent_names: string | null;
  total_navigation_events: number;
  last_visit: string;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${path}`);
  return (await r.json()) as T;
}

export type Origin = "HUMAN" | "AUTOMATION" | "UNKNOWN" | "SIMULATED" | null;

export type Persona =
  | "POWER_USER" | "ACTIVE_CONSUMER" | "TRIAL"
  | "BUILDER" | "EXPLORER" | "LURKER" | "AUTOMATION";

export type RefreshStatus = {
  snapshots: Array<{
    snapshot_name: string;
    source_view: string;
    refreshed_at: string;
    row_count: number;
    refresh_seconds: number;
    triggered_by: string;
  }>;
  last_refresh: string | null;
  snapshot_count: number;
  data_earliest: string | null;   // MIN(timestamp) across sink tables
  data_latest:   string | null;   // MAX(timestamp)
  data_days:     number | null;   // (latest - earliest) / 1 day
  note?:         string;
};

export type QuotaConfig = Record<string, { value: string; updated_at: string | null; updated_by: string | null }>;

export type EngineInfo = { id: string; name: string; type: string | null };
export type EngineListResponse = { engines: EngineInfo[] };
export type AliveResources = { agent?: number; datastore?: number; engine?: number };

export type SessionFileRow = {
  actor_email: string;
  origin: Origin;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  session_id: string;
  list_calls: number;
  download_calls: number;
  total_file_ops: number;
  first_op: string;
  last_op: string;
  file_activity_signal: "confirmed" | "likely" | "unknown";
};

export type AgentUsageRow = {
  agent_id: string;
  assistant_id: string;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  traces: number;
  chunks: number;
};

export type ConversationRow = {
  timestamp: string;
  trace_id: string;
  actor_email: string;
  origin: Origin;
  engine_id_raw: string | null;
  engine_display_name: string | null;
  prompt: string;
  session_id: string | null;
  state: string | null;
  assist_token: string | null;
};

export type ChoiceRow = {
  timestamp: string;
  trace_id: string;
  engine_id_raw: string | null;
  agent_id: string | null;
  finish_reason: string | null;
  response_text: string | null;
  reasoning_text: string | null;
  part_count: number;
};

async function post<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: "POST" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${path}`);
  return (await r.json()) as T;
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? "?" + parts.join("&") : "";
}

// Kinds emitted by apps/api/contexts/observability/domain/identity.py.
// Keep in sync with IdentityKind enum there.
export type IdentityKind =
  | "google_email"
  | "oidc_wif_okta"
  | "oidc_wif_azure"
  | "oidc_wif_generic"
  | "oidc_subject"
  | "service_account"
  | "simulated"
  | "unknown";

export type UserListEntry = {
  actor_email: string;
  origin: Origin;
  persona: Persona | null;
  identity_kind: IdentityKind;
  is_human: boolean;
  chat_turns: number;
  deep_research_calls: number;
  notebooklm_ops: number;
  a2a_invocations: number;
  programmatic_searches: number;
  session_files: number;
  custom_agent_visits: number;
  distinct_custom_agents: number;
  engines_touched: number;
  total_data_access: number;
  last_access: string | null;
};

export type UserDeepDive = {
  actor_email: string;
  identity: {
    kind: IdentityKind;
    actor_id: string;
    display: string;
    is_human: boolean;
  };
  persona: PersonaRow[];
  data_access_summary: DataAccessSummaryRow[];
  agentspace_summary: AgentspaceNavSummaryRow[];
  agentspace_detail: AgentspaceNavRow[];
  conversations: Array<{
    timestamp: string;
    prompt: string;
    response_text: string | null;
    engine_display_name: string | null;
    join_status: "matched" | "no_response";
  }>;
  builder: BuilderRow[];
  admin_events: Array<{
    timestamp: string;
    action: string;
    service: string | null;
    resource_type: string | null;
    resource_id: string | null;
  }>;
  data_access_events: Array<{
    timestamp: string;
    action: string;
    service: string | null;
    engine_id_raw: string | null;
    datastore_id: string | null;
    full_method: string;
  }>;
  // Per-feature drill-down arrays (each guaranteed complete, not subsampled by autocomplete noise)
  dr_events: Array<{ timestamp: string; action: string; full_method: string }>;
  notebooklm_events: Array<{ timestamp: string; action: string; full_method: string }>;
  a2a_events: Array<{ timestamp: string; action: string; full_method: string }>;
  chat_events: Array<{ timestamp: string; action: string; full_method: string }>;
  session_files: SessionFileRow[];
  agentspace_events: Array<{
    timestamp: string;
    page_type: string;
    agent_id: string | null;
    agent_name: string | null;
  }>;
  dr_prompts: Array<{
    dr_ts: string;
    dr_action: string;
    attributed_prompt: string | null;
    prompt_ts: string | null;
    attribution_delta_sec: number | null;
    engine_display_name: string | null;
  }>;
  custom_agent_prompts: Array<{
    prompt_ts: string;
    agent_id: string;
    agent_name: string | null;
    agent_open_ts: string;
    elapsed_since_open_sec: number;
    prompt: string;
    engine_display_name: string | null;
  }>;
};

export type AgentDirectoryRow = {
  agent_id: string;
  agent_name: string;
  agent_type: "built-in" | "custom";
  signal_kind: "api_calls" | "page_opens";
  total: number;
  unique_users: number;
  top_user_email: string | null;
  top_user_value: number | null;
  last_activity: string | null;
};

export type AgentDeepDive = {
  agent_id: string;
  directory: AgentDirectoryRow | null;
  users: Array<{ actor_email: string; origin: Origin; calls: number; last_seen: string | null }>;
  events: Array<{
    timestamp: string;
    action: string;
    actor_email: string;
    full_method?: string;
    engine_id_raw?: string | null;
    agent_id?: string | null;
  }>;
  prompts: Array<{
    event_ts: string;
    actor_email: string;
    prompt: string;
    engine_display_name?: string | null;
    // Deep Research specific
    dr_action?: string;
    attribution_delta_sec?: number;
    // Custom agent specific
    elapsed_since_open_sec?: number;
    agent_open_ts?: string;
  }>;
};

export type QuotaTotalRow = {
  feature: string;
  eligible_users: number;
  total_daily_quota: number;
  total_used_today: number;
  overall_utilization: number | null;
  users_over_quota: number;
};

export type QuotaUtilizationRow = {
  actor_email: string;
  tier: "standard" | "plus";
  feature: string;
  daily_limit: number;
  used_today: number;
  utilization: number;
  over_quota: boolean;
};

export type UserTierRow = {
  actor_email: string;
  tier: "standard" | "plus";
  notes: string | null;
  assigned_at: string | null;
  assigned_by: string | null;
};

export type LicensedUser = {
  user_principal: string;      // email for Workspace tenants, numeric subject for OIDC/WIF
  state: string;               // ASSIGNED / UNASSIGNED / ...
  license_config: string | null;
  create_time: string | null;
  update_time: string | null;
  last_login_time: string | null;
};
export type LicensedUsers = {
  users: LicensedUser[];
  count: number;
  assigned_count: number;
  unseen_count: number;
  note?: string;
};

export type QuotaOverview = {
  today_ca: string;
  window_days: number;
  totals: QuotaTotalRow[];
  utilization: QuotaUtilizationRow[];
  tiers: UserTierRow[];
  config: Array<{ key: string; value: string }>;
  recent: Array<{ d: string; actor_email: string; feature: string; n: number }>;
};

export const api = {
  healthz: () => get<{ status: string; project: string; dataset: string }>("/api/healthz"),
  meta:    () => get<Meta>("/api/meta"),
  engines: () => get<EngineListResponse>("/api/engines"),
  aliveResources: () => get<AliveResources>("/api/resources/alive"),
  summary: (origin?: Origin, engineId?: string | null, sinceHours?: number | null) =>
    get<Summary>(`/api/summary${qs({ origin, engine_id: engineId, since_hours: sinceHours })}`),
  view:    <T = Record<string, unknown>>(name: string, origin?: Origin, engineId?: string | null, sinceHours?: number | null) =>
    get<ViewResponse<T>>(`/api/v/${encodeURIComponent(name)}${qs({ origin, engine_id: engineId, since_hours: sinceHours })}`),
  users:   (sinceHours?: number | null) => get<{ users: UserListEntry[]; count: number }>(`/api/users${qs({ since_hours: sinceHours })}`),
  user:    (email: string) => get<UserDeepDive>(`/api/user/${encodeURIComponent(email)}`),
  agents:  () => get<{ agents: AgentDirectoryRow[]; count: number }>("/api/agents"),
  agent:   (agentId: string) => get<AgentDeepDive>(`/api/agent/${encodeURIComponent(agentId)}`),
  refreshStatus: () => get<RefreshStatus>("/api/refresh/status"),
  refreshNow:    () => post<{ refreshed: any[]; ok_count: number }>("/api/refresh?triggered_by=ui"),
  quotaConfig:   () => get<QuotaConfig>("/api/quota/config"),
  quotaSet:      (key: string, value: string) =>
    post<{ key: string; value: string; ok: boolean }>(`/api/quota/config?key=${encodeURIComponent(key)}&value=${encodeURIComponent(value)}&by=ui`),
  quotaOverview: (windowDays: 1 | 7 | 30 = 1) =>
    get<QuotaOverview>(`/api/quota/overview?window_days=${windowDays}`),
  personaLicensedUsers: () => get<LicensedUsers>("/api/persona/licensed_users"),
  quotaSetTier:  (email: string, tier: "standard" | "plus", notes = "") =>
    post<{ email: string; tier: string; ok: boolean }>(`/api/quota/tier?email=${encodeURIComponent(email)}&tier=${tier}&by=ui&notes=${encodeURIComponent(notes)}`),
};
