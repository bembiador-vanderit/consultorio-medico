import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { User } from "../types/user";
import { getNavigationItems, navigationGroups, type AppView, type NavigationItem, type NavigationVisibilityResolver } from "../navigation/navigation";
import { Button, Drawer, IconButton } from "../ui";
import { NavigationIcon } from "./NavigationIcon";

export function Sidebar({ items, activeView, onNavigate }: { items: readonly NavigationItem[]; activeView: AppView; onNavigate: (view: AppView) => void }) {
  return <nav aria-label="Navegación principal" className="atlas-navigation">{navigationGroups.map((group) => {
    const entries = items.filter((item) => item.group === group.id);
    return entries.length > 0 && <div key={group.id} className="atlas-navigation-group"><p className="atlas-caption">{group.label}</p><ul>
      {entries.map((item) => <li key={item.id}><button type="button" aria-current={activeView === item.view ? "page" : undefined} onClick={() => onNavigate(item.view)}>
        <NavigationIcon name={item.icon} /><span>{item.label}</span>
      </button></li>)}
    </ul></div>;
  })}</nav>;
}

function AtlasMark() {
  return <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false"><path d="M24 41 7 24C-5 10 13-3 24 10 35-3 53 10 41 24Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /><path d="M4 24h10l5-10 7 20 5-10h13" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /></svg>;
}

function AccountMenu({ user, onSignOut }: { user: TopbarProps["user"]; onSignOut: () => void }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const trigger = useRef<HTMLElement>(null);
  const initials = user.full_name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("");
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => { if (event.target instanceof Node && ref.current && !ref.current.contains(event.target)) ref.current.open = false; };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  return <details ref={ref} className="atlas-account-menu" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null) && ref.current) ref.current.open = false; }} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); if (ref.current) ref.current.open = false; trigger.current?.focus(); } }}>
    <summary ref={trigger} aria-label={`Cuenta de ${user.full_name}`}><span className="atlas-account-avatar" aria-hidden="true">{initials}</span><div className="atlas-user"><p className="atlas-label">{user.full_name}</p><p className="atlas-help">{user.roles.map((role) => roleLabels[role] ?? role).join(" · ")}</p></div><span className="atlas-account-chevron" aria-hidden="true">⌄</span></summary>
    <div className="atlas-account-panel"><p className="atlas-label">{user.full_name}</p><p className="atlas-help">{user.roles.map((role) => roleLabels[role] ?? role).join(" · ")}</p>{Boolean(user.specialty_names?.length) && <p className="atlas-help">{user.specialty_names?.join(" · ")}</p>}<Button variant="ghost" onClick={() => { if (ref.current) ref.current.open = false; onSignOut(); }}>Cerrar sesión</Button></div>
  </details>;
}

type TopbarProps = { pageTitle: string; user: Pick<User, "full_name" | "roles" | "specialty_names">; activeCenterName?: string; notifications?: ReactNode; onOpenMenu: () => void; onSignOut: () => void; menuOpen: boolean; onOpenPatients?: () => void };
const roleLabels: Record<string, string> = { doctor: "Médico", secretary: "Secretaría", admin: "Administrador" };
export function Topbar({ pageTitle, user, activeCenterName, notifications, onOpenMenu, onSignOut, menuOpen, onOpenPatients }: TopbarProps) {
  return <header className="atlas-topbar"><div className="atlas-topbar-context"><IconButton label="Abrir navegación" variant="outline" className="atlas-mobile-menu" onClick={onOpenMenu} aria-expanded={menuOpen} aria-haspopup="dialog">☰</IconButton>
    <div className="atlas-topbar-title"><p className="atlas-card-title">{pageTitle}</p>{activeCenterName && <p className="atlas-help">{activeCenterName}</p>}</div><span className="atlas-mobile-brand"><AtlasMark /><strong>Atlas</strong></span>{onOpenPatients && <Button className="atlas-topbar-search" variant="outline" onClick={onOpenPatients}><NavigationIcon name="patient" />Buscar paciente</Button>}</div>
    <div className="atlas-topbar-account">{notifications}<AccountMenu user={user} onSignOut={onSignOut} /></div>
  </header>;
}

type ShellProps = Omit<TopbarProps, "onOpenMenu" | "menuOpen"> & { activeView: AppView; onNavigate: (view: AppView) => void; children: ReactNode; resolveVisibility?: NavigationVisibilityResolver };
export function AtlasAppShell({ activeView, onNavigate, children, resolveVisibility, ...topbar }: ShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const mainId = useId();
  const items = getNavigationItems(topbar.user, resolveVisibility);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (media.matches) setMobileOpen(false); };
    media.addEventListener("change", closeOnDesktop);
    return () => media.removeEventListener("change", closeOnDesktop);
  }, []);
  function navigate(view: AppView) { setMobileOpen(false); onNavigate(view); }
  const primaryViews: readonly AppView[] = ["dashboard", "appointments", "patients"];
  return <div className="atlas-root atlas-shell"><a className="atlas-skip-link" href={`#${mainId}`}>Saltar al contenido</a>
    <aside className="atlas-sidebar"><div className="atlas-brand"><span className="atlas-brand-mark"><AtlasMark /></span><div><strong>Atlas</strong><p className="atlas-help">Consultorio</p></div></div><Sidebar items={items} activeView={activeView} onNavigate={navigate} /><p className="atlas-sidebar-footer">Atlas Consultorio</p></aside>
    <div className="atlas-shell-body"><Topbar {...topbar} onOpenPatients={items.some((item) => item.view === "patients") ? () => navigate("patients") : undefined} menuOpen={mobileOpen} onOpenMenu={() => setMobileOpen(true)} /><main id={mainId} tabIndex={-1} className="atlas-main">{children}</main></div>
    <nav className="atlas-bottom-navigation" aria-label="Navegación móvil">{primaryViews.map((view) => { const item = items.find((entry) => entry.view === view); return item && <button key={view} type="button" aria-current={activeView === view ? "page" : undefined} onClick={() => navigate(view)}><NavigationIcon name={item.icon} /><span>{view === "dashboard" ? "Inicio" : item.label}</span></button>; })}<button type="button" aria-label="Más opciones" aria-haspopup="dialog" aria-expanded={mobileOpen} aria-current={!primaryViews.includes(activeView) ? "page" : undefined} onClick={() => setMobileOpen(true)}><span className="atlas-more-icon" aria-hidden="true">•••</span><span>Más</span></button></nav>
    <Drawer title="Atlas · Navegación" open={mobileOpen} onClose={() => setMobileOpen(false)}><Sidebar items={items} activeView={activeView} onNavigate={navigate} /></Drawer>
  </div>;
}
