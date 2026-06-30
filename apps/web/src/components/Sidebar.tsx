import { useState } from "react";
import { NavLink } from "react-router-dom";
import Brand from "./Brand";
import { useI18n } from "../i18n";
import {
  IChevronRight, ICog, IDashboard, ISearch,
  ITimeline, IUser, IWrench, IZap, IChat,
} from "./Icon";

type Item = { to: string; labelKey: string; icon: React.FC<{ className?: string }> };

const SECTIONS: { labelKey: string; items: Item[] }[] = [
  {
    labelKey: "nav.section.overview",
    items: [
      { to: "/overview", labelKey: "nav.overview", icon: IDashboard },
    ],
  },
  {
    labelKey: "nav.section.user",
    items: [
      { to: "/persona",       labelKey: "nav.persona",       icon: IUser },
      { to: "/user",          labelKey: "nav.user",          icon: IUser },
      { to: "/conversations", labelKey: "nav.conversations", icon: IChat },
      { to: "/builders",      labelKey: "nav.builders",      icon: IWrench },
    ],
  },
  {
    labelKey: "nav.section.resource",
    items: [
      { to: "/agents",      labelKey: "nav.agents",      icon: IWrench },
      { to: "/data-access", labelKey: "nav.data_access", icon: ISearch },
      { to: "/files",       labelKey: "nav.files",       icon: IZap },
    ],
  },
  {
    labelKey: "nav.section.audit",
    items: [
      { to: "/activity", labelKey: "nav.activity", icon: ITimeline },
      { to: "/raw",      labelKey: "nav.raw",      icon: IZap },
    ],
  },
];

const SETTINGS: Item = { to: "/settings", labelKey: "nav.settings", icon: ICog };

export default function Sidebar() {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem("ge-side") === "1"; } catch { return false; }
  });
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem("ge-side", next ? "1" : "0"); } catch {}
  };

  return (
    <aside
      className={`shrink-0 bg-surface border-r border-border-subtle flex flex-col sticky top-0 h-screen transition-all duration-200 ${
        collapsed ? "w-16" : "w-60"
      }`}
    >
      <div className="px-4 py-5 border-b border-border-subtle">
        <Brand collapsed={collapsed} />
      </div>
      <nav className="flex-1 overflow-y-auto py-3">
        {SECTIONS.map((sec) => (
          <div key={sec.labelKey} className="mb-3">
            {!collapsed && (
              <div className="px-4 pb-1 text-[11px] uppercase tracking-wider text-ink-muted">
                {t(sec.labelKey as any)}
              </div>
            )}
            {sec.items.map((it) => (
              <NavItem key={it.to} item={it} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </nav>
      <div className="border-t border-border-subtle py-2">
        <NavItem item={SETTINGS} collapsed={collapsed} />
        <button
          onClick={toggle}
          className="w-full px-4 py-2 mt-1 flex items-center gap-3 text-sm text-ink-muted hover:text-ink-primary rounded-md"
          title={t("nav.collapse")}
        >
          <IChevronRight className={`w-4 h-4 stroke-current shrink-0 transition-transform ${collapsed ? "" : "rotate-180"}`} />
          {!collapsed && <span>{t("nav.collapse")}</span>}
        </button>
      </div>
    </aside>
  );
}

function NavItem({ item, collapsed }: { item: Item; collapsed?: boolean }) {
  const { t } = useI18n();
  const Icon = item.icon;
  const label = t(item.labelKey as any);
  return (
    <NavLink
      to={item.to}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `relative flex items-center gap-3 mx-2 px-3 py-2 rounded-md text-sm transition-colors ${
          isActive
            ? "bg-subtle text-ink-primary font-medium"
            : "text-ink-secondary hover:text-ink-primary hover:bg-subtle/60"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r bg-accent" />}
          <Icon className="w-4 h-4 stroke-current shrink-0" />
          {!collapsed && <span className="truncate">{label}</span>}
        </>
      )}
    </NavLink>
  );
}
