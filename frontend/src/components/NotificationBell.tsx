import { useEffect, useState } from "react";
import { api } from "../services/api";
import { announceNotificationsChanged, notificationsChangedEvent } from "../services/notificationEvents";

type Notification = {
  id: number;
  follow_up_id: number | null;
  appointment_id: number | null;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
};

type Props = { onOpenNotifications: () => void };

export default function NotificationBell({ onOpenNotifications }: Props) {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      await api.post("/follow-ups/notifications/sync");
      const { data } = await api.get<Notification[]>("/follow-ups/notifications", { params: { unread_only: true } });
      setItems(data);
    } catch (error) {
      console.error("Error cargando notificaciones:", error);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60000);
    const refreshNotifications = () => void load();
    window.addEventListener(notificationsChangedEvent, refreshNotifications);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(notificationsChangedEvent, refreshNotifications);
    };
  }, []);

  async function markRead(id: number) {
    try {
      await api.post(`/follow-ups/notifications/${id}/read`);
      setItems((current) => current.filter((item) => item.id !== id));
      announceNotificationsChanged();
    } catch (error) {
      console.error("Error marcando notificación:", error);
    }
  }

  const unread = items.length;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={`Notificaciones${unread ? `, ${unread} sin leer` : ""}`}
        className="relative rounded-lg border border-slate-200 bg-white px-3 py-2 text-xl hover:bg-slate-50"
      >
        🔔
        {unread > 0 && <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-600 px-1 text-center text-[11px] font-bold leading-5 text-white">{unread > 99 ? "99+" : unread}</span>}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-xl border bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div><p className="font-bold">Notificaciones pendientes</p><p className="text-xs text-slate-500">Eventos, seguimientos y citas próximas</p></div>
            <button type="button" onClick={() => void load()} className="text-xs font-semibold text-teal-700 hover:underline">Actualizar</button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 && <p className="p-5 text-sm text-slate-500">No tienes notificaciones pendientes.</p>}
            {items.map((item) => (
              <div key={item.id} className={`border-b px-4 py-3 ${item.is_read ? "bg-white" : "bg-teal-50"}`}>
                <div className="flex items-start gap-3">
                  <span className="mt-0.5">{item.notification_type.includes("overdue") ? "🚨" : item.notification_type.includes("appointment") ? "📅" : "⏰"}</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-sm">{item.title}</p>
                    <p className="mt-1 text-sm text-slate-600">{item.message}</p>
                    {!item.is_read && <button type="button" onClick={() => void markRead(item.id)} className="mt-2 text-xs font-semibold text-teal-700 hover:underline">Marcar como leída</button>}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="border-t bg-slate-50 p-3">
            <button type="button" onClick={() => { setOpen(false); onOpenNotifications(); }} className="w-full rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800">Ver en Dashboard</button>
          </div>
        </div>
      )}
    </div>
  );
}
