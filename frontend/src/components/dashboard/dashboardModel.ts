import type { AppView } from "../../navigation/navigation";
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

const roleSummaries: readonly DashboardRoleSummary[] = [
  { id: "doctor", title: "Jornada clínica", description: "Priorice la agenda, los seguimientos y su disponibilidad." },
  { id: "secretary", title: "Operación de agenda", description: "Coordine citas y pacientes dentro de los centros y médicos asignados." },
  { id: "admin", title: "Administración operativa", description: "Revise el estado de usuarios y centros de atención." },
];

function hasRole(user: Pick<User, "roles">, role: DashboardRole) {
  return user.roles.includes(role);
}

export function getDashboardActions(user: Pick<User, "roles">): DashboardAction[] {
  const actions = quickActions.filter((action) => !action.roles || action.roles.some((role) => hasRole(user, role)));
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
