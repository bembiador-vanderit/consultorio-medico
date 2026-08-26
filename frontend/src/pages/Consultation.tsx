import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Appointment } from "../types/appointment";

type Props = { appointment: Appointment; onBack: () => void };
type Context = { appointment_id: number; patient_id: number; doctor_id: number; center_id: number | null; appointment_date: string; appointment_time: string; appointment_reason: string | null; appointment_status: string; previous_consultations: Consultation[] };
type Consultation = { id: number; patient_id: number; appointment_id: number | null; doctor_id: number | null; center_id: number | null; consultation_date: string; reason_for_visit: string | null; current_illness: string | null; personal_history: string | null; family_history: string | null; allergies: string | null; current_medications: string | null; previous_surgeries: string | null; chronic_conditions: string | null; habits: string | null; clinical_notes: string | null; created_at: string; updated_at: string };

type Form = Omit<Consultation, "id" | "patient_id" | "appointment_id" | "doctor_id" | "center_id" | "created_at" | "updated_at">;
const emptyForm = (reason: string | null): Form => ({ consultation_date: new Date().toISOString().slice(0, 10), reason_for_visit: reason || "", current_illness: "", personal_history: "", family_history: "", allergies: "", current_medications: "", previous_surgeries: "", chronic_conditions: "", habits: "", clinical_notes: "" });

export default function Consultation({ appointment, onBack }: Props) {
  const [context, setContext] = useState<Context | null>(null);
  const [form, setForm] = useState<Form>(emptyForm(appointment.reason));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Consultation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      setLoading(true); setError("");
      try {
        const { data } = await api.get<Context>(`/clinical-history/appointments/${appointment.id}/context`);
        setContext(data);
        setForm(emptyForm(data.appointment_reason));
      } catch (e: any) { setError(e?.response?.data?.detail || "No fue posible cargar el contexto de la consulta."); }
      finally { setLoading(false); }
    })();
  }, [appointment.id]);

  function update(field: keyof Form, value: string) { setForm((current) => ({ ...current, [field]: value })); }

  async function save() {
    if (!context) return;
    setSaving(true); setError(""); setSaved(null);
    try {
      const { data } = await api.post<Consultation>(`/clinical-history/patients/${context.patient_id}`, { ...form, appointment_id: context.appointment_id });
      setSaved(data);
      setContext((current) => current ? { ...current, previous_consultations: [data, ...current.previous_consultations] } : current);
    } catch (e: any) { setError(e?.response?.data?.detail || "No fue posible guardar la consulta."); }
    finally { setSaving(false); }
  }

  if (loading) return <section><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver a la agenda</button><p className="mt-6 text-slate-500">Cargando contexto de atención...</p></section>;

  return <section>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver a la agenda</button><h2 className="mt-2 text-2xl font-bold">Consulta médica</h2><p className="mt-1 text-sm text-slate-500">La consulta queda vinculada automáticamente con la cita, médico y centro.</p></div><div className="rounded-lg bg-teal-50 px-4 py-2 text-sm text-teal-900"><strong>Cita #{appointment.id}</strong><br />{appointment.appointment_date} · {appointment.appointment_time.slice(0, 5)}</div></div>
    {error && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {saved && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">Consulta guardada correctamente. ID #{saved.id} · cita #{saved.appointment_id}.</div>}
    <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="rounded-xl border bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold">Historia de la consulta</h3>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm font-medium">Fecha de consulta<input type="date" value={form.consultation_date} onChange={(e) => update("consultation_date", e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" required /></label>
          <label className="text-sm font-medium">Motivo de consulta<input value={form.reason_for_visit || ""} onChange={(e) => update("reason_for_visit", e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" /></label>
          <Field label="Enfermedad actual" value={form.current_illness || ""} onChange={(v) => update("current_illness", v)} />
          <Field label="Antecedentes personales" value={form.personal_history || ""} onChange={(v) => update("personal_history", v)} />
          <Field label="Antecedentes familiares" value={form.family_history || ""} onChange={(v) => update("family_history", v)} />
          <Field label="Alergias" value={form.allergies || ""} onChange={(v) => update("allergies", v)} />
          <Field label="Medicamentos actuales" value={form.current_medications || ""} onChange={(v) => update("current_medications", v)} />
          <Field label="Cirugías previas" value={form.previous_surgeries || ""} onChange={(v) => update("previous_surgeries", v)} />
          <Field label="Enfermedades crónicas" value={form.chronic_conditions || ""} onChange={(v) => update("chronic_conditions", v)} />
          <Field label="Hábitos" value={form.habits || ""} onChange={(v) => update("habits", v)} />
        </div>
        <label className="mt-4 block text-sm font-medium">Notas clínicas<textarea value={form.clinical_notes || ""} onChange={(e) => update("clinical_notes", e.target.value)} rows={5} className="mt-1 w-full rounded-lg border p-2.5" /></label>
        <div className="mt-6 flex justify-end"><button onClick={() => void save()} disabled={saving || !context} className="rounded-lg bg-teal-700 px-5 py-2.5 font-medium text-white disabled:opacity-50">{saving ? "Guardando..." : "Guardar consulta"}</button></div>
      </div>
      <aside className="space-y-4">
        <div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Contexto de atención</h3><dl className="mt-3 space-y-3 text-sm"><div><dt className="text-slate-500">Paciente</dt><dd className="font-semibold">{appointment.patient_name}</dd></div><div><dt className="text-slate-500">Médico</dt><dd className="font-semibold">{appointment.doctor_name}</dd></div><div><dt className="text-slate-500">Centro</dt><dd className="font-semibold">{appointment.center_name ? `${appointment.center_name}${appointment.center_city ? ` · ${appointment.center_city}` : ""}` : "Sin centro"}</dd></div><div><dt className="text-slate-500">Motivo de la cita</dt><dd>{appointment.reason || "—"}</dd></div></dl><div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">appointment_id: <strong>{context?.appointment_id}</strong><br />doctor_id: <strong>{context?.doctor_id}</strong><br />center_id: <strong>{context?.center_id ?? "NULL"}</strong></div></div>
        <div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Consultas anteriores</h3>{context?.previous_consultations.length ? <div className="mt-3 space-y-3">{context.previous_consultations.slice(0, 5).map((item) => <div key={item.id} className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">{item.consultation_date}</p><p className="mt-1 text-slate-600">{item.reason_for_visit || "Sin motivo registrado"}</p></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No hay consultas anteriores.</p>}</div>
      </aside>
    </div>
  </section>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label className="text-sm font-medium">{label}<textarea value={value} onChange={(e) => onChange(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border p-2.5" /></label>; }
