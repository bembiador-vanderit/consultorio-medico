import type { User } from "../types/user";

export type AppView = "finance" | "insurance" | "security" | "dashboard" | "patients" | "appointments" | "reports" | "care-context" | "availability" | "users" | "follow-ups" | "consultation" | "clinical-coverages" | "documents" | "personalization" | "agent-devices" | "print-management";
export type AccentTheme = "classic" | "blue" | "turquoise" | "clinical-green" | "indigo" | "violet";
export type FinanceSection = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type FinanceGroupId = "daily" | "ars" | "control";
export type FinanceNavigationGroup = {
  id: FinanceGroupId;
  label: string;
  sections: { index: FinanceSection; label: string }[];
};

export const financeNavigationGroups: readonly FinanceNavigationGroup[] = [
  { id: "daily", label: "Operación diaria", sections: [
    { index: 0, label: "Caja" }, { index: 1, label: "Facturación" },
    { index: 2, label: "Movimientos" }, { index: 3, label: "Pendientes" },
  ] },
  { id: "ars", label: "ARS", sections: [
    { index: 4, label: "Reclamaciones" }, { index: 5, label: "Pagos / remesas" },
    { index: 6, label: "CxC ARS" },
  ] },
  { id: "control", label: "Control", sections: [
    { index: 7, label: "Conciliación / resumen" },
  ] },
];

const financeSectionPermission: Record<FinanceSection, readonly string[]> = {
  0: ["finance:read", "finance:collect"], 1: ["finance:read"], 2: ["finance:read"], 3: ["finance:read"],
  4: ["ars:read"], 5: ["ars:read", "ars:payment"], 6: ["ars:read", "ars:report"], 7: ["ars:read", "ars:reconcile"],
};

export function getFinanceNavigationGroups(user: Pick<User, "permissions">): FinanceNavigationGroup[] {
  return financeNavigationGroups.map(group => ({
    ...group,
    sections: group.sections.filter(({ index }) => financeSectionPermission[index].every(permission => user.permissions?.includes(permission))),
  })).filter(group => group.sections.length > 0);
}

export function getDefaultFinanceSection(user: Pick<User, "permissions">): FinanceSection {
  return getFinanceNavigationGroups(user)[0]?.sections[0]?.index ?? 0;
}
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
  { id: "print-management", label: "Gestión de impresión", view: "print-management", icon: "report", group: "administration", order: 97, visibility: { kind: "authenticated" } },
  { id: "agent-devices", label: "Agentes y dispositivos", view: "agent-devices", icon: "center", group: "administration", order: 96, visibility: { kind: "authenticated" } },
  { id: "finance", label: "Finanzas", view: "finance", icon: "report", group: "general", order: 50, visibility: { kind: "authenticated" } },
  { id: "insurance", label: "Aseguradoras / ARS", view: "insurance", icon: "center", group: "administration", order: 95, visibility: { kind: "any-role", roles: ["admin"] } },
  { id: "security", label: "Seguridad", view: "security", icon: "users", group: "administration", order: 100, visibility: { kind: "authenticated" } },
  { id: "dashboard", label: "Dashboard", view: "dashboard", icon: "home", group: "general", order: 10, visibility: { kind: "authenticated" } },
  { id: "appointments", label: "Agenda", view: "appointments", icon: "calendar", group: "general", order: 20, visibility: { kind: "authenticated" } },
  { id: "reports", label: "Reportes de citas", view: "reports", icon: "report", group: "general", order: 30, visibility: { kind: "authenticated" } },
  { id: "patients", label: "Pacientes", view: "patients", icon: "patient", group: "general", order: 40, visibility: { kind: "authenticated" } },
  { id: "follow-ups", label: "Seguimientos", view: "follow-ups", icon: "bell", group: "clinical", order: 60, visibility: { kind: "any-role", roles: ["doctor", "secretary"] } },
  { id: "availability", label: "Mi disponibilidad", view: "availability", icon: "clock", group: "clinical", order: 70, visibility: { kind: "any-role", roles: ["doctor"] } },
  { id: "clinical-coverages", label: "Cobertura clínica", view: "clinical-coverages", icon: "clinical", group: "clinical", order: 80, visibility: { kind: "any-role", roles: ["doctor", "secretary"] } },
  { id: "users", label: "Usuarios y roles", view: "users", icon: "users", group: "administration", order: 80, visibility: { kind: "any-role", roles: ["admin"] } },
  { id: "care-context", label: "Localidades y centros", view: "care-context", icon: "center", group: "administration", order: 90, visibility: { kind: "any-role", roles: ["admin"] } },
  { id: "personalization", label: "Personalización", view: "personalization", icon: "clinical", group: "administration", order: 91, visibility: { kind: "authenticated" } },
  { id: "documents", label: "Documentos", view: "documents", icon: "clinical", group: "administration", order: 92, visibility: { kind: "any-role", roles: ["admin"] } },
];

export type NavigationVisibilityResolver = (item: NavigationItem, user: Pick<User, "roles" | "permissions">) => boolean;

export function getDefaultGestionOrder(): string[] {
  return navigationItems.filter(item => item.group === "general").sort((a, b) => a.order - b.order).map(item => item.id);
}

export function normalizeGestionOrder(availableItems: readonly NavigationItem[], preferredOrder: readonly string[] = []): string[] {
  const available = availableItems.filter(item => item.group === "general").sort((a, b) => a.order - b.order);
  const availableIds = new Set(available.map(item => item.id));
  const preferred = preferredOrder.filter((id, index) => availableIds.has(id) && preferredOrder.indexOf(id) === index);
  const included = new Set(preferred);
  return [...preferred, ...available.filter(item => !included.has(item.id)).map(item => item.id)];
}

export function orderGestionItems(items: readonly NavigationItem[], preferredOrder: readonly string[] = []): NavigationItem[] {
  const order = normalizeGestionOrder(items, preferredOrder);
  const position = new Map(order.map((id, index) => [id, index]));
  return [...items].sort((left, right) => left.group === "general" && right.group === "general"
    ? (position.get(left.id) ?? Number.MAX_SAFE_INTEGER) - (position.get(right.id) ?? Number.MAX_SAFE_INTEGER)
    : left.order - right.order);
}

export const roleNavigationVisibility: NavigationVisibilityResolver = (item, user) => {
  if (item.view === "agent-devices" || item.view === "print-management") return !!user.permissions?.includes("local_agents:view");
  if(item.view === "follow-ups" && user.roles.includes("secretary")) return !user.permissions || ["patients:view","patients:access"].every(p=>user.permissions!.includes(p));
  if (item.view === "finance") return !!user.permissions?.some(permission => permission === "finance:read" || permission === "ars:read");
  if (item.view === "insurance" && !user.permissions?.includes("users:manage")) return false;
  if (item.view === "documents" && !user.permissions?.includes("documents:manage") && !user.permissions?.includes("users:manage")) return false;
  const capability = ({ insurance: "users:manage", appointments: "patients:access", reports: "patients:access", patients: "patients:view", "follow-ups": "clinical:access", availability: "patients:access", "clinical-coverages": "patients:access", users: "users:manage", "care-context": "centers:manage" } as Record<string, string>)[item.view];
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
  { id: "administration", label: "Herramientas" },
] as const;
