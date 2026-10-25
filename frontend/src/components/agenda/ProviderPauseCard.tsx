import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { PauseReason, ProviderPause } from "../../types/providerPause";

const reasons: { value: PauseReason; label: string }[] = [
  { value: "ward_rounds", label: "Pase de visita" },
  { value: "procedure", label: "Procedimiento" },
  { value: "emergency", label: "Emergencia" },
  { value: "meeting", label: "Reunión" },
  { value: "lunch", label: "Almuerzo" },
  { value: "temporary_absence", label: "Ausencia temporal" },
  { value: "other", label: "Otro" },
];
const labelFor = (reason: PauseReason) => reasons.find((item) => item.value === reason)?.label ?? reason;
const timestamp = (value: string) => new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`);
const message = (error: any) => error?.response?.data?.detail || "No fue posible completar la operación.";

export function ProviderPauseCard({ centerId, doctorId, doctorName, canManage, isAdmin }: {
  centerId: number; doctorId: number; doctorName: string; canManage: boolean; isAdmin: boolean;
}) {
  const [current, setCurrent] = useState<ProviderPause | null>(null);
  const [history, setHistory] = useState<ProviderPause[] | null>(null);
  const [reason, setReason] = useState<PauseReason | "">("");
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now());

  useEffect(() => {
    let active = true;
    setLoading(true);
    setCurrent(null);
    setHistory(null);
    setError("");
    void api.get<ProviderPause | null>("/provider-pauses/current", { params: { center_id: centerId, doctor_id: doctorId } })
      .then(({ data }) => { if (active) setCurrent(data); })
      .catch((failure) => { if (active) setError(message(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [centerId, doctorId]);

  useEffect(() => {
    if (!current) return;
    const timer = window.setInterval(() => setClock(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, [current]);

  async function loadHistory() {
    if (history) { setHistory(null); return; }
    try {
      const { data } = await api.get<ProviderPause[]>("/provider-pauses", { params: { center_id: centerId, doctor_id: doctorId } });
      setHistory(data);
    } catch (failure) { setError(message(failure)); }
  }

  async function start() {
    if (!reason || busy || !canManage) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post<ProviderPause>("/provider-pauses/start", {
        center_id: centerId, ...(isAdmin ? { doctor_id: doctorId } : {}), reason, notes: notes.trim() || null,
      });
      setCurrent(data); setHistory(null); setEditing(false); setReason(""); setNotes(""); setClock(Date.now());
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  }

  async function finish() {
    if (!current || busy || !canManage) return;
    setBusy(true); setError("");
    try {
      await api.post(`/provider-pauses/${current.id}/finish`);
      setCurrent(null); setHistory(null);
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  }

  const elapsed = current ? Math.max(0, Math.floor((clock - timestamp(current.actual_started_at).getTime()) / 60000)) : 0;
  return <section className={`agenda-pause-card${current ? " is-paused" : " is-available"}`} aria-label={`Pausa operativa de ${doctorName}`}>
    <div className="agenda-pause-card-heading"><strong>{doctorName}</strong><span className={`agenda-pause-status${current ? " is-paused" : " is-available"}`}>{loading ? "Consultando" : current ? "En pausa" : "Disponible"}</span></div>
    {loading ? <p className="text-sm">Consultando pausa…</p> : current ? <>
      <p className="agenda-pause-reason">{labelFor(current.reason)}</p>
      <p className="text-sm">Desde {timestamp(current.actual_started_at).toLocaleTimeString("es-DO", { hour: "2-digit", minute: "2-digit" })} · {elapsed} min transcurridos</p>
      {current.notes && <p className="text-sm text-slate-600">{current.notes}</p>}
      {canManage && <button type="button" className="mt-2 rounded border px-3 py-2 text-sm" disabled={busy} onClick={() => void finish()}>Finalizar pausa</button>}
    </> : <>
      <p className="text-sm text-emerald-800">DISPONIBLE · Sin pausa operativa</p>
      {canManage && !editing && <button type="button" className="mt-2 rounded border px-3 py-2 text-sm" onClick={() => setEditing(true)}>Iniciar pausa</button>}
      {canManage && editing && <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="text-sm">Motivo <select className="ml-2 rounded border p-2" value={reason} onChange={(event) => setReason(event.target.value as PauseReason | "")}><option value="">Seleccione</option>{reasons.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label className="text-sm">Observación <input className="ml-2 rounded border p-2" maxLength={1000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <button type="button" className="rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={!reason || busy} onClick={() => void start()}>Guardar inicio</button>
        <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => setEditing(false)}>Cancelar</button>
      </div>}
    </>}
    <button type="button" className="mt-2 block text-sm underline" onClick={() => void loadHistory()}>{history ? "Ocultar pausas anteriores" : "Ver historial de pausas"}</button>
    {history && <ol className="mt-2 space-y-1 text-xs text-slate-600">{history.map((item) => <li key={item.id}>{labelFor(item.reason)} · {timestamp(item.actual_started_at).toLocaleString("es-DO")} · {item.duration_seconds === null ? "En curso" : `${Math.floor(item.duration_seconds / 60)} min`}</li>)}</ol>}
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
  </section>;
}
