import { useId, useState, type ReactNode } from "react";
import type { Appointment } from "../../types/appointment";
import type { NavigationIcon as IconName } from "../../navigation/navigation";
import { NavigationIcon } from "../../layouts/NavigationIcon";
import { AppointmentStatusBadge } from "../agenda/AppointmentStatusBadge";
import { Button } from "../../ui";
import type { DashboardAction } from "./dashboardModel";

export function DashboardCard({ title, description, children, className = "", icon = "calendar", action }: { title: string; description?: string; children: ReactNode; className?: string; icon?: IconName; action?: ReactNode }) {
  return <section className={`atlas-card dashboard-card ${className}`}>
    <header className="dashboard-card-heading"><div><h3 className="atlas-card-title"><NavigationIcon name={icon} />{title}</h3>{description && <p className="atlas-help">{description}</p>}</div>{action}</header>
    <div className="dashboard-card-body">{children}</div>
  </section>;
}

export function MetricCard({ label, value, help, error, icon = "calendar", tone = "sky" }: { label: string; value: string | number; help?: string; error?: boolean; icon?: IconName; tone?: DashboardAction["tone"] }) {
  return <div className={`atlas-card dashboard-metric dashboard-tone--${tone}`}><span className="dashboard-icon" aria-hidden="true"><NavigationIcon name={icon} /></span><div><p className="dashboard-metric-label">{label}</p><p className="dashboard-metric-value">{value}</p>{help && <p className="dashboard-metric-help" role={error ? "alert" : undefined}>{help}</p>}</div></div>;
}

export function QuickActions({ actions, onNavigate }: { actions: readonly DashboardAction[]; onNavigate: (action: DashboardAction) => void }) {
  const [expanded, setExpanded] = useState(false);
  const actionsId = useId();
  return <section aria-labelledby="dashboard-actions-title" className="dashboard-actions"><h3 id="dashboard-actions-title" className="atlas-caption">Acciones rápidas</h3><div id={actionsId} className={`dashboard-actions-grid${expanded ? " dashboard-actions-grid--expanded" : ""}`}>{actions.map((action) => <button key={action.id} type="button" aria-label={action.label} data-dashboard-action={action.id} onClick={() => onNavigate(action)} className={`dashboard-action dashboard-tone--${action.tone}`}><span className="dashboard-icon" aria-hidden="true"><NavigationIcon name={action.icon} /></span><span><strong>{action.label}</strong><span className="dashboard-action-help">{action.description}</span></span></button>)}</div>{actions.length > 4 && <Button className="dashboard-more-actions" variant="ghost" size="sm" aria-expanded={expanded} aria-controls={actionsId} onClick={() => setExpanded((current) => !current)}>{expanded ? "Menos accesos" : "Más accesos"}</Button>}</section>;
}

export function TodayAppointments({ appointments, loading, error, onOpenAgenda }: { appointments: Appointment[]; loading: boolean; error: string | null; onOpenAgenda?: () => void }) {
  const sorted = [...appointments].sort((a, b) => a.appointment_time.localeCompare(b.appointment_time));
  return <DashboardCard title="Agenda de hoy" icon="calendar" action={onOpenAgenda && <Button variant="ghost" size="sm" onClick={onOpenAgenda}>Ver agenda</Button>}>
    {loading && <p role="status" className="dashboard-empty">Cargando citas de hoy…</p>}
    {error && <p role="alert" className="dashboard-error">{error}</p>}
    {!loading && !error && !appointments.length && <p className="dashboard-empty">No hay citas para hoy dentro de tu alcance.</p>}
    {!loading && !error && appointments.length > 0 && <ol className="dashboard-appointments">{sorted.slice(0, 5).map((appointment) => <li key={appointment.id}><time>{appointment.appointment_time.slice(0, 5)}</time><div><strong title={appointment.patient_name}>{appointment.patient_name}</strong><span title={appointment.reason || appointment.doctor_name}>{appointment.reason || appointment.doctor_name}{appointment.center_name ? ` · ${appointment.center_name}` : ""}</span></div><AppointmentStatusBadge status={appointment.status} /></li>)}</ol>}
    {!loading && !error && appointments.length > 5 && <p className="atlas-help dashboard-list-note">Mostrando 5 de {appointments.length} citas. Consulte el resto en Agenda.</p>}
  </DashboardCard>;
}
