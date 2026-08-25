import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { ClinicalHistory, ClinicalHistoryInput } from "../../types/clinicalHistory";

type Props = { patientId: number; patientName: string; onClose: () => void };
type RequestedTest = { id?: number; test_name: string };

type FollowUpForm = {
  due_at: string;
  reason: string;
  priority: "low" | "normal" | "high" | "urgent";
  notes: string;
};

const emptyFields = {
  reason_for_visit: "",
  current_illness: "",
  personal_history: "",
  family_history: "",
  allergies: "",
  current_medications: "",
  previous_surgeries: "",
  chronic_conditions: "",
  habits: "",
  clinical_notes: "",
  requested_tests: "",
};

const fields: Array<[keyof typeof emptyFields, string]> = [
  ["reason_for_visit", "Motivo de consulta"],
  ["current_illness", "Enfermedad actual"],
  ["personal_history", "Antecedentes personales"],
  ["family_history", "Antecedentes familiares"],
  ["allergies", "Alergias"],
  ["current_medications", "Medicamentos habituales"],
  ["previous_surgeries", "Cirugías previas"],
  ["chronic_conditions", "Enfermedades crónicas"],
  ["habits", "Hábitos"],
  ["clinical_notes", "Observaciones clínicas"],
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function defaultFollowUpDate() {
  const value = new Date(Date.now() + 24 * 60 * 60 * 1000);
  value.setHours(9, 0, 0, 0);
  const offset = value.getTimezoneOffset();
  return new Date(value.getTime() - offset * 60000).toISOString().slice(0, 16);
}

function emptyHistory(): ClinicalHistoryInput {
  return { consultation_date: today(), ...emptyFields };
}

function emptyFollowUp(): FollowUpForm {
  return { due_at: defaultFollowUpDate(), reason: "", priority: "normal", notes: "" };
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function historySummary(record: ClinicalHistory) {
  return record.reason_for_visit || record.current_illness || record.clinical_notes || "Consulta registrada";
}

export default function ClinicalHistoryPanel({ patientId, patientName, onClose }: Props) {
  const [records, setRecords] = useState<ClinicalHistory[]>([]);
  const [index, setIndex] = useState(0);
  const [form, setForm] = useState<ClinicalHistoryInput>(emptyHistory);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [showTests, setShowTests] = useState(false);
  const [showFullPrevious, setShowFullPrevious] = useState<number | null>(null);
  const [previousTests, setPreviousTests] = useState<Record<number, string[]>>({});
  const [showFollowUp, setShowFollowUp] = useState(false);
  const [followUp, setFollowUp] = useState<FollowUpForm>(emptyFollowUp);
  const [savingFollowUp, setSavingFollowUp] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [followUpError, setFollowUpError] = useState("");

  const current = records[index];
  const positionLabel = useMemo(() => (records.length ? `Consulta ${index + 1} de ${records.length}` : "Nueva consulta"), [index, records.length]);

  async function loadTests(historyId: number) {
    const { data } = await api.get<RequestedTest[]>(`/clinical-history/${historyId}/requested-tests`);
    return data.map((item) => item.test_name);
  }

  async function load() {
    try {
      const { data } = await api.get<ClinicalHistory[]>(`/clinical-history/patients/${patientId}`);
      setRecords(data);
      if (data.length) {
        const tests = await loadTests(data[0].id);
        setIndex(0);
        setForm({ ...data[0], requested_tests: tests.join("\n") });
        setIsNew(false);
        setShowTests(Boolean(tests.length));
        setPreviousTests({ [data[0].id]: tests });
      } else {
        setForm(emptyHistory());
        setIsNew(true);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible cargar la historia clínica.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [patientId]);

  async function showRecord(nextIndex: number) {
    const record = records[nextIndex];
    const tests = await loadTests(record.id);
    setIndex(nextIndex);
    setForm({ ...record, requested_tests: tests.join("\n") });
    setIsNew(false);
    setShowTests(Boolean(tests.length));
    setMessage("");
    setError("");
  }

  function newConsultation() {
    setForm(emptyHistory());
    setIsNew(true);
    setShowTests(false);
    setMessage("");
    setError("");
  }

  async function loadPreviousTests(historyId: number) {
    if (previousTests[historyId]) return previousTests[historyId];
    try {
      const tests = await loadTests(historyId);
      setPreviousTests((currentTests) => ({ ...currentTests, [historyId]: tests }));
      return tests;
    } catch { return []; }
  }

  async function openPreviousRecord(historyId: number) {
    await loadPreviousTests(historyId);
    setShowFullPrevious((currentValue) => (currentValue === historyId ? null : historyId));
  }

  async function syncTests(historyId: number) {
    const { data } = await api.get<RequestedTest[]>(`/clinical-history/${historyId}/requested-tests`);
    for (const item of data) if (item.id) await api.delete(`/clinical-history/requested-tests/${item.id}`);
    const tests = (form.requested_tests || "").split("\n").map((value) => value.trim()).filter(Boolean);
    for (const test_name of tests) await api.post(`/clinical-history/${historyId}/requested-tests`, { test_name });
    setPreviousTests((currentTests) => ({ ...currentTests, [historyId]: tests }));
  }

  async function save() {
    setSaving(true); setMessage(""); setError("");
    try {
      const historyPayload = { ...form };
      delete (historyPayload as any).requested_tests;
      let saved: ClinicalHistory;
      if (isNew) {
        const { data } = await api.post<ClinicalHistory>(`/clinical-history/patients/${patientId}`, historyPayload);
        saved = data;
      } else if (current) {
        const { data } = await api.put<ClinicalHistory>(`/clinical-history/${current.id}`, historyPayload);
        saved = data;
      } else return;
      await syncTests(saved.id);
      const nextRecords = (isNew ? [saved, ...records] : records.map((record) => record.id === saved.id ? saved : record))
        .sort((a, b) => b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id);
      setRecords(nextRecords);
      setIndex(nextRecords.findIndex((record) => record.id === saved.id));
      setForm({ ...saved, requested_tests: form.requested_tests || "" });
      setIsNew(false);
      setMessage("Historia clínica y análisis/pruebas guardados correctamente.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible guardar la historia clínica.");
    } finally { setSaving(false); }
  }

  function openFollowUp() {
    setFollowUp(emptyFollowUp());
    setFollowUpError("");
    setShowFollowUp(true);
  }

  async function createFollowUp() {
    if (!current || isNew) {
      setFollowUpError("Guarda primero la consulta actual para poder vincular el seguimiento.");
      return;
    }
    if (!followUp.reason.trim() || !followUp.due_at) {
      setFollowUpError("Indica la fecha/hora y el motivo del seguimiento.");
      return;
    }
    setSavingFollowUp(true); setFollowUpError("");
    try {
      await api.post("/follow-ups", {
        patient_id: patientId,
        clinical_history_id: current.id,
        due_at: new Date(followUp.due_at).toISOString(),
        reason: followUp.reason.trim(),
        priority: followUp.priority,
        notes: followUp.notes.trim() || null,
      });
      setShowFollowUp(false);
      setMessage("Seguimiento programado correctamente. Se creó una notificación para el médico.");
    } catch (err: any) {
      setFollowUpError(err?.response?.data?.detail || "No fue posible crear el seguimiento.");
    } finally { setSavingFollowUp(false); }
  }

  function printTests() {
    const items = (form.requested_tests || "").split("\n").map((value) => value.trim()).filter(Boolean);
    if (!items.length) return;
    const popup = window.open("", "_blank", "width=800,height=900");
    if (!popup) return;
    const escape = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
    popup.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Orden de análisis y pruebas</title><style>body{font-family:Arial,sans-serif;margin:48px;color:#111}h1{font-size:22px}.muted{color:#555;font-size:13px}.item{padding:10px 0;border-bottom:1px solid #ddd}footer{margin-top:70px;color:#666;font-size:12px}</style></head><body><h1>Orden de análisis y pruebas</h1><p class="muted"><strong>Paciente:</strong> ${escape(patientName)}</p><p class="muted"><strong>Fecha de consulta:</strong> ${escape(formatDate(form.consultation_date))}</p><hr/>${items.map((item) => `<div class="item">☐ ${escape(item)}</div>`).join("")}<footer>Documento emitido por el médico tratante.</footer><script>window.onload=()=>window.print()</script></body></html>`);
    popup.document.close();
  }

  const previousRecords = records.filter((record) => record.id !== current?.id).slice(0, 6);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="max-h-[94vh] w-full max-w-7xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="sticky top-0 z-20 flex items-center justify-between border-b bg-white px-6 py-4">
          <div><h3 className="text-xl font-bold">Historia clínica</h3><p className="text-sm text-slate-500">{patientName}</p></div>
          <button onClick={onClose} className="text-2xl text-slate-500" aria-label="Cerrar">×</button>
        </div>

        {loading ? <p className="p-6 text-slate-500">Cargando historia clínica...</p> : (
          <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <section className="min-w-0 space-y-5">
              <div className="rounded-xl border bg-slate-50 p-4">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div><label className="mb-1 block text-sm font-medium">Fecha de la consulta</label><input type="date" value={form.consultation_date} onChange={(event) => setForm({ ...form, consultation_date: event.target.value })} className="rounded-lg border px-3 py-2" /><p className="mt-1 text-xs text-slate-500">{positionLabel}</p></div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void showRecord(index + 1)} disabled={isNew || index >= records.length - 1} className="rounded-lg border px-4 py-2 disabled:opacity-40">← Anterior</button>
                    <button type="button" onClick={() => void showRecord(index - 1)} disabled={isNew || index <= 0} className="rounded-lg border px-4 py-2 disabled:opacity-40">Siguiente →</button>
                    <button type="button" onClick={newConsultation} className="rounded-lg bg-slate-700 px-4 py-2 text-white">Nueva consulta</button>
                    <button type="button" onClick={openFollowUp} disabled={isNew || !current} className="rounded-lg bg-amber-600 px-4 py-2 font-medium text-white disabled:opacity-40">⏰ Programar seguimiento</button>
                  </div>
                </div>
              </div>

              {fields.map(([name, label]) => <label key={name} className="block"><span className="mb-1 block text-sm font-medium">{label}</span><textarea value={form[name] ?? ""} onChange={(event) => setForm({ ...form, [name]: event.target.value })} rows={3} className="w-full rounded-lg border px-3 py-2" /></label>)}

              <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="font-semibold text-indigo-900">Análisis y pruebas indicadas</h4><p className="text-xs text-indigo-700">Opcional y asociado a esta consulta.</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => setShowTests((value) => !value)} className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-800">{showTests ? "Ocultar" : "Agregar análisis / pruebas"}</button><button type="button" onClick={printTests} disabled={!form.requested_tests?.trim()} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">🖨️ Imprimir orden</button></div></div>
                {showTests && <label className="mt-4 block"><span className="mb-1 block text-sm font-medium">Un análisis o prueba por línea</span><textarea value={form.requested_tests ?? ""} onChange={(event) => setForm({ ...form, requested_tests: event.target.value })} rows={7} placeholder={'Hemograma\nGlucosa en sangre\nPerfil lipídico\nRadiografía de tórax'} className="w-full rounded-lg border bg-white px-3 py-2" /></label>}
              </div>

              {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
              {message && <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}
              <div className="flex justify-end gap-3 border-t pt-5"><button onClick={onClose} className="rounded-lg border px-5 py-2">Cerrar</button><button onClick={() => void save()} disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 text-white disabled:opacity-50">{saving ? "Guardando..." : isNew ? "Guardar consulta" : "Guardar cambios"}</button></div>
            </section>

            <aside className="lg:sticky lg:top-20 lg:self-start"><div className="rounded-xl border bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><h4 className="font-semibold">Consultas anteriores</h4><p className="text-xs text-slate-500">Historial reciente del paciente</p></div><span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600">{previousRecords.length}</span></div>
              {previousRecords.length === 0 ? <p className="mt-4 rounded-lg border border-dashed bg-white p-4 text-sm text-slate-500">No hay consultas anteriores para mostrar.</p> : <div className="mt-4 space-y-3">{previousRecords.map((record) => { const tests = previousTests[record.id] || []; const isExpanded = showFullPrevious === record.id; return <article key={record.id} className="rounded-lg border bg-white p-3 shadow-sm"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{formatDate(record.consultation_date)}</p><p className="mt-1 font-medium text-slate-900">{historySummary(record)}</p></div><button type="button" onClick={() => void openPreviousRecord(record.id)} className="shrink-0 text-xs font-semibold text-indigo-700 hover:underline">{isExpanded ? "Ocultar" : "Ver completa"}</button></div><div className="mt-2 space-y-1 text-xs text-slate-600">{record.chronic_conditions && <p><strong>Crónicas:</strong> {record.chronic_conditions}</p>}{record.allergies && <p><strong>Alergias:</strong> {record.allergies}</p>}{record.current_medications && <p><strong>Medicamentos:</strong> {record.current_medications}</p>}{tests.length > 0 && <p><strong>Pruebas:</strong> {tests.length}</p>}</div>{isExpanded && <div className="mt-3 space-y-2 border-t pt-3 text-xs text-slate-700">{record.current_illness && <p><strong>Enfermedad actual:</strong> {record.current_illness}</p>}{record.personal_history && <p><strong>Antecedentes personales:</strong> {record.personal_history}</p>}{record.family_history && <p><strong>Antecedentes familiares:</strong> {record.family_history}</p>}{record.previous_surgeries && <p><strong>Cirugías:</strong> {record.previous_surgeries}</p>}{record.habits && <p><strong>Hábitos:</strong> {record.habits}</p>}{record.clinical_notes && <p><strong>Observaciones:</strong> {record.clinical_notes}</p>}{tests.length > 0 && <div><p className="font-semibold">Análisis/pruebas:</p><ul className="mt-1 list-disc pl-4">{tests.map((test) => <li key={test}>{test}</li>)}</ul></div>}</div>}</article>; })}</div>}
            </div></aside>
          </div>
        )}

        {showFollowUp && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><div className="flex items-start justify-between"><div><h3 className="text-lg font-bold">Programar seguimiento</h3><p className="text-sm text-slate-500">{patientName} · consulta del {current ? formatDate(current.consultation_date) : ""}</p></div><button type="button" onClick={() => setShowFollowUp(false)} className="text-2xl text-slate-400">×</button></div><div className="mt-5 space-y-4"><label className="block"><span className="mb-1 block text-sm font-medium">Fecha y hora</span><input type="datetime-local" value={followUp.due_at} onChange={(event) => setFollowUp({ ...followUp, due_at: event.target.value })} className="w-full rounded-lg border px-3 py-2" /></label><label className="block"><span className="mb-1 block text-sm font-medium">Motivo</span><input value={followUp.reason} onChange={(event) => setFollowUp({ ...followUp, reason: event.target.value })} placeholder="Revisar resultados de laboratorio" className="w-full rounded-lg border px-3 py-2" /></label><label className="block"><span className="mb-1 block text-sm font-medium">Prioridad</span><select value={followUp.priority} onChange={(event) => setFollowUp({ ...followUp, priority: event.target.value as FollowUpForm["priority"] })} className="w-full rounded-lg border px-3 py-2"><option value="low">Baja</option><option value="normal">Normal</option><option value="high">Alta</option><option value="urgent">Urgente</option></select></label><label className="block"><span className="mb-1 block text-sm font-medium">Notas</span><textarea value={followUp.notes} onChange={(event) => setFollowUp({ ...followUp, notes: event.target.value })} rows={3} placeholder="Indicaciones para el seguimiento" className="w-full rounded-lg border px-3 py-2" /></label>{followUpError && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{followUpError}</div>}<div className="flex justify-end gap-3 border-t pt-4"><button type="button" onClick={() => setShowFollowUp(false)} className="rounded-lg border px-4 py-2">Cancelar</button><button type="button" onClick={() => void createFollowUp()} disabled={savingFollowUp} className="rounded-lg bg-amber-600 px-5 py-2 font-medium text-white disabled:opacity-50">{savingFollowUp ? "Programando..." : "Programar seguimiento"}</button></div></div></div></div>}
      </div>
    </div>
  );
}
