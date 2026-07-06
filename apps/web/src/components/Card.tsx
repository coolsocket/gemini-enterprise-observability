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

type Accent = "default" | "success" | "info" | "warn" | "danger" | "accent"
  | "gblue" | "gred" | "gyellow" | "ggreen";

const ACCENT: Record<Accent, string> = {
  default: "text-ink-primary",
  success: "text-success",
  info:    "text-info",
  warn:    "text-warn",
  danger:  "text-danger",
  accent:  "text-accent",
  gblue:   "text-gblue",
  gred:    "text-gred",
  gyellow: "text-gyellow",
  ggreen:  "text-ggreen",
};

const ACCENT_BAR: Record<Accent, string> = {
  default: "bg-ink-muted",
  success: "bg-success",
  info:    "bg-info",
  warn:    "bg-warn",
  danger:  "bg-danger",
  accent:  "bg-accent",
  gblue:   "bg-gblue",
  gred:    "bg-gred",
  gyellow: "bg-gyellow",
  ggreen:  "bg-ggreen",
};

export default function Card({
  title, value, hint, accent = "default", topAccent,
}: {
  title: string;
  value: string;
  hint?: string;
  accent?: Accent;
  topAccent?: boolean;
}) {
  return (
    <div className="bg-surface rounded-xl border border-border-subtle shadow-card overflow-hidden">
      {topAccent && <div className={`h-1 ${ACCENT_BAR[accent]}`} />}
      <div className="p-5">
        <div className="text-ink-muted text-[11px] uppercase tracking-wider mb-1.5">{title}</div>
        <div className={`text-2xl font-semibold tracking-tight ${ACCENT[accent]}`}>{value}</div>
        {hint && <div className="text-ink-muted text-xs mt-1.5">{hint}</div>}
      </div>
    </div>
  );
}

export function Panel({
  title, action, children, className = "",
}: {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`bg-surface rounded-xl border border-border-subtle shadow-card ${className}`}>
      {title && (
        <div className="px-5 pt-4 pb-3 flex items-center justify-between border-b border-border-subtle">
          <h2 className="text-[11px] uppercase tracking-wider text-ink-muted">{title}</h2>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="py-12 text-center">
      <div className="text-ink-secondary text-sm">{title}</div>
      {hint && <div className="text-ink-muted text-xs mt-1">{hint}</div>}
    </div>
  );
}
