import { getNavigationItems, type AppView } from "../../navigation/navigation";
import type { User } from "../../types/user";
import type { NavigationIcon } from "../../navigation/navigation";

export type DashboardRole = "doctor" | "secretary" | "admin";

export type DashboardAction = {
  id: string;
  label: string;
  description: string;
  view: AppView;
  roles?: readonly DashboardRole[];
  icon: NavigationIcon;
  tone: "sky" | "sage" | "amber" | "coral" | "mint";
  intent?: "new-appointment";
};

export type DashboardRoleSummary = {
  id: DashboardRole;
  title: string;
  description: string;
};

const quickActions: readonly DashboardAction[] = [
  { id: "new-appointment", label: "Nueva cita", description: "Registrar una cita", view: "appointments", intent: "new-appointment", icon: "calendar", tone: "amber", roles: ["doctor", "secretary", "admin"] },
  { id: "patients", label: "Pacientes", description: "Buscar y gestionar", view: "patients", icon: "patient", tone: "sage" },
  { id: "agenda", label: "Ver agenda", description: "Citas y confirmaciones", view: "appointments", icon: "calendar", tone: "sky" },
  { id: "reports", label: "Reportes de citas", description: "Consultar reportes", view: "reports", icon: "report", tone: "coral" },
  { id: "follow-ups", label: "Ver seguimientos", description: "Seguimientos propios", view: "follow-ups", roles: ["doctor"], icon: "bell", tone: "mint" },
  { id: "availability", label: "Mi disponibilidad", description: "Gestionar disponibilidad", view: "availability", roles: ["doctor"], icon: "clock", tone: "sage" },
  { id: "coverages", label: "Cobertura clínica", description: "Coberturas vigentes", view: "clinical-coverages", roles: ["doctor", "secretary"], icon: "clinical", tone: "mint" },
  { id: "users", label: "Usuarios y roles", description: "Gestionar cuentas", view: "users", roles: ["admin"], icon: "users", tone: "sky" },
  { id: "centers", label: "Centros de atención", description: "Localidades y centros", view: "care-context", roles: ["admin"], icon: "center", tone: "sage" },
];

export type DashboardWidget = { id: string; label: string; group: "actions" | "metrics" | "summary" };

const metricWidgets: readonly DashboardWidget[] = [
  { id: "metric-appointments", label: "Citas de hoy", group: "metrics" },
  { id: "metric-patients", label: "Pacientes disponibles", group: "metrics" },
  { id: "metric-notifications", label: "Notificaciones pendientes", group: "metrics" },
  { id: "metric-follow-ups", label: "Seguimientos pendientes", group: "metrics" },
  { id: "metric-users", label: "Usuarios activos", group: "metrics" },
  { id: "metric-centers", label: "Centros activos", group: "metrics" },
];
const summaryWidgets: readonly DashboardWidget[] = [
  { id: "agenda-today", label: "Agenda de hoy", group: "summary" },
  { id: "notifications-panel", label: "Detalle de notificaciones", group: "summary" },
];

export const dashboardWidgetIds = [
  "users", "centers", ...quickActions.filter(action => action.id !== "users" && action.id !== "centers").map(action => action.id),
  ...metricWidgets.map(widget => widget.id), ...summaryWidgets.map(widget => widget.id),
] as const;

export function getDefaultDashboardWidgetOrder(): string[] { return [...dashboardWidgetIds]; }

export function normalizeDashboardWidgetOrder(visible: readonly string[], preferred: readonly string[] = []): string[] {
  const available = new Set(visible);
  const valid = preferred.filter((id, index) => available.has(id) && preferred.indexOf(id) === index);
  const included = new Set(valid);
  return [...valid, ...visible.filter(id => !included.has(id))];
}

export function getDashboardWidgets(user: Pick<User, "roles" | "permissions">): DashboardWidget[] {
  const actions = getDashboardActions(user).map(action => ({ id: action.id, label: action.label, group: "actions" as const }));
  const can = (permission: string) => !user.permissions || user.permissions.includes(permission);
  const metrics = metricWidgets.filter(widget =>
    widget.id === "metric-appointments" ? can("patients:access") :
    widget.id === "metric-patients" ? can("patients:view") :
    widget.id === "metric-follow-ups" ? user.roles.includes("doctor") && can("clinical:access") :
    widget.id === "metric-users" ? user.roles.includes("admin") && can("users:manage") :
    widget.id === "metric-centers" ? user.roles.includes("admin") && can("centers:manage") : true);
  const summary = summaryWidgets.filter(widget => widget.id !== "agenda-today" || can("patients:access"));
  return [...actions, ...metrics, ...summary];
}

const roleSummaries: readonly DashboardRoleSummary[] = [
  { id: "doctor", title: "Jornada clínica", description: "Priorice la agenda, los seguimientos y su disponibilidad." },
  { id: "secretary", title: "Operación de agenda", description: "Coordine citas y pacientes dentro de los centros y médicos asignados." },
  { id: "admin", title: "Administración operativa", description: "Revise el estado de usuarios y centros de atención." },
];

function hasRole(user: Pick<User, "roles">, role: DashboardRole) {
  return user.roles.includes(role);
}

export function getDashboardActions(user: Pick<User, "roles" | "permissions">): DashboardAction[] {
  const visible = new Set(getNavigationItems(user).map(item => item.view));
  const actions = quickActions.filter((action) => visible.has(action.view) && (!action.roles || action.roles.some((role) => hasRole(user, role))));
  return hasRole(user, "admin") && !hasRole(user, "doctor") && !hasRole(user, "secretary")
    ? [...actions.filter((action) => action.id === "users" || action.id === "centers"), ...actions.filter((action) => action.id !== "users" && action.id !== "centers")]
    : actions;
}

export function getDashboardRoleSummaries(user: Pick<User, "roles">): DashboardRoleSummary[] {
  return roleSummaries.filter((summary) => hasRole(user, summary.id));
}

export function roleLabel(role: string) {
  return ({ doctor: "Médico", secretary: "Secretaría", admin: "Administrador" } as Record<string, string>)[role] ?? role;
}
