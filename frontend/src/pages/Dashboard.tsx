import { useEffect, useMemo, useState } from "react";
import { DashboardCard, MetricCard, QuickActions, TodayAppointments } from "../components/dashboard/DashboardBlocks";
import { getDashboardActions, getDashboardRoleSummaries, roleLabel } from "../components/dashboard/dashboardModel";
import type { AppView } from "../navigation/navigation";
import { api } from "../services/api";
import { announceNotificationsChanged, notificationsChangedEvent } from "../services/notificationEvents";
import type { Appointment } from "../types/appointment";
import type { User } from "../types/user";
import { NavigationIcon } from "../layouts/NavigationIcon";
import { Button } from "../ui";
import "./dashboard.css";

type Notification = { id: number; title: string; message: string; is_read: boolean };
type FollowUp = { id: number; status: string };
type AdminUser = { id: number; is_active: boolean };
type Center = { id: number; is_active: boolean };
type Loadable<T> = { loading: boolean; data: T; error: string | null };

const initial = <T,>(data: T): Loadable<T> => ({ loading: true, data, error: null });
const today = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; };

export default function Dashboard({ user, patientsVersion, onNavigate, onNewAppointment }: { user: User; patientsVersion: number; onNavigate: (view: AppView) => void; onNewAppointment?: () => void }) {
  const [patients, setPatients] = useState<Loadable<number | null>>(() => initial(null));
  const [appointments, setAppointments] = useState<Loadable<Appointment[]>>(() => initial([]));
  const [notifications, setNotifications] = useState<Loadable<Notification[]>>(() => initial([]));
  const [followUps, setFollowUps] = useState<Loadable<FollowUp[]>>(() => initial([]));
  const [administration, setAdministration] = useState<Loadable<{ users: AdminUser[]; centers: Center[] }>>(() => initial({ users: [], centers: [] }));
  const isDoctor = user.roles.includes("doctor");
  const isAdmin = user.roles.includes("admin");

  async function loadPatients() {
    setPatients((current) => ({ ...current, loading: true, error: null }));
    try { const { data } = await api.get<{ count: number }>("/patients/count"); setPatients({ loading: false, data: data.count, error: null }); }
    catch { setPatients({ loading: false, data: null, error: "No fue posible cargar los pacientes disponibles." }); }
  }

  async function loadAppointments() {
    setAppointments((current) => ({ ...current, loading: true, error: null }));
    try { const date = today(); const { data } = await api.get<Appointment[]>("/appointments", { params: { start: date, end: date } }); setAppointments({ loading: false, data, error: null }); }
    catch { setAppointments({ loading: false, data: [], error: "No fue posible cargar las citas de hoy. Puede continuar usando las demás herramientas." }); }
  }

  async function loadNotifications() {
    setNotifications((current) => ({ ...current, loading: true, error: null }));
    try { await api.post("/follow-ups/notifications/sync"); const { data } = await api.get<Notification[]>("/follow-ups/notifications", { params: { unread_only: true } }); setNotifications({ loading: false, data, error: null }); }
    catch { setNotifications({ loading: false, data: [], error: "No fue posible cargar las notificaciones." }); }
  }

  async function loadFollowUps() {
    if (!isDoctor) return;
    setFollowUps((current) => ({ ...current, loading: true, error: null }));
    try { const { data } = await api.get<FollowUp[]>("/follow-ups"); setFollowUps({ loading: false, data, error: null }); }
    catch { setFollowUps({ loading: false, data: [], error: "No fue posible cargar los seguimientos." }); }
  }

  async function loadAdministration() {
    if (!isAdmin) return;
    setAdministration((current) => ({ ...current, loading: true, error: null }));
    try {
      const [users, centers] = await Promise.all([api.get<AdminUser[]>("/users"), api.get<Center[]>("/centers")]);
      setAdministration({ loading: false, data: { users: users.data, centers: centers.data }, error: null });
    } catch { setAdministration({ loading: false, data: { users: [], centers: [] }, error: "No fue posible cargar el resumen administrativo." }); }
  }

  useEffect(() => {
    void loadPatients(); void loadAppointments(); void loadNotifications(); void loadFollowUps(); void loadAdministration();
    const refreshNotifications = () => void loadNotifications();
    window.addEventListener(notificationsChangedEvent, refreshNotifications);
    return () => window.removeEventListener(notificationsChangedEvent, refreshNotifications);
  // User identity changes only during a new authenticated session; patientsVersion refreshes the patient metric.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id, patientsVersion]);

  async function markRead(id: number) {
    try { await api.post(`/follow-ups/notifications/${id}/read`); setNotifications((current) => ({ ...current, data: current.data.filter((item) => item.id !== id) })); announceNotificationsChanged(); }
    catch { setNotifications((current) => ({ ...current, error: "No fue posible actualizar la notificación." })); }
  }

  const actions = useMemo(() => getDashboardActions(user), [user]);
  const roleSummaries = useMemo(() => getDashboardRoleSummaries(user), [user]);
  const openFollowUps = followUps.data.filter((item) => item.status !== "completed").length;
  const activeUsers = administration.data.users.filter((item) => item.is_active).length;
  const activeCenters = administration.data.centers.filter((item) => item.is_active).length;

  return <section aria-labelledby="dashboard-title" className="dashboard-workspace">
    <header className="dashboard-welcome"><div><p className="atlas-caption dashboard-desktop-label">Dashboard</p><h2 id="dashboard-title">Hola, {user.full_name}</h2><p className="atlas-help dashboard-role-label">{user.roles.length ? user.roles.map(roleLabel).join(" · ") : "Usuario autenticado"}</p></div>
      {isDoctor && <div className="dashboard-specialties" aria-label="Especialidades asignadas"><span className="atlas-caption">Especialidades</span>{user.specialty_names?.length ? user.specialty_names.map((name, index) => <span className="atlas-badge atlas-tone--success" key={`${name}-${index}`}>{name}</span>) : <span className="atlas-help">Especialidades pendientes de configurar</span>}</div>}
    </header>
    {roleSummaries.length > 0 && <div className="dashboard-role-context">{roleSummaries.map((summary) => <span key={summary.id} title={summary.description}><NavigationIcon name={summary.id === "admin" ? "users" : summary.id === "doctor" ? "clinical" : "calendar"} />{summary.title}</span>)}</div>}
    <QuickActions actions={actions} onNavigate={(action) => action.intent === "new-appointment" && onNewAppointment ? onNewAppointment() : onNavigate(action.view)} />
    <div className="dashboard-metrics" aria-label="Resumen de actividad">
      <MetricCard label="Citas de hoy" error={Boolean(appointments.error)} value={appointments.loading ? "…" : appointments.error ? "—" : appointments.data.length} help={appointments.error ?? "Dentro de su alcance"} icon="calendar" tone="sky" />
      <MetricCard label="Pacientes disponibles" error={Boolean(patients.error)} value={patients.loading ? "…" : patients.data ?? "—"} help={patients.error ?? "Pacientes accesibles"} icon="patient" tone="sage" />
      <MetricCard label="Notificaciones pendientes" error={Boolean(notifications.error)} value={notifications.loading ? "…" : notifications.error ? "—" : notifications.data.length} help={notifications.error ?? "Avisos para su usuario"} icon="bell" tone="amber" />
      {isDoctor && <MetricCard label="Seguimientos pendientes" error={Boolean(followUps.error)} value={followUps.loading ? "…" : followUps.error ? "—" : openFollowUps} help={followUps.error ?? "Sin completar"} icon="clinical" tone="mint" />}
      {isAdmin && <MetricCard label="Usuarios activos" error={Boolean(administration.error)} value={administration.loading ? "…" : administration.error ? "—" : activeUsers} help={administration.error ?? "Cuentas habilitadas"} icon="users" tone="sky" />}
      {isAdmin && <MetricCard label="Centros activos" error={Boolean(administration.error)} value={administration.loading ? "…" : administration.error ? "—" : activeCenters} help={administration.error ?? "Centros habilitados"} icon="center" tone="sage" />}
    </div>
    <div className="dashboard-summary-grid">
      <TodayAppointments appointments={appointments.data} loading={appointments.loading} error={appointments.error} onOpenAgenda={() => onNavigate("appointments")} />
      <DashboardCard title="Notificaciones pendientes" icon="bell" className="dashboard-notifications">
        {notifications.loading && <p role="status" className="dashboard-empty">Cargando notificaciones…</p>}
        {!notifications.loading && notifications.error && <p role="alert" className="dashboard-error">{notifications.error}</p>}
        {!notifications.loading && !notifications.error && !notifications.data.length && <p className="dashboard-empty">No hay notificaciones pendientes.</p>}
        {!notifications.loading && !notifications.error && notifications.data.length > 0 && <ul className="dashboard-notification-list">{notifications.data.map((notification) => <li key={notification.id}><span className="dashboard-icon dashboard-tone--amber" aria-hidden="true"><NavigationIcon name="bell" /></span><div><strong>{notification.title}</strong><p>{notification.message}</p><Button variant="ghost" size="sm" onClick={() => void markRead(notification.id)}>Marcar leída</Button></div></li>)}</ul>}
      </DashboardCard>
    </div>
  </section>;
}
