import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import type { Patient } from "../types/patient";
import type { User } from "../types/user";

type FollowUp = {
  id: number;
  patient_id: number;
  doctor_id: number;
  clinical_history_id: number | null;
  center_id: number | null;
  due_at: string;
  reason: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: "pending" | "completed" | "cancelled";
  notes: string | null;
  created_at: string;
  completed_at: string | null;
};

type Props = { user: User; onBack: () => void };

export default function FollowUps({ user, onBack }: Props) {
  const [items, setItems] = useState<FollowUp[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [patientId, setPatientId] = useState<number | "">("");
  const [dueAt, setDueAt] = useState("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState<FollowUp["priority"]>("normal");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const [followUps, patientResponse] = await Promise.all([
      api.get<FollowUp[]>("/follow-ups"),
      api.get<Patient[]>("/patients", { params: { limit: 100 } }),
    ]);
    setItems(followUps.data);
    setPatients(patientResponse.data);
  }

  useEffect(() => { void load().catch(() => setError("No fue posible cargar los seguimientos.")); }, []);

  const filteredPatients = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return patients.slice(0, 10);
    return patients.filter((p) => `${p.first_name} ${p.last_name}`.toLowerCase().includes(term)).slice(0, 10);
  }, [patients, query]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!patientId || !dueAt || !reason.trim()) return;
    try {
      setSaving(true); setError("");
      await api.post("/follow-ups", {
        patient_id: patientId,
        due_at: new Date(dueAt).toISOString(),
        reason: reason.trim(),
        priority,
        notes: notes.trim() || null,
        ...(user.roles.includes("admin") ? {} : { doctor_id: user.id }),
      });
      setPatientId(""); setQuery(""); setDueAt(""); setReason(""); setPriority("normal"); setNotes("");
      await load();
    } catch (reasonError) {
      console.error(reasonError); setError("No fue posible crear el seguimiento.");
    } finally { setSaving(false); }
  }

  async function complete(id: number) {
    await api.post(`/follow-ups/${id}/complete`);
    setItems((current) => current.map((item) => item.id === id ? { ...item, status: "completed", completed_at: new Date().toISOString() } : item));
  }

  return (
    <section>
      <button onClick={onBack} className="mb-4 text-sm font-semibold text-teal-700 hover:underline">← Volver</button>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-sm font-medium text-teal-700">Seguimientos</p><h2 className="mt-1 text-3xl font-bold">Seguimiento de pacientes</h2><p className="mt-2 text-slate-500">Programa recordatorios clínicos y genera automáticamente una notificación para el médico responsable.</p></div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <form onSubmit={submit} className="rounded-xl border bg-white p-6 shadow-sm">
          <h3 className="font-bold">Nuevo seguimiento</h3>
          {error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <label className="mt-5 block text-sm font-medium">Buscar paciente<input value={query} onChange={(e) => { setQuery(e.target.value); setPatientId(""); }} placeholder="Escriba nombre o apellido" className="mt-1 w-full rounded-lg border p-2.5" /></label>
          <div className="mt-2 max-h-36 overflow-auto rounded-lg border">
            {filteredPatients.map((patient) => <button type="button" key={patient.id} onClick={() => { setPatientId(patient.id); setQuery(`${patient.first_name} ${patient.last_name}`); }} className={`block w-full border-b px-3 py-2 text-left text-sm last:border-0 hover:bg-teal-50 ${patientId === patient.id ? "bg-teal-50 font-semibold" : ""}`}>{patient.first_name} {patient.last_name}</button>)}
            {filteredPatients.length === 0 && <p className="p-3 text-sm text-slate-500">No se encontraron pacientes.</p>}
          </div>
          <label className="mt-4 block text-sm font-medium">Fecha y hora<input required type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" /></label>
          <label className="mt-4 block text-sm font-medium">Motivo<input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ej. Revisar resultados de laboratorio" className="mt-1 w-full rounded-lg border p-2.5" /></label>
          <label className="mt-4 block text-sm font-medium">Prioridad<select value={priority} onChange={(e) => setPriority(e.target.value as FollowUp["priority"])} className="mt-1 w-full rounded-lg border p-2.5"><option value="low">Baja</option><option value="normal">Normal</option><option value="high">Alta</option><option value="urgent">Urgente</option></select></label>
          <label className="mt-4 block text-sm font-medium">Notas<textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border p-2.5" /></label>
          <button disabled={saving || !patientId} className="mt-5 w-full rounded-lg bg-teal-700 px-4 py-2.5 font-semibold text-white disabled:opacity-50">{saving ? "Guardando..." : "Crear seguimiento"}</button>
        </form>

        <div className="rounded-xl border bg-white p-6 shadow-sm">
          <h3 className="font-bold">Mis seguimientos</h3>
          <div className="mt-4 space-y-3">
            {items.length === 0 && <p className="text-sm text-slate-500">No hay seguimientos programados.</p>}
            {items.map((item) => {
              const patient = patients.find((p) => p.id === item.patient_id);
              return <div key={item.id} className={`rounded-lg border p-4 ${item.status === "completed" ? "opacity-60" : ""}`}>
                <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{patient ? `${patient.first_name} ${patient.last_name}` : `Paciente #${item.patient_id}`}</p><p className="text-sm text-slate-600">{item.reason}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold uppercase">{item.priority}</span></div>
                <p className="mt-2 text-sm text-slate-500">{new Date(item.due_at).toLocaleString("es-DO")}</p>
                {item.notes && <p className="mt-2 text-sm text-slate-600">{item.notes}</p>}
                {item.status !== "completed" && <button onClick={() => void complete(item.id)} className="mt-3 text-sm font-semibold text-teal-700 hover:underline">Marcar como completado</button>}
              </div>;
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
