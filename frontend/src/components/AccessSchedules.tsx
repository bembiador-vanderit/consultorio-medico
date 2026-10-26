import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";

type Window = { day: number; start: string; end: string };
type Schedule = {
  timezone: string; restrict_outside_schedule: boolean; weekly_schedule: Window[]; allowed: boolean;
  current_until: string | null; next_window: { starts_at: string; ends_at: string } | null;
  exceptions: { id: number; starts_at: string; ends_at: string; reason: string; authorized_by: number }[];
  blocked_dates: { id: number; day: string; reason: string; authorized_by: number }[];
};
const days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const field = "rounded border p-2";
const errorMessage = (error: any) => typeof error.response?.data?.detail === "string" ? error.response.data.detail : "No se pudo guardar. Revise las fechas y los horarios, sin superposiciones.";

export default function AccessSchedules({ users }: { users: User[] }) {
  const [selected, setSelected] = useState("");
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [dirty, setDirty] = useState(false);
  const [zone, setZone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [day, setDay] = useState("");
  const [blockReason, setBlockReason] = useState("");
  const path = `/administration/access-schedules/${selected}`;
  useEffect(() => {
    let active = true;
    setSchedule(null); setError(""); setMessage(""); setDirty(false);
    setStart(""); setEnd(""); setReason(""); setDay(""); setBlockReason("");
    if (selected) void api.get<Schedule>(path).then(({ data }) => {
      if (active) { setSchedule(data); setZone(data.timezone); }
    }).catch(error => { if (active) setError(errorMessage(error)); });
    return () => { active = false; };
  }, [selected]);
  async function save(action: () => Promise<{ data: Schedule }>) {
    setBusy(true); setError(""); setMessage("");
    try { const { data } = await action(); setSchedule(data); setDirty(false); setMessage("Cambio guardado. El usuario debe volver a iniciar sesión en esta organización."); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  const format = (value: string) => new Date(value).toLocaleString("es-DO", { timeZone: schedule?.timezone, dateStyle: "medium", timeStyle: "short" });
  const author = (id: number) => users.find(user => user.id === id)?.full_name || `Usuario ${id}`;
  function editWindow(index: number, key: "start" | "end", value: string) {
    setDirty(true);
    if (schedule) setSchedule({ ...schedule, weekly_schedule: schedule.weekly_schedule.map((window, i) => i === index ? { ...window, [key]: value } : window) });
  }
  return <section className="space-y-4 rounded-xl border bg-white p-5" aria-label="Horarios de acceso">
    <h3 className="font-bold">Horarios laborales y acceso</h3>
    <p>Configure el acceso de cada usuario a esta organización y todos sus centros. Las horas extra conservan su alcance y permisos actuales. Los días bloqueados tienen prioridad.</p>
    <label>Usuario del horario <select className={field} value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}>
      <option value="">Seleccione…</option>{users.map(user => <option key={user.id} value={user.id}>{user.full_name}</option>)}
    </select></label>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {schedule && <fieldset disabled={busy} className="space-y-4">
      <p>Zona horaria: <strong>{schedule.timezone}</strong>. Todas las horas se muestran en esta zona, aunque su equipo use otra.</p>
      {dirty ? <p role="status">Cambios sin guardar. Guarde el horario antes de gestionar excepciones; el estado efectivo se actualizará al guardar.</p> : <>
        <p>{!schedule.restrict_outside_schedule ? "Acceso sin restricción de horario." : schedule.allowed ? `Acceso permitido hasta ${schedule.current_until ? format(schedule.current_until) : "el fin de su ventana"}.` : "Fuera del horario autorizado."}</p>
        {schedule.next_window && <p>Próxima ventana: {format(schedule.next_window.starts_at)} a {format(schedule.next_window.ends_at)}.</p>}
        {schedule.restrict_outside_schedule && !schedule.allowed && !schedule.next_window && <p>No hay una ventana prevista en los próximos 370 días.</p>}
      </>}
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save(() => api.put(path, { restrict_outside_schedule: schedule.restrict_outside_schedule, weekly_schedule: schedule.weekly_schedule })); }}>
        <label className="block"><input type="checkbox" checked={schedule.restrict_outside_schedule} onChange={event => { setDirty(true); setSchedule({ ...schedule, restrict_outside_schedule: event.target.checked }); }} /> Restringir acceso fuera del horario</label>
        <p>Sin ventanas y con restricción activa, solo las horas extra permiten entrar. Para turnos nocturnos use dos días; 24:00 significa el final del día.</p>
        {days.map((label, weekday) => <div key={label} className="flex flex-wrap items-center gap-2 rounded border p-2"><strong className="w-24">{label}</strong>
          {!schedule.weekly_schedule.some(window => window.day === weekday) && <span>Sin acceso habitual</span>}
          {schedule.weekly_schedule.map((window, index) => window.day === weekday && <div key={index} className="flex items-center gap-2">
            <input aria-label={`${label} inicio ${index + 1}`} className={field} required type="time" value={window.start} onChange={event => editWindow(index, "start", event.target.value)} />
            <span>a</span><input aria-label={`${label} fin ${index + 1}`} className={`${field} w-24`} required pattern="(?:(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00)" placeholder="17:00" value={window.end} onChange={event => editWindow(index, "end", event.target.value)} />
            <button type="button" aria-label={`Quitar ventana ${label} ${index + 1}`} onClick={() => { setDirty(true); setSchedule({ ...schedule, weekly_schedule: schedule.weekly_schedule.filter((_, i) => i !== index) }); }}>Quitar</button>
          </div>)}
          <button type="button" disabled={schedule.weekly_schedule.length >= 28} onClick={() => { setDirty(true); setSchedule({ ...schedule, weekly_schedule: [...schedule.weekly_schedule, { day: weekday, start: "08:00", end: "17:00" }] }); }}>Añadir ventana {label}</button>
        </div>)}
        <button className={field}>Guardar horario</button>
      </form>
      <fieldset disabled={dirty} className="space-y-4">
      <form className="flex flex-wrap items-end gap-3 border-t pt-4" onSubmit={event => { event.preventDefault(); void save(() => api.post(`${path}/exceptions`, { starts_at: start, ends_at: end, reason })); }}>
        <h4 className="w-full font-bold">Autorizar horas extra</h4>
        <label>Desde<input className={`block ${field}`} required type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></label>
        <label>Hasta<input className={`block ${field}`} required type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} /></label>
        <label>Motivo de horas extra<input className={`block ${field}`} required maxLength={300} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <button className={field}>Autorizar excepción</button>
      </form>
      <ul>{schedule.exceptions.map(item => <li key={item.id} className="border-b py-2">{format(item.starts_at)} a {format(item.ends_at)} · {item.reason} · Autorizó: {author(item.authorized_by)} <button onClick={() => void save(() => api.delete(`${path}/exceptions/${item.id}`))}>Retirar excepción {item.id}</button></li>)}</ul>
      <form className="flex flex-wrap items-end gap-3 border-t pt-4" onSubmit={event => { event.preventDefault(); void save(() => api.post(`${path}/blocked-dates`, { day, reason: blockReason })); }}>
        <h4 className="w-full font-bold">Días sin acceso</h4>
        <label>Fecha bloqueada<input className={`block ${field}`} required type="date" value={day} onChange={event => setDay(event.target.value)} /></label>
        <label>Motivo de ausencia<input className={`block ${field}`} required maxLength={300} placeholder="Feriado, vacaciones, licencia…" value={blockReason} onChange={event => setBlockReason(event.target.value)} /></label>
        <button className={field}>Bloquear fecha</button>
      </form>
      <ul>{schedule.blocked_dates.map(item => <li key={item.id} className="border-b py-2">{item.day} · {item.reason} · Autorizó: {author(item.authorized_by)} <button onClick={() => void save(() => api.delete(`${path}/blocked-dates/${item.id}`))}>Retirar bloqueo {item.id}</button></li>)}</ul>
      <form className="space-y-2 border-t pt-4" onSubmit={event => { event.preventDefault(); setBusy(true); setError(""); void api.put("/administration/access-schedules/timezone", { timezone: zone }).then(() => {
        window.dispatchEvent(new CustomEvent("atlas-session-expired", { detail: "Zona horaria actualizada. Vuelva a iniciar sesión." }));
      }).catch(error => setError(errorMessage(error))).finally(() => setBusy(false)); }}>
        <label>Zona horaria de toda la organización <input className={field} required maxLength={64} value={zone} onChange={event => setZone(event.target.value)} placeholder="America/Santo_Domingo" /></label>
        <p>Use un nombre IANA, por ejemplo America/Santo_Domingo o Europe/Madrid. Este cambio afecta a todos los horarios y exige un nuevo inicio de sesión a todos los miembros.</p>
        <button className={field}>Actualizar zona horaria</button>
      </form>
      </fieldset>
    </fieldset>}
  </section>;
}
