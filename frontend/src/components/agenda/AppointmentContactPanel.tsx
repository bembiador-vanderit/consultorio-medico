import { useEffect, useState } from "react";
import { api } from "../../services/api";

type Result = "will_attend" | "will_not_attend" | "no_answer" | "retry";
type Filter = "" | "pending" | Result;
type Attempt = {
  id: number; appointment_id: number; contacted_by_name: string; contacted_at: string;
  contact_value: string | null; result: Result; notes: string | null;
};
type DailyItem = {
  appointment_id: number; patient_name: string; patient_phone: string | null;
  appointment_date: string; appointment_time: string | null; doctor_name: string;
  center_name: string | null; latest_contact: Attempt | null;
};
type Daily = {
  date: string;
  totals: { total_expected: number; contacted: number; not_contacted: number;
    will_attend: number; will_not_attend: number; no_answer: number; retry: number };
  items: DailyItem[];
};

const labels: Record<Result, string> = {
  will_attend: "Indicó que asistirá",
  will_not_attend: "Indicó que no asistirá",
  no_answer: "No respondió",
  retry: "Reintentar",
};
const options: { value: Filter; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "pending", label: "Pendientes de contactar" },
  { value: "will_attend", label: labels.will_attend },
  { value: "will_not_attend", label: labels.will_not_attend },
  { value: "no_answer", label: labels.no_answer },
  { value: "retry", label: labels.retry },
];
const stamp = (value: string) => {
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`;
  return new Date(normalized).toLocaleString("es-DO", { dateStyle: "short", timeStyle: "short" });
};
const errorText = (reason: any) => reason?.response?.data?.detail || "No fue posible completar la operación.";

export function AppointmentContactPanel({ initialDate, centerId, doctorId, canRecord }: {
  initialDate: string; centerId?: number; doctorId?: number; canRecord: boolean;
}) {
  const [day, setDay] = useState(initialDate);
  const [filter, setFilter] = useState<Filter>("");
  const [daily, setDaily] = useState<Daily | null>(null);
  const [selected, setSelected] = useState<DailyItem | null>(null);
  const [history, setHistory] = useState<Attempt[] | null>(null);
  const [result, setResult] = useState<Result>("will_attend");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    api.get<Daily>("/appointment-contacts", { params: {
      day, ...(centerId ? { center_id: centerId } : {}),
      ...(doctorId ? { doctor_id: doctorId } : {}), ...(filter ? { result: filter } : {}),
    } }).then(({ data }) => { if (active) setDaily(data); })
      .catch((reason) => { if (active) { setDaily(null); setError(errorText(reason)); } });
    return () => { active = false; };
  }, [day, centerId, doctorId, filter, refresh]);

  async function open(item: DailyItem) {
    setSelected(item);
    setPhone(item.patient_phone || "");
    setResult("will_attend");
    setNotes("");
    setHistory(null);
    setError("");
    try {
      const { data } = await api.get<Attempt[]>(`/appointment-contacts/${item.appointment_id}`);
      setHistory(data);
    } catch (reason) { setError(errorText(reason)); }
  }

  async function save() {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/appointment-contacts/${selected.appointment_id}`, {
        result, channel: "phone", contact_value: phone.trim() || null, notes: notes.trim() || null,
      });
      const { data } = await api.get<Attempt[]>(`/appointment-contacts/${selected.appointment_id}`);
      setHistory(data);
      setSelected(null);
      setRefresh((value) => value + 1);
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  return <section className="agenda-contact-panel rounded-xl border bg-white p-4 shadow-sm" aria-label="Contactos previos">
    <h2 className="text-lg font-semibold">Contactos previos a la cita</h2>
    <p className="mt-1 text-sm text-slate-600">Registro de llamadas; no confirma la cita ni asigna turnos. El orden de la lista es por hora de cita, no por llamada.</p>
    <div className="agenda-contact-context mt-4 flex flex-wrap gap-3">
      <label className="text-sm">Fecha<input type="date" className="ml-2 rounded border p-2" value={day} onChange={(event) => { setDay(event.target.value); setSelected(null); }} /></label>
      <label className="text-sm">Resultado<select className="ml-2 rounded border p-2" value={filter} onChange={(event) => setFilter(event.target.value as Filter)}>{options.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    {daily && <>
      <p className="agenda-contact-summary mt-4 text-sm" aria-label="Resumen de contactos">Previstos: {daily.totals.total_expected} · Contactados: {daily.totals.contacted} · Sin contactar: {daily.totals.not_contacted} · Asistirán: {daily.totals.will_attend} · No asistirán: {daily.totals.will_not_attend} · No respondieron: {daily.totals.no_answer} · Reintentar: {daily.totals.retry}</p>
      <div className="agenda-contact-cards mt-4 grid gap-3 lg:grid-cols-2">
        {daily.items.map((item) => <article key={item.appointment_id} className="agenda-contact-card rounded-lg border p-3">
          <strong className="block">{item.patient_name}</strong>
          <p className="text-sm">{item.patient_phone || "Sin teléfono"}</p>
          <p className="mt-1 text-sm text-slate-600">{item.appointment_date} · {item.appointment_time?.slice(0, 5) ?? "Por turno"} · {item.doctor_name}{item.center_name && ` · ${item.center_name}`}</p>
          <p className="mt-2 text-sm">Último contacto: <strong>{item.latest_contact ? labels[item.latest_contact.result] : "Pendiente de contactar"}</strong></p>
          {item.latest_contact && <p className="text-xs text-slate-600">{stamp(item.latest_contact.contacted_at)} · Registrado por: {item.latest_contact.contacted_by_name}</p>}
          <button type="button" className="mt-3 rounded border px-3 py-2 text-sm" onClick={() => void open(item)}>{canRecord ? "Registrar contacto / Ver historial" : "Ver historial"}</button>
        </article>)}
      </div>
      {daily.items.length === 0 && <p className="mt-4 text-sm text-slate-600">No hay citas previstas con este filtro.</p>}
    </>}
    {selected && <div className="agenda-contact-history mt-5 rounded-lg border bg-slate-50 p-4" aria-label="Historial de contacto">
      <div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{selected.patient_name} — historial</h3><button type="button" className="rounded border px-3 py-1" onClick={() => setSelected(null)}>Cerrar</button></div>
      {history === null ? <p className="mt-2 text-sm">Cargando historial…</p> : history.length === 0 ? <p className="mt-2 text-sm">Sin intentos registrados.</p> : <ol className="mt-2 space-y-2 text-sm">{history.map((attempt) => <li key={attempt.id} className="rounded border bg-white p-2">{stamp(attempt.contacted_at)} — {labels[attempt.result]} · {attempt.contacted_by_name}{attempt.contact_value && ` · ${attempt.contact_value}`}{attempt.notes && <p className="mt-1">{attempt.notes}</p>}</li>)}</ol>}
      {canRecord && <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <label className="text-sm">Resultado<select className="mt-1 block w-full rounded border p-2" value={result} onChange={(event) => setResult(event.target.value as Result)}>{options.filter((item) => item.value && item.value !== "pending").map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label className="text-sm">Teléfono utilizado (si aplica)<input className="mt-1 block w-full rounded border p-2" maxLength={30} value={phone} onChange={(event) => setPhone(event.target.value)} /></label>
        <label className="text-sm sm:col-span-2">Observación<textarea className="mt-1 block w-full rounded border p-2" maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <button type="button" className="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy || history === null} onClick={() => void save()}>Guardar intento</button>
      </div>}
    </div>}
  </section>;
}
