import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { ClinicalHistory, ClinicalHistoryInput } from "../../types/clinicalHistory";

type Props = { patientId: number; patientName: string; onClose: () => void };

const emptyFields = {
  reason_for_visit: "", current_illness: "", personal_history: "", family_history: "", allergies: "",
  current_medications: "", previous_surgeries: "", chronic_conditions: "", habits: "", clinical_notes: "",
  requested_tests: "",
};

const fields: Array<[keyof typeof emptyFields, string]> = [
  ["reason_for_visit", "Motivo de consulta"], ["current_illness", "Enfermedad actual"], ["personal_history", "Antecedentes personales"],
  ["family_history", "Antecedentes familiares"], ["allergies", "Alergias"], ["current_medications", "Medicamentos habituales"],
  ["previous_surgeries", "Cirugías previas"], ["chronic_conditions", "Enfermedades crónicas"], ["habits", "Hábitos"], ["clinical_notes", "Observaciones clínicas"],
];

function today() { return new Date().toISOString().slice(0, 10); }
function emptyHistory(): ClinicalHistoryInput { return { consultation_date: today(), ...emptyFields }; }
function formatDate(value: string) { return new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" }); }

export default function ClinicalHistoryPanel({ patientId, patientName, onClose }: Props) {
  const [records, setRecords] = useState<ClinicalHistory[]>([]); const [index, setIndex] = useState(0); const [form, setForm] = useState<ClinicalHistoryInput>(emptyHistory);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [isNew, setIsNew] = useState(false); const [showTests, setShowTests] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  const current = records[index];
  const positionLabel = useMemo(() => records.length ? `Consulta ${index + 1} de ${records.length}` : "Nueva consulta", [index, records.length]);

  useEffect(() => { async function load() { try { const { data } = await api.get<ClinicalHistory[]>(`/clinical-history/patients/${patientId}`); setRecords(data); if (data.length) { setIndex(0); setForm(data[0]); setIsNew(false); setShowTests(Boolean(data[0].requested_tests?.trim())); } else { setForm(emptyHistory()); setIsNew(true); } } catch (err: any) { setError(err?.response?.data?.detail || "No fue posible cargar la historia clínica."); } finally { setLoading(false); } } void load(); }, [patientId]);

  function showRecord(nextIndex: number) { setIndex(nextIndex); setForm(records[nextIndex]); setIsNew(false); setShowTests(Boolean(records[nextIndex].requested_tests?.trim())); setMessage(""); setError(""); }
  function newConsultation() { setForm(emptyHistory()); setIsNew(true); setShowTests(false); setMessage(""); setError(""); }
  async function save() { setSaving(true); setMessage(""); setError(""); try { if (isNew) { const { data } = await api.post<ClinicalHistory>(`/clinical-history/patients/${patientId}`, form); const nextRecords = [data, ...records].sort((a, b) => b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id); setRecords(nextRecords); setIndex(nextRecords.findIndex((record) => record.id === data.id)); setForm(data); setIsNew(false); } else if (current) { const { data } = await api.put<ClinicalHistory>(`/clinical-history/${current.id}`, form); const nextRecords = records.map((record) => record.id === data.id ? data : record).sort((a, b) => b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id); setRecords(nextRecords); setIndex(nextRecords.findIndex((record) => record.id === data.id)); setForm(data); } setMessage("Historia clínica guardada correctamente."); } catch (err: any) { setError(err?.response?.data?.detail || "No fue posible guardar la historia clínica."); } finally { setSaving(false); } }

  function printTests() {
    const items = (form.requested_tests || "").split("\n").map((item) => item.trim()).filter(Boolean); if (!items.length) return;
    const popup = window.open("", "_blank", "width=800,height=900"); if (!popup) return;
    const escape = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
    popup.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Orden de análisis y pruebas</title><style>body{font-family:Arial,sans-serif;margin:48px;color:#111}h1{font-size:22px}.muted{color:#555;font-size:13px}.item{padding:10px 0;border-bottom:1px solid #ddd}footer{margin-top:70px;color:#666;font-size:12px}</style></head><body><h1>Orden de análisis y pruebas</h1><p class="muted"><strong>Paciente:</strong> ${escape(patientName)}</p><p class="muted"><strong>Fecha de consulta:</strong> ${escape(formatDate(form.consultation_date))}</p><hr/>${items.map((item) => `<div class="item">☐ ${escape(item)}</div>`).join("")}<footer>Documento emitido por el médico tratante.</footer><script>window.onload=()=>window.print()</script></body></html>`); popup.document.close();
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"><div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white shadow-xl"><div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4"><div><h3 className="text-xl font-bold">Historia clínica</h3><p className="text-sm text-slate-500">{patientName}</p></div><button onClick={onClose} className="text-2xl text-slate-500 hover:text-slate-900" aria-label="Cerrar">×</button></div>{loading ? <p className="p-6 text-slate-500">Cargando historia clínica...</p> : <div className="space-y-5 p-6"><div className="rounded-xl border bg-slate-50 p-4"><div className="flex flex-wrap items-end justify-between gap-4"><div><label className="mb-1 block text-sm font-medium text-slate-700">Fecha de la consulta</label><input type="date" value={form.consultation_date} onChange={(event) => setForm({ ...form, consultation_date: event.target.value })} className="rounded-lg border border-slate-300 bg-white px-3 py-2"/><p className="mt-1 text-xs text-slate-500">{positionLabel}</p></div><div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => showRecord(index + 1)} disabled={isNew || index >= records.length - 1} className="rounded-lg border px-4 py-2 font-medium disabled:opacity-40">← Anterior</button><button type="button" onClick={() => showRecord(index - 1)} disabled={isNew || index <= 0} className="rounded-lg border px-4 py-2 font-medium disabled:opacity-40">Siguiente →</button><button type="button" onClick={newConsultation} className="rounded-lg bg-slate-700 px-4 py-2 font-medium text-white">Nueva consulta</button></div></div></div>{fields.map(([name, label]) => <label key={name} className="block"><span className="mb-1 block text-sm font-medium text-slate-700">{label}</span><textarea value={form[name] ?? ""} onChange={(event) => setForm({ ...form, [name]: event.target.value })} rows={3} className="w-full rounded-lg border border-slate-300 px-3 py-2"/></label>)}

  <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="font-semibold text-indigo-900">Análisis y pruebas indicadas</h4><p className="text-xs text-indigo-700">Opcional. Se guarda como parte de esta consulta.</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => setShowTests((value) => !value)} className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-800">{showTests ? "Ocultar" : "Agregar análisis / pruebas"}</button><button type="button" onClick={printTests} disabled={!form.requested_tests?.trim()} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">🖨️ Imprimir orden</button></div></div>{showTests && <label className="mt-4 block"><span className="mb-1 block text-sm font-medium text-slate-700">Un análisis o prueba por línea</span><textarea value={form.requested_tests ?? ""} onChange={(event) => setForm({ ...form, requested_tests: event.target.value })} rows={7} placeholder={'Hemograma\nGlucosa en sangre\nPerfil lipídico\nRadiografía de tórax'} className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2"/><p className="mt-1 text-xs text-slate-500">Puedes escribir el nombre del análisis, estudio de imagen o prueba que el paciente debe realizar.</p></label>}</div>

  {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}{message && <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}<div className="flex justify-end gap-3 border-t pt-5"><button onClick={onClose} className="rounded-lg border border-slate-300 px-5 py-2 font-medium">Cerrar</button><button onClick={() => void save()} disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-50">{saving ? "Guardando..." : isNew ? "Guardar consulta" : "Guardar cambios"}</button></div></div>}</div></div>;
}
