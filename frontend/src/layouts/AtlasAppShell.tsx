import { useEffect, useId, useState, type ReactNode } from "react";
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

type TopbarProps = { pageTitle: string; user: Pick<User, "full_name" | "roles" | "specialty_names">; activeCenterName?: string; notifications?: ReactNode; onOpenMenu: () => void; onSignOut: () => void; menuOpen: boolean };
const roleLabels: Record<string, string> = { doctor: "Médico", secretary: "Secretaría", admin: "Administrador" };
export function Topbar({ pageTitle, user, activeCenterName, notifications, onOpenMenu, onSignOut, menuOpen }: TopbarProps) {
  return <header className="atlas-topbar"><div className="atlas-topbar-context"><IconButton label="Abrir navegación" variant="outline" className="atlas-mobile-menu" onClick={onOpenMenu} aria-expanded={menuOpen} aria-haspopup="dialog">☰</IconButton>
    <div><p className="atlas-card-title">{pageTitle}</p>{activeCenterName && <p className="atlas-help">{activeCenterName}</p>}</div></div>
    <div className="atlas-topbar-account">{notifications}<div className="atlas-user"><p className="atlas-label">{user.full_name}</p><p className="atlas-help">{user.roles.map((role) => roleLabels[role] ?? role).join(" · ")}</p>{Boolean(user.specialty_names?.length) && <p className="atlas-help">{user.specialty_names?.join(" · ")}</p>}</div>
      <Button variant="outline" size="sm" onClick={onSignOut}>Cerrar sesión</Button></div>
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
  return <div className="atlas-root atlas-shell"><a className="atlas-skip-link" href={`#${mainId}`}>Saltar al contenido</a>
    <aside className="atlas-sidebar"><div className="atlas-brand"><span className="atlas-brand-mark" aria-hidden="true">A</span><div><strong>Atlas</strong><p className="atlas-help">Consultorio</p></div></div><Sidebar items={items} activeView={activeView} onNavigate={navigate} /></aside>
    <div className="atlas-shell-body"><Topbar {...topbar} menuOpen={mobileOpen} onOpenMenu={() => setMobileOpen(true)} /><main id={mainId} tabIndex={-1} className="atlas-main">{children}</main></div>
    <Drawer title="Atlas · Navegación" open={mobileOpen} onClose={() => setMobileOpen(false)}><Sidebar items={items} activeView={activeView} onNavigate={navigate} /></Drawer>
  </div>;
}
