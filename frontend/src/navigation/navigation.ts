import type { User } from "../types/user";

export type AppView = "security" | "dashboard" | "patients" | "appointments" | "reports" | "care-context" | "availability" | "users" | "follow-ups" | "consultation" | "clinical-coverages";
/** Receives the requested transition and may defer it until the current view is ready to leave. */
export type NavigationGuard = (proceed: () => void) => void;
export type NavigationGuardRegistrar = (guard: NavigationGuard | null) => void;
export type NavigationIcon = "home" | "calendar" | "report" | "patient" | "bell" | "clock" | "clinical" | "users" | "center";
export type NavigationItem = {
  id: string;
  label: string;
  view: AppView;
  icon: NavigationIcon;
  group: "general" | "clinical" | "administration";
  order: number;
  visibility: { kind: "authenticated" } | { kind: "any-role"; roles: readonly string[] };
};

/** Mirrors App.tsx at the approved base. Visibility never grants authorization. */
export const navigationItems: readonly NavigationItem[] = [
  { id: "security", label: "Seguridad", view: "security", icon: "users", group: "administration", order: 100, visibility: { kind: "authenticated" } },
  { id: "dashboard", label: "Dashboard", view: "dashboard", icon: "home", group: "general", order: 10, visibility: { kind: "authenticated" } },
  { id: "appointments", label: "Agenda", view: "appointments", icon: "calendar", group: "general", order: 20, visibility: { kind: "authenticated" } },
  { id: "reports", label: "Reportes de citas", view: "reports", icon: "report", group: "general", order: 30, visibility: { kind: "authenticated" } },
  { id: "patients", label: "Pacientes", view: "patients", icon: "patient", group: "general", order: 40, visibility: { kind: "authenticated" } },
  { id: "follow-ups", label: "Seguimientos", view: "follow-ups", icon: "bell", group: "clinical", order: 50, visibility: { kind: "any-role", roles: ["doctor"] } },
  { id: "availability", label: "Mi disponibilidad", view: "availability", icon: "clock", group: "clinical", order: 60, visibility: { kind: "any-role", roles: ["doctor"] } },
  { id: "clinical-coverages", label: "Cobertura clínica", view: "clinical-coverages", icon: "clinical", group: "clinical", order: 70, visibility: { kind: "any-role", roles: ["doctor", "secretary"] } },
  { id: "users", label: "Usuarios y roles", view: "users", icon: "users", group: "administration", order: 80, visibility: { kind: "any-role", roles: ["admin"] } },
  { id: "care-context", label: "Localidades y centros", view: "care-context", icon: "center", group: "administration", order: 90, visibility: { kind: "any-role", roles: ["admin"] } },
];

export type NavigationVisibilityResolver = (item: NavigationItem, user: Pick<User, "roles" | "permissions">) => boolean;
export const roleNavigationVisibility: NavigationVisibilityResolver = (item, user) => {
  const capability = ({ appointments: "patients:access", reports: "patients:access", patients: "patients:access", "follow-ups": "clinical:access", availability: "patients:access", "clinical-coverages": "patients:access", users: "users:manage", "care-context": "centers:manage" } as Record<string, string>)[item.view];
  if (capability && user.permissions && !user.permissions.includes(capability)) return false;
  return item.visibility.kind === "authenticated" || item.visibility.roles.some((role) => user.roles.includes(role));
};

/** A later API capability adapter can replace the resolver; no invented permissions today. */
export function getNavigationItems(user: Pick<User, "roles" | "permissions"> | null, resolve: NavigationVisibilityResolver = roleNavigationVisibility) {
  return user ? navigationItems.filter((item) => resolve(item, user)).sort((a, b) => a.order - b.order) : [];
}

export const navigationGroups = [
  { id: "general", label: "Gestión" },
  { id: "clinical", label: "Atención" },
  { id: "administration", label: "Administración" },
] as const;
