import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";

type Notification = {
  id: number;
  follow_up_id: number | null;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
};

export default function Dashboard({ user, patientsVersion }: { user: User; patientsVersion: number }) {
  const [patientCount, setPatientCount] = useState<number | null>(null);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  async function loadPatientCount() {
    try {
      setLoadingPatients(true);
      const { data } = await api.get<{ count: number }>("/patients/count");
      setPatientCount(data.count);
    } catch (error) {
      console.error("Error cargando cantidad de pacientes:", error);
      setPatientCount(null);
    } finally {
      setLoadingPatients(false);
    }
  }

  async function loadNotifications() {
    try {
      const { data } = await api.get<Notification[]>("/follow-ups/notifications");
      setNotifications(data);
    } catch (error) {
      console.error("Error cargando notificaciones:", error);
    }
  }

  async function markRead(id: number) {
    await api.post(`/follow-ups/notifications/${id}/read`);
    setNotifications((items) => items.map((item) => item.id === id ? { ...item, is_read: true } : item));
  }

  useEffect(() => {
    loadPatientCount();
    loadNotifications();
  }, [patientsVersion]);

  const unreadCount = notifications.filter((item) => !item.is_read).length;

  return (
    <section>
      <p className="text-sm font-medium text-teal-700">Dashboard</p>
      <h2 className="mt-1 text-3xl font-bold">Bienvenido, {user.full_name}</h2>
      <p className="mt-2 text-slate-500">Resumen general del consultorio.</p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard title="Pacientes" value={loadingPatients ? "..." : patientCount ?? "—"} />
        <StatCard title="Citas de hoy" value="0" />
        <StatCard title="Notificaciones" value={unreadCount} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border bg-white p-6 shadow-sm">
          <h3 className="font-bold">Notificaciones</h3>
          <p className="mt-1 text-sm text-slate-500">Seguimientos y avisos dirigidos a tu usuario.</p>
          <div className="mt-4 space-y-3">
            {notifications.length === 0 && <p className="text-sm text-slate-500">No hay notificaciones.</p>}
            {notifications.slice(0, 8).map((notification) => (
              <div key={notification.id} className={`rounded-lg border p-3 ${notification.is_read ? "bg-white" : "bg-teal-50"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{notification.title}</p>
                    <p className="mt-1 text-sm text-slate-600">{notification.message}</p>
                  </div>
                  {!notification.is_read && (
                    <button className="shrink-0 text-xs font-semibold text-teal-700 hover:underline" onClick={() => markRead(notification.id)}>
                      Marcar leída
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border bg-white p-6 shadow-sm">
          <h3 className="font-bold">Acciones rápidas</h3>
          <p className="mt-1 text-sm text-slate-500">
            Los seguimientos se crearán desde la consulta clínica y generarán automáticamente una notificación para el médico responsable.
          </p>
        </div>
      </div>
    </section>
  );
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded-xl border bg-white p-6 shadow-sm">
      <p className="text-sm text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-bold">{value}</p>
    </div>
  );
}
