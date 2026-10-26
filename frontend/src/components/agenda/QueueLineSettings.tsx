import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { QueueLine } from "../../types/queue";
import { QueueCallPolicySettings } from "./QueueCallPolicySettings";

type Doctor = { id: number; full_name: string; centerIds: number[] };
type Center = { id: number; name: string };
const errorText = (reason: any) => reason?.response?.data?.detail || "No fue posible guardar la línea.";

export function QueueLineSettings({ doctors, centers, showCallPolicy = false }: { doctors: Doctor[]; centers: Center[]; showCallPolicy?: boolean }) {
  const [lines, setLines] = useState<QueueLine[]>([]);
  const [centerId, setCenterId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [name, setName] = useState("");
  const [prefix, setPrefix] = useState("");
  const [drafts, setDrafts] = useState<Record<number, { name: string; prefix: string; is_active: boolean; call_on_consultation_start: boolean }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      const { data } = await api.get<QueueLine[]>("/queue-lines");
      setLines(data);
      setDrafts(Object.fromEntries(data.map((line) => [line.id, { name: line.name, prefix: line.prefix, is_active: line.is_active, call_on_consultation_start: line.call_on_consultation_start ?? false }])));
      setError("");
    } catch (reason) { setError(errorText(reason)); }
  }
  useEffect(() => { void load(); }, []);

  async function create() {
    if (!centerId || !doctorId || !name.trim() || !prefix.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/queue-lines", { center_id: Number(centerId), doctor_id: Number(doctorId),
        specialty_id: null, name: name.trim(), prefix: prefix.trim().toUpperCase(), call_on_consultation_start: false });
      setName(""); setPrefix("");
      await load();
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  async function update(line: QueueLine) {
    const draft = drafts[line.id];
    if (!draft || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.put(`/queue-lines/${line.id}`, { name: draft.name.trim(), prefix: draft.prefix.trim().toUpperCase(), is_active: draft.is_active,
        ...(showCallPolicy ? {} : { call_on_consultation_start: draft.call_on_consultation_start }) });
      await load();
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  return <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm" aria-label="Líneas de turnos">
    <h3 className="font-semibold">Líneas de turnos</h3>
    <p className="mt-1 text-sm text-slate-500">Cada línea pertenece a un médico y centro. Su prefijo no depende de quién registre la llegada.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <label className="text-sm">Centro<select className="mt-1 w-full rounded border p-2" value={centerId} onChange={(event) => { setCenterId(event.target.value); setDoctorId(""); }}><option value="">Seleccione</option>{centers.map((center) => <option key={center.id} value={center.id}>{center.name}</option>)}</select></label>
      <label className="text-sm">Médico<select className="mt-1 w-full rounded border p-2" value={doctorId} onChange={(event) => setDoctorId(event.target.value)}><option value="">Seleccione</option>{doctors.filter((doctor) => doctor.centerIds.includes(Number(centerId))).map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.full_name}</option>)}</select></label>
      <label className="text-sm">Nombre<input className="mt-1 w-full rounded border p-2" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label className="text-sm">Prefijo<input className="mt-1 w-full rounded border p-2 uppercase" maxLength={4} value={prefix} onChange={(event) => setPrefix(event.target.value)} /></label>
      <button type="button" className="self-end rounded bg-teal-700 px-3 py-2 text-white disabled:opacity-50" disabled={busy || !centerId || !doctorId || !name.trim() || !prefix.trim()} onClick={() => void create()}>Crear línea</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    <div className="mt-4 space-y-3">{lines.map((line) => {
      const draft = drafts[line.id];
      return <div key={line.id} className="grid gap-2 rounded-lg border p-3 text-sm sm:grid-cols-5">
        <p>{line.doctor_name}<br /><span className="text-slate-500">{line.center_name}</span></p>
        <label>Nombre<input className="mt-1 w-full rounded border p-2" maxLength={120} value={draft?.name ?? line.name} onChange={(event) => setDrafts((current) => ({ ...current, [line.id]: { ...current[line.id], name: event.target.value } }))} /></label>
        <label>Prefijo<input className="mt-1 w-full rounded border p-2 uppercase" maxLength={4} value={draft?.prefix ?? line.prefix} onChange={(event) => setDrafts((current) => ({ ...current, [line.id]: { ...current[line.id], prefix: event.target.value } }))} /></label>
        <div className="flex flex-wrap items-end gap-2"><label className="flex items-center gap-1"><input type="checkbox" checked={draft?.is_active ?? line.is_active} onChange={(event) => setDrafts((current) => ({ ...current, [line.id]: { ...current[line.id], is_active: event.target.checked } }))} /> Activa</label>{!showCallPolicy && <label className="flex items-center gap-1"><input type="checkbox" checked={draft?.call_on_consultation_start ?? line.call_on_consultation_start ?? false} onChange={(event) => setDrafts((current) => ({ ...current, [line.id]: { ...current[line.id], call_on_consultation_start: event.target.checked } }))} /> Iniciar también llama</label>}<button type="button" className="rounded border px-3 py-2 disabled:opacity-50" disabled={busy || !draft?.name.trim() || !draft?.prefix.trim()} onClick={() => void update(line)}>Guardar</button></div>
        {showCallPolicy && <QueueCallPolicySettings line={line} />}
      </div>;
    })}</div>
  </section>;
}
