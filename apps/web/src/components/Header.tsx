import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { IChip, IMoon, IRefresh, ISun } from "./Icon";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";
import { useI18n, type Locale } from "../i18n";
import { api, type Origin } from "../api";

const ROUTE_KEYS: Record<string, string> = {
  "/overview":      "overview",
  "/conversations": "conversations",
  "/persona":       "persona",
  "/builders":      "builders",
  "/data-access":   "data_access",
  "/files":         "files",
  "/activity":      "activity",
  "/raw":           "raw",
  "/settings":      "settings",
};

function StatusBadge({ ok }: { ok: boolean }) {
  const { t } = useI18n();
  return (
    <div className={`inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border text-xs ${
      ok
        ? "border-success/30 bg-success-bg/40 text-success"
        : "border-danger/30 bg-danger-bg/40 text-danger"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-success animate-pulse-dot" : "bg-danger"}`} />
      {ok ? t("header.live") : t("header.offline")}
    </div>
  );
}

function LangToggle() {
  const { locale, setLocale } = useI18n();
  const opts: { val: Locale; label: string }[] = [
    { val: "zh", label: "中" },
    { val: "en", label: "EN" },
  ];
  return (
    <div className="inline-flex items-center h-8 rounded-md border border-border-subtle bg-surface overflow-hidden text-xs">
      {opts.map((o) => (
        <button
          key={o.val}
          onClick={() => setLocale(o.val)}
          className={`px-2.5 h-full transition-colors font-medium ${
            locale === o.val
              ? "bg-accent text-ink-inverse"
              : "text-ink-secondary hover:text-ink-primary"
          }`}
          title={`Switch to ${o.label}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<string>(() => document.documentElement.getAttribute("data-theme") ?? "dark");
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("ge-theme", next); } catch {}
    setTheme(next);
  };
  return (
    <button
      onClick={flip}
      title={theme === "dark" ? "切到亮色" : "切到暗色"}
      className="w-8 h-8 inline-flex items-center justify-center rounded-md border border-border-subtle bg-surface text-ink-secondary hover:text-ink-primary hover:border-border-default transition-colors"
    >
      {theme === "dark" ? <ISun /> : <IMoon />}
    </button>
  );
}

function OriginToggle() {
  const { origin, setOrigin } = useOrigin();
  const { t } = useI18n();
  const qc = useQueryClient();
  const opts: { val: Origin; label: string }[] = [
    { val: null,         label: t("header.origin.all") },
    { val: "HUMAN",      label: t("header.origin.human") },
    { val: "SIMULATED",  label: t("header.origin.simulated") },
    { val: "AUTOMATION", label: t("header.origin.automation") },
  ];
  const pick = (v: Origin) => {
    setOrigin(v);
    qc.invalidateQueries();
  };
  return (
    <div className="inline-flex items-center h-8 rounded-md border border-border-subtle bg-surface overflow-hidden text-xs">
      {opts.map((o) => (
        <button
          key={String(o.val)}
          onClick={() => pick(o.val)}
          className={`px-2.5 h-full transition-colors ${
            origin === o.val
              ? "bg-accent text-ink-inverse font-medium"
              : "text-ink-secondary hover:text-ink-primary hover:bg-subtle"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function useFmtAgo() {
  const { locale } = useI18n();
  return (iso: string | null | undefined): string => {
    if (!iso) return "—";
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (locale === "en") {
      if (mins < 1) return "just now";
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.round(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      return `${Math.round(hrs / 24)}d ago`;
    }
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins} 分钟前`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} 小时前`;
    return `${Math.round(hrs / 24)} 天前`;
  };
}

function EngineSelector() {
  const { engineId, setEngineId } = useEngine();
  const { t } = useI18n();
  const qc = useQueryClient();
  const engines = useQuery({ queryKey: ["engines"], queryFn: api.engines });
  const [open, setOpen] = useState(false);

  const list = engines.data?.engines ?? [];
  const current = list.find((e) => e.id === engineId);
  const label = current ? current.name : t("header.engine.all");

  const pick = (id: string | null) => {
    setEngineId(id);
    setOpen(false);
    qc.invalidateQueries();
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border text-xs transition-colors ${
          engineId
            ? "border-info/40 bg-info-bg/30 text-info"
            : "border-border-subtle bg-surface text-ink-secondary hover:text-ink-primary"
        }`}
        title="选择 GE engine / app"
      >
        <IChip className="w-3.5 h-3.5 stroke-current shrink-0" />
        <span className="truncate max-w-[160px]">{label}</span>
        <span className="text-ink-muted">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 min-w-[280px] bg-surface border border-border-subtle rounded-md shadow-card overflow-hidden">
          <button
            onClick={() => pick(null)}
            className={`w-full text-left px-3 py-2 text-xs hover:bg-subtle ${!engineId ? "bg-subtle text-ink-primary font-medium" : "text-ink-secondary"}`}
          >
            {t("header.engine.all")}
          </button>
          <div className="border-t border-border-subtle" />
          {list.map((e) => (
            <button
              key={e.id}
              onClick={() => pick(e.id)}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-subtle ${engineId === e.id ? "bg-subtle text-ink-primary font-medium" : "text-ink-secondary"}`}
            >
              <div>{e.name}</div>
              <div className="text-[10px] text-ink-muted font-mono">{e.id}</div>
              {e.type && <div className="text-[10px] text-ink-muted">{e.type.replace("SOLUTION_TYPE_", "")}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RefreshButton() {
  const { t } = useI18n();
  const fmtAgo = useFmtAgo();
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["refresh-status"],
    queryFn: api.refreshStatus,
    refetchInterval: 30_000,
  });
  const m = useMutation({
    mutationFn: api.refreshNow,
    onSuccess: () => qc.invalidateQueries(),
  });
  const lastRefresh = status.data?.last_refresh;
  const isOk = !m.isError;

  return (
    <div className="inline-flex items-center gap-1 h-8 px-2.5 rounded-md border border-border-subtle bg-surface text-xs">
      <span className="text-ink-muted">{t("header.snapshot")}:</span>
      <span className="text-ink-secondary">{fmtAgo(lastRefresh)}</span>
      <button
        onClick={() => m.mutate()}
        disabled={m.isPending}
        title={t("header.refresh")}
        className={`ml-1 w-6 h-6 inline-flex items-center justify-center rounded ${
          isOk ? "text-ink-secondary hover:text-ink-primary" : "text-danger"
        } disabled:opacity-60 disabled:cursor-wait`}
      >
        <span className={m.isPending ? "animate-spin inline-flex" : "inline-flex"}>
          <IRefresh />
        </span>
      </button>
    </div>
  );
}

export default function Header() {
  const { t } = useI18n();
  const loc = useLocation();
  const routeKey = ROUTE_KEYS[loc.pathname] ?? "";
  const meta = routeKey
    ? { title: t(`route.${routeKey}.title` as any), subtitle: t(`route.${routeKey}.subtitle` as any) }
    : { title: "", subtitle: "" };
  const [healthOk, setHealthOk] = useState(true);
  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      try {
        const r = await fetch("/api/healthz");
        if (!cancelled) setHealthOk(r.ok);
      } catch {
        if (!cancelled) setHealthOk(false);
      }
    };
    ping();
    const id = setInterval(ping, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <header className="px-8 pt-6 pb-4 flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold text-ink-primary tracking-tight">{meta.title}</h1>
        <p className="text-sm text-ink-muted mt-0.5">{meta.subtitle}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <StatusBadge ok={healthOk} />
        <EngineSelector />
        <OriginToggle />
        <LangToggle />
        <ThemeToggle />
        <RefreshButton />
      </div>
    </header>
  );
}
