import type { ReactNode } from "react";
import type { Appointment } from "../../types/appointment";
import type { DashboardAction } from "./dashboardModel";

export function DashboardCard({ title, description, children, className = "" }: { title: string; description?: string; children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
    <h3 className="text-lg font-bold text-slate-900">{title}</h3>
    {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
    <div className="mt-4">{children}</div>
  </section>;
}

export function MetricCard({ label, value, help }: { label: string; value: string | number; help?: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <p className="text-sm font-medium text-slate-600">{label}</p>
    <p className="mt-2 text-3xl font-bold text-slate-900">{value}</p>
    {help && <p className="mt-2 text-xs text-slate-500">{help}</p>}
  </div>;
}

export function QuickActions({ actions, onNavigate }: { actions: readonly DashboardAction[]; onNavigate: (action: DashboardAction) => void }) {
  return <DashboardCard title="Acciones rápidas" description="Accesos a flujos disponibles para su rol.">
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {actions.map((action) => <button key={action.id} type="button" aria-label={action.label} data-dashboard-action={action.id} onClick={() => onNavigate(action)} className="rounded-lg border border-slate-200 p-4 text-left transition hover:border-teal-300 hover:bg-teal-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700">
        <span className="block font-semibold text-teal-800">{action.label}</span>
        <span className="mt-1 block text-sm text-slate-600">{action.description}</span>
      </button>)}
    </div>
  </DashboardCard>;
}

const appointmentStatus: Record<Appointment["status"], string> = {
  scheduled: "Programada",
  confirmed: "Confirmada",
  completed: "Completada",
  cancelled: "Cancelada",
  no_show: "No asistió",
};

export function TodayAppointments({ appointments, loading, error }: { appointments: Appointment[]; loading: boolean; error: string | null }) {
  return <DashboardCard title="Agenda de hoy" description="Citas visibles dentro de su alcance actual.">
    {loading && <p role="status" className="text-sm text-slate-500">Cargando citas de hoy…</p>}
    {error && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{error}</p>}
    {!loading && !error && appointments.length === 0 && <p className="text-sm text-slate-500">No hay citas para hoy dentro de tu alcance.</p>}
    {!loading && !error && appointments.length > 0 && <ol className="space-y-3">
      {appointments.slice(0, 5).map((appointment) => <li key={appointment.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-3">
        <div><p className="font-semibold text-slate-900">{appointment.patient_name}</p><p className="text-sm text-slate-600">{appointment.doctor_name}{appointment.center_name ? ` · ${appointment.center_name}` : ""}</p></div>
        <div className="text-right"><p className="font-semibold text-slate-800">{appointment.appointment_time.slice(0, 5)}</p><p className="text-xs text-slate-500">{appointmentStatus[appointment.status]}</p></div>
      </li>)}
    </ol>}
  </DashboardCard>;
}
