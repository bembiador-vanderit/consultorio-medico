import { useEffect, useMemo, useState } from "react";
import { DashboardCard, MetricCard, QuickActions, TodayAppointments } from "../components/dashboard/DashboardBlocks";
import { getDashboardActions, getDashboardRoleSummaries, roleLabel } from "../components/dashboard/dashboardModel";
import type { AppView } from "../navigation/navigation";
import { api } from "../services/api";
import { announceNotificationsChanged, notificationsChangedEvent } from "../services/notificationEvents";
import type { Appointment } from "../types/appointment";
import type { User } from "../types/user";

type Notification = { id: number; title: string; message: string; is_read: boolean };
type FollowUp = { id: number; status: string };
type AdminUser = { id: number; is_active: boolean };
type Center = { id: number; is_active: boolean };
type Loadable<T> = { loading: boolean; data: T; error: string | null };

const initial = <T,>(data: T): Loadable<T> => ({ loading: true, data, error: null });
const today = () => new Date().toISOString().slice(0, 10);

export default function Dashboard({ user, patientsVersion, onNavigate }: { user: User; patientsVersion: number; onNavigate: (view: AppView) => void }) {
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

  return <section aria-labelledby="dashboard-title">
    <p className="text-sm font-medium text-teal-700">Dashboard</p>
    <h2 id="dashboard-title" className="mt-1 text-3xl font-bold text-slate-900">Bienvenido, {user.full_name}</h2>
    <p className="mt-2 text-slate-600">{user.roles.length ? user.roles.map(roleLabel).join(" · ") : "Usuario autenticado"}</p>

    {isDoctor && <div className="mt-6"><DashboardCard title="Especialidades asignadas" description="Información de perfil. La especialidad se define en cada cita o consulta.">
      <p className="font-semibold text-teal-800">{user.specialty_names?.length ? user.specialty_names.join(" · ") : "Especialidades pendientes de configurar"}</p>
    </DashboardCard></div>}

    {roleSummaries.length > 0 && <div className="mt-6 grid gap-4 lg:grid-cols-3">
      {roleSummaries.map((summary) => <DashboardCard key={summary.id} title={summary.title} description={summary.description}><p className="text-sm text-slate-600">Los datos y acciones visibles respetan el alcance que aplica el backend.</p></DashboardCard>)}
    </div>}

    <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <MetricCard label="Citas de hoy" value={appointments.loading ? "…" : appointments.error ? "—" : appointments.data.length} help="Solo citas dentro de su alcance." />
      <MetricCard label="Pacientes disponibles" value={patients.loading ? "…" : patients.data ?? "—"} help={patients.error ?? "Conteo provisto por la API."} />
      <MetricCard label="Notificaciones pendientes" value={notifications.loading ? "…" : notifications.error ? "—" : notifications.data.length} help={notifications.error ?? "Avisos dirigidos a su usuario."} />
      {isDoctor && <MetricCard label="Seguimientos pendientes" value={followUps.loading ? "…" : followUps.error ? "—" : openFollowUps} help={followUps.error ?? "Seguimientos propios aún no completados."} />}
      {isAdmin && <MetricCard label="Usuarios activos" value={administration.loading ? "…" : administration.error ? "—" : activeUsers} help={administration.error ?? "Datos administrativos disponibles."} />}
      {isAdmin && <MetricCard label="Centros activos" value={administration.loading ? "…" : administration.error ? "—" : activeCenters} help={administration.error ?? "Datos administrativos disponibles."} />}
    </div>

    <div className="mt-6 grid gap-6 xl:grid-cols-2">
      <TodayAppointments appointments={appointments.data} loading={appointments.loading} error={appointments.error} />
      <DashboardCard title="Notificaciones pendientes" description="Eventos y recordatorios dirigidos a tu usuario.">
        {notifications.loading && <p role="status" className="text-sm text-slate-500">Cargando notificaciones…</p>}
        {!notifications.loading && notifications.error && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{notifications.error}</p>}
        {!notifications.loading && !notifications.error && notifications.data.length === 0 && <p className="text-sm text-slate-500">No hay notificaciones pendientes.</p>}
        {!notifications.loading && !notifications.error && <div className="space-y-3">{notifications.data.map((notification) => <div key={notification.id} className="rounded-lg border border-teal-100 bg-teal-50 p-3"><div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-slate-900">{notification.title}</p><p className="mt-1 text-sm text-slate-600">{notification.message}</p></div><button type="button" className="shrink-0 text-xs font-semibold text-teal-700 hover:underline" onClick={() => void markRead(notification.id)}>Marcar leída</button></div></div>)}</div>}
      </DashboardCard>
    </div>

    <div className="mt-6"><QuickActions actions={actions} onNavigate={(action) => onNavigate(action.view)} /></div>
  </section>;
}
