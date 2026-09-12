import type { AppView } from "../../navigation/navigation";
import type { User } from "../../types/user";

export type DashboardRole = "doctor" | "secretary" | "admin";

export type DashboardAction = {
  id: string;
  label: string;
  description: string;
  view: AppView;
  roles?: readonly DashboardRole[];
};

export type DashboardRoleSummary = {
  id: DashboardRole;
  title: string;
  description: string;
};

const quickActions: readonly DashboardAction[] = [
  { id: "agenda", label: "Ver agenda", description: "Revise las citas dentro de su alcance.", view: "appointments" },
  { id: "patients", label: "Pacientes", description: "Consulte los pacientes disponibles para su rol.", view: "patients" },
  { id: "reports", label: "Reportes de citas", description: "Genere reportes de la agenda permitida.", view: "reports" },
  { id: "follow-ups", label: "Ver seguimientos", description: "Revise sus seguimientos pendientes.", view: "follow-ups", roles: ["doctor"] },
  { id: "availability", label: "Mi disponibilidad", description: "Actualice su disponibilidad clínica.", view: "availability", roles: ["doctor"] },
  { id: "coverages", label: "Cobertura clínica", description: "Consulte las coberturas vigentes permitidas.", view: "clinical-coverages", roles: ["doctor", "secretary"] },
  { id: "users", label: "Usuarios y roles", description: "Administre cuentas y roles autorizados.", view: "users", roles: ["admin"] },
  { id: "centers", label: "Centros de atención", description: "Administre localidades y centros autorizados.", view: "care-context", roles: ["admin"] },
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
  return quickActions.filter((action) => !action.roles || action.roles.some((role) => hasRole(user, role)));
}

export function getDashboardRoleSummaries(user: Pick<User, "roles">): DashboardRoleSummary[] {
  return roleSummaries.filter((summary) => hasRole(user, summary.id));
}

export function roleLabel(role: string) {
  return ({ doctor: "Médico", secretary: "Secretaría", admin: "Administrador" } as Record<string, string>)[role] ?? role;
}
