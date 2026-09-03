import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { ClinicalHistory, ClinicalHistoryInput, RequestedTest } from "../../types/clinicalHistory";

type Props = { patientId: number; patientName: string; onClose: () => void };
type Diagnosis = { id: number; description: string; icd10_code: string | null; is_primary: boolean };
type Prescription = {
  id: number;
  medication: string;
  presentation: string | null;
  dose: string | null;
  route: string | null;
  frequency: string | null;
  duration: string | null;
  quantity: number | null;
  instructions: string | null;
};
type VitalSigns = {
  systolic_pressure: number | null;
  diastolic_pressure: number | null;
  heart_rate: number | null;
  respiratory_rate: number | null;
  temperature_c: number | null;
  oxygen_saturation: number | null;
  weight_kg: number | null;
  height_cm: number | null;
};
type ClinicalDetails = { diagnoses: Diagnosis[]; prescriptions: Prescription[]; tests: string[]; vitalSigns: VitalSigns | null };

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

function vitalSignItems(vitalSigns: VitalSigns | null | undefined) {
  if (!vitalSigns) return [];
  const items: Array<[string, string]> = [];
  if (vitalSigns.systolic_pressure !== null || vitalSigns.diastolic_pressure !== null) {
    items.push(["Presión arterial", `${vitalSigns.systolic_pressure ?? "-"}/${vitalSigns.diastolic_pressure ?? "-"} mmHg`]);
  }
  const measurements: Array<[string, number | null, string]> = [
    ["Frecuencia cardíaca", vitalSigns.heart_rate, "lpm"],
    ["Frecuencia respiratoria", vitalSigns.respiratory_rate, "rpm"],
    ["Temperatura", vitalSigns.temperature_c, "°C"],
    ["Saturación", vitalSigns.oxygen_saturation, "%"],
    ["Peso", vitalSigns.weight_kg, "kg"],
    ["Talla", vitalSigns.height_cm, "cm"],
  ];
  for (const [label, value, unit] of measurements) {
    if (value !== null) items.push([label, `${value} ${unit}`]);
  }
  return items;
}

export default function ClinicalHistoryPanel({ patientId, patientName, onClose }: Props) {
  const [records, setRecords] = useState<ClinicalHistory[]>([]);
  const [index, setIndex] = useState(0);
  const [form, setForm] = useState<ClinicalHistoryInput>(emptyHistory);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [showTests, setShowTests] = useState(false);
  const [showFullPrevious, setShowFullPrevious] = useState<number | null>(null);
  const [previousTests, setPreviousTests] = useState<Record<number, string[]>>({});
  const [detailsByHistory, setDetailsByHistory] = useState<Record<number, ClinicalDetails>>({});
  const [loadingDetailsId, setLoadingDetailsId] = useState<number | null>(null);
  const [downloadingDocument, setDownloadingDocument] = useState("");
  const [showFollowUp, setShowFollowUp] = useState(false);
  const [followUp, setFollowUp] = useState<FollowUpForm>(emptyFollowUp);
  const [savingFollowUp, setSavingFollowUp] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [followUpError, setFollowUpError] = useState("");

  const current = records[index];
  const currentDetails = current ? detailsByHistory[current.id] : undefined;
  const currentVitalSigns = vitalSignItems(currentDetails?.vitalSigns);
  const positionLabel = useMemo(
    () => (isNew || !records.length ? "Nueva consulta" : `Consulta ${index + 1} de ${records.length}`),
    [index, isNew, records.length],
  );

  async function loadTests(historyId: number) {
    const { data } = await api.get<RequestedTest[]>(`/clinical-history/${historyId}/requested-tests`);
    return data.map((item) => item.test_name);
  }

  async function loadClinicalDetails(historyId: number) {
    setLoadingDetailsId(historyId);
    try {
      const [{ data: diagnoses }, { data: prescriptions }, tests, { data: vitalSigns }] = await Promise.all([
        api.get<Diagnosis[]>(`/clinical-history/${historyId}/diagnoses`),
        api.get<Prescription[]>(`/clinical-history/${historyId}/prescriptions`),
        loadTests(historyId),
        api.get<VitalSigns | null>(`/clinical-history/${historyId}/vital-signs`),
      ]);
      const details = { diagnoses, prescriptions, tests, vitalSigns };
      setDetailsByHistory((currentDetails) => ({ ...currentDetails, [historyId]: details }));
      setPreviousTests((currentTests) => ({ ...currentTests, [historyId]: tests }));
      return details;
    } finally {
      setLoadingDetailsId((currentId) => currentId === historyId ? null : currentId);
    }
  }

  async function load() {
    try {
      const { data } = await api.get<ClinicalHistory[]>(`/clinical-history/patients/${patientId}`);
      setRecords(data);
      if (data.length) {
        const initialTests = data[0].requested_tests.map((item) => item.test_name);
        setIndex(0);
        setForm({ ...data[0], requested_tests: initialTests.join("\n") });
        setIsNew(false);
        setHasUnsavedChanges(false);
        setShowTests(Boolean(initialTests.length));
        setPreviousTests({ [data[0].id]: initialTests });
        try {
          const { tests } = await loadClinicalDetails(data[0].id);
          setForm({ ...data[0], requested_tests: tests.join("\n") });
        } catch (err: any) {
          setError(err?.response?.data?.detail || "La historia se cargó, pero no fue posible obtener diagnósticos y recetas.");
        }
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
    const initialTests = record.requested_tests.map((item) => item.test_name);
    setIndex(nextIndex);
    setForm({ ...record, requested_tests: initialTests.join("\n") });
    setIsNew(false);
    setHasUnsavedChanges(false);
    setShowTests(Boolean(initialTests.length));
    setMessage("");
    setError("");
    try {
      const { tests } = detailsByHistory[record.id] || await loadClinicalDetails(record.id);
      setForm({ ...record, requested_tests: tests.join("\n") });
      setShowTests(Boolean(tests.length));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "La consulta se cargó, pero no fue posible obtener diagnósticos y recetas.");
    }
  }

  async function openPreviousRecord(historyId: number) {
    if (showFullPrevious === historyId) {
      setShowFullPrevious(null);
      return;
    }
    try {
      if (!detailsByHistory[historyId]) await loadClinicalDetails(historyId);
      setShowFullPrevious(historyId);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible cargar el detalle de la consulta.");
    }
  }

  async function syncTests(historyId: number) {
    const { data } = await api.get<RequestedTest[]>(`/clinical-history/${historyId}/requested-tests`);
    for (const item of data) if (item.id) await api.delete(`/clinical-history/requested-tests/${item.id}`);
    const tests = (form.requested_tests || "").split("\n").map((value) => value.trim()).filter(Boolean);
    const savedTests: RequestedTest[] = [];
    for (const test_name of tests) {
      const { data: savedTest } = await api.post<RequestedTest>(`/clinical-history/${historyId}/requested-tests`, { test_name });
      savedTests.push(savedTest);
    }
    setPreviousTests((currentTests) => ({ ...currentTests, [historyId]: tests }));
    setDetailsByHistory((currentDetails) => ({
      ...currentDetails,
      [historyId]: {
        diagnoses: currentDetails[historyId]?.diagnoses || [],
        prescriptions: currentDetails[historyId]?.prescriptions || [],
        tests,
        vitalSigns: currentDetails[historyId]?.vitalSigns || null,
      },
    }));
    return savedTests;
  }

  async function save() {
    if (isNew || current?.status === "completed") return;
    setSaving(true); setMessage(""); setError("");
    try {
      const historyPayload = { ...form };
      delete (historyPayload as any).requested_tests;
      let saved: ClinicalHistory;
      if (current) {
        const { data } = await api.put<ClinicalHistory>(`/clinical-history/${current.id}`, historyPayload);
        saved = data;
      } else return;
      const savedTests = await syncTests(saved.id);
      saved = { ...saved, requested_tests: savedTests };
      const nextRecords = records.map((record) => record.id === saved.id ? saved : record)
        .sort((a, b) => b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id);
      setRecords(nextRecords);
      setIndex(nextRecords.findIndex((record) => record.id === saved.id));
      setForm({ ...saved, requested_tests: form.requested_tests || "" });
      setIsNew(false);
      setHasUnsavedChanges(false);
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

  async function downloadPdf(historyId: number, kind: "summary" | "prescription" | "tests") {
    const documentKey = `${historyId}:${kind}`;
    const endpoints = {
      summary: `/clinical-history/${historyId}/summary/pdf`,
      prescription: `/clinical-history/${historyId}/prescriptions/pdf`,
      tests: `/clinical-history/${historyId}/requested-tests/pdf`,
    };
    const filenames = {
      summary: `resumen-consulta-${historyId}.pdf`,
      prescription: `receta-${historyId}.pdf`,
      tests: `orden-estudios-${historyId}.pdf`,
    };
    setDownloadingDocument(documentKey);
    setError("");
    try {
      const response = await api.get<Blob>(endpoints[kind], { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = filenames[kind];
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible descargar el documento clínico.");
    } finally {
      setDownloadingDocument("");
    }
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
                  <div><label className="mb-1 block text-sm font-medium">Fecha de la consulta</label><input type="date" value={form.consultation_date} disabled={isNew || current?.status === "completed"} onChange={(event) => { setForm({ ...form, consultation_date: event.target.value }); setHasUnsavedChanges(true); }} className="rounded-lg border px-3 py-2 disabled:bg-slate-100" /><p className="mt-1 text-xs text-slate-500">{positionLabel}{current?.status === "completed" ? " · Finalizada" : ""}</p></div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void showRecord(index + 1)} disabled={isNew || index >= records.length - 1} className="rounded-lg border px-4 py-2 disabled:opacity-40">← Anterior</button>
                    <button type="button" onClick={() => void showRecord(index - 1)} disabled={isNew || index <= 0} className="rounded-lg border px-4 py-2 disabled:opacity-40">Siguiente →</button>
                    <button type="button" onClick={openFollowUp} disabled={isNew || !current} className="rounded-lg bg-amber-600 px-4 py-2 font-medium text-white disabled:opacity-40">⏰ Programar seguimiento</button>
                  </div>
                </div>
              </div>

              {isNew && <div className="rounded-lg border border-dashed bg-slate-50 p-5 text-sm text-slate-600">No hay consultas vinculadas a citas para este paciente. Las nuevas consultas deben iniciarse desde la Agenda.</div>}
              {!isNew && fields.map(([name, label]) => <label key={name} className="block"><span className="mb-1 block text-sm font-medium">{label}</span><textarea value={form[name] ?? ""} disabled={current?.status === "completed"} onChange={(event) => { setForm({ ...form, [name]: event.target.value }); setHasUnsavedChanges(true); }} rows={3} className="w-full rounded-lg border px-3 py-2 disabled:bg-slate-100" /></label>)}

              {!isNew && current && <div className="rounded-xl border border-teal-200 bg-teal-50/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-semibold text-teal-950">Contenido clínico vinculado</h4><p className="text-xs text-teal-700">Diagnósticos, receta y documentos de esta consulta.</p>{hasUnsavedChanges && <p className="mt-1 text-xs font-medium text-amber-700">Guarda los cambios antes de generar documentos.</p>}</div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void downloadPdf(current.id, "summary")} disabled={hasUnsavedChanges || Boolean(downloadingDocument)} className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">{downloadingDocument === `${current.id}:summary` ? "Generando..." : "Resumen PDF"}</button><button type="button" onClick={() => void downloadPdf(current.id, "prescription")} disabled={hasUnsavedChanges || !currentDetails?.prescriptions.length || Boolean(downloadingDocument)} className="rounded-lg border border-teal-300 bg-white px-3 py-2 text-sm font-medium text-teal-800 disabled:opacity-40">{downloadingDocument === `${current.id}:prescription` ? "Generando..." : "Receta PDF"}</button></div></div>
                {loadingDetailsId === current.id ? <p className="mt-4 text-sm text-slate-500">Cargando contenido clínico...</p> : <><div className="mt-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Signos vitales</p>{currentVitalSigns.length ? <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{currentVitalSigns.map(([label, value]) => <div key={label} className="rounded-lg border border-cyan-100 bg-white p-3 text-sm"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 font-semibold text-cyan-900">{value}</p></div>)}</div> : <p className="mt-2 text-sm text-slate-500">Sin signos vitales registrados.</p>}</div><div className="mt-4 grid gap-4 md:grid-cols-2"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Diagnósticos</p>{currentDetails?.diagnoses.length ? <div className="mt-2 space-y-2">{currentDetails.diagnoses.map((item) => <div key={item.id} className="rounded-lg border bg-white p-3 text-sm"><p className="font-medium">{item.description}{item.is_primary && <span className="ml-2 rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">Principal</span>}</p>{item.icd10_code && <p className="mt-1 text-xs text-slate-500">CIE-10: {item.icd10_code}</p>}</div>)}</div> : <p className="mt-2 text-sm text-slate-500">Sin diagnósticos registrados.</p>}</div><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Medicamentos recetados</p>{currentDetails?.prescriptions.length ? <div className="mt-2 space-y-2">{currentDetails.prescriptions.map((item) => <div key={item.id} className="rounded-lg border bg-white p-3 text-sm"><p className="font-medium">{item.medication}{item.presentation ? ` · ${item.presentation}` : ""}</p><p className="mt-1 text-xs text-slate-600">{[item.dose, item.route, item.frequency, item.duration].filter(Boolean).join(" · ") || "Pauta no especificada"}</p>{item.quantity && <p className="mt-1 text-xs text-slate-500">Cantidad: {item.quantity}</p>}{item.instructions && <p className="mt-1 text-xs text-slate-500">{item.instructions}</p>}</div>)}</div> : <p className="mt-2 text-sm text-slate-500">Sin medicamentos recetados.</p>}</div></div></>}
              </div>}

              {!isNew && <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="font-semibold text-indigo-900">Análisis y pruebas indicadas</h4><p className="text-xs text-indigo-700">Opcional y asociado a esta consulta.</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => setShowTests((value) => !value)} className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-800">{showTests ? "Ocultar" : "Agregar análisis / pruebas"}</button><button type="button" onClick={() => current && void downloadPdf(current.id, "tests")} disabled={hasUnsavedChanges || isNew || !current || !form.requested_tests?.trim() || Boolean(downloadingDocument)} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">{current && downloadingDocument === `${current.id}:tests` ? "Generando PDF..." : "Descargar orden PDF"}</button></div></div>
                {showTests && <label className="mt-4 block"><span className="mb-1 block text-sm font-medium">Un análisis o prueba por línea</span><textarea value={form.requested_tests ?? ""} disabled={current?.status === "completed"} onChange={(event) => { setForm({ ...form, requested_tests: event.target.value }); setHasUnsavedChanges(true); }} rows={7} placeholder={'Hemograma\nGlucosa en sangre\nPerfil lipídico\nRadiografía de tórax'} className="w-full rounded-lg border bg-white px-3 py-2 disabled:bg-slate-100" /></label>}
              </div>}

              {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
              {message && <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}
              <div className="flex justify-end gap-3 border-t pt-5"><button onClick={onClose} className="rounded-lg border px-5 py-2">Cerrar</button>{!isNew && current?.status !== "completed" && <button onClick={() => void save()} disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 text-white disabled:opacity-50">{saving ? "Guardando..." : "Guardar cambios"}</button>}</div>
            </section>

            <aside className="lg:sticky lg:top-20 lg:self-start">
              <div className="rounded-xl border bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3"><div><h4 className="font-semibold">Consultas anteriores</h4><p className="text-xs text-slate-500">Historial clínico reciente del paciente</p></div><span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600">{previousRecords.length}</span></div>
                {previousRecords.length === 0 ? <p className="mt-4 rounded-lg border border-dashed bg-white p-4 text-sm text-slate-500">No hay consultas anteriores para mostrar.</p> : <div className="mt-4 space-y-3">{previousRecords.map((record) => {
                  const details = detailsByHistory[record.id];
                  const tests = details?.tests || previousTests[record.id] || [];
                  const vitalItems = vitalSignItems(details?.vitalSigns);
                  const isExpanded = showFullPrevious === record.id;
                  const isLoading = loadingDetailsId === record.id;
                  return <article key={record.id} className="rounded-lg border bg-white p-3 shadow-sm">
                    <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{formatDate(record.consultation_date)}</p><p className="mt-1 font-medium text-slate-900">{historySummary(record)}</p>{record.appointment_id && <p className="mt-1 text-xs text-slate-400">Cita #{record.appointment_id}</p>}</div><button type="button" onClick={() => void openPreviousRecord(record.id)} disabled={isLoading} className="shrink-0 text-xs font-semibold text-indigo-700 hover:underline disabled:opacity-40">{isLoading ? "Cargando..." : isExpanded ? "Ocultar" : "Ver completa"}</button></div>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-slate-600">{record.chronic_conditions && <span className="rounded-full bg-slate-100 px-2 py-1">Condición crónica</span>}{record.allergies && <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-800">Alergias</span>}{vitalItems.length > 0 && <span className="rounded-full bg-cyan-50 px-2 py-1 text-cyan-800">Signos vitales</span>}{details?.diagnoses.length ? <span className="rounded-full bg-teal-50 px-2 py-1 text-teal-800">{details.diagnoses.length} diagnóstico{details.diagnoses.length === 1 ? "" : "s"}</span> : null}{details?.prescriptions.length ? <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-800">{details.prescriptions.length} medicamento{details.prescriptions.length === 1 ? "" : "s"}</span> : null}{tests.length > 0 && <span className="rounded-full bg-indigo-50 px-2 py-1 text-indigo-800">{tests.length} estudio{tests.length === 1 ? "" : "s"}</span>}</div>
                    {isExpanded && details && <div className="mt-3 space-y-3 border-t pt-3 text-xs text-slate-700">
                      {record.current_illness && <p><strong>Enfermedad actual:</strong> {record.current_illness}</p>}{record.personal_history && <p><strong>Antecedentes personales:</strong> {record.personal_history}</p>}{record.family_history && <p><strong>Antecedentes familiares:</strong> {record.family_history}</p>}{record.previous_surgeries && <p><strong>Cirugías:</strong> {record.previous_surgeries}</p>}{record.habits && <p><strong>Hábitos:</strong> {record.habits}</p>}{record.clinical_notes && <p><strong>Observaciones:</strong> {record.clinical_notes}</p>}
                      <div><p className="font-semibold">Signos vitales:</p>{vitalItems.length ? <ul className="mt-1 list-disc pl-4">{vitalItems.map(([label, value]) => <li key={label}>{label}: {value}</li>)}</ul> : <p className="mt-1 text-slate-500">Sin mediciones.</p>}</div>
                      <div><p className="font-semibold">Diagnósticos:</p>{details.diagnoses.length ? <ul className="mt-1 list-disc pl-4">{details.diagnoses.map((item) => <li key={item.id}>{item.description}{item.icd10_code ? ` · CIE-10 ${item.icd10_code}` : ""}{item.is_primary ? " · Principal" : ""}</li>)}</ul> : <p className="mt-1 text-slate-500">Sin diagnósticos.</p>}</div>
                      <div><p className="font-semibold">Receta:</p>{details.prescriptions.length ? <ul className="mt-1 list-disc pl-4">{details.prescriptions.map((item) => <li key={item.id}>{item.medication}{item.presentation ? ` · ${item.presentation}` : ""}{item.dose ? ` · ${item.dose}` : ""}</li>)}</ul> : <p className="mt-1 text-slate-500">Sin medicamentos.</p>}</div>
                      {tests.length > 0 && <div><p className="font-semibold">Estudios/análisis:</p><ul className="mt-1 list-disc pl-4">{tests.map((test) => <li key={test}>{test}</li>)}</ul></div>}
                      <div className="flex flex-wrap gap-2 pt-1"><button type="button" onClick={() => void downloadPdf(record.id, "summary")} disabled={Boolean(downloadingDocument)} className="rounded-md bg-teal-700 px-2.5 py-1.5 font-medium text-white disabled:opacity-40">{downloadingDocument === `${record.id}:summary` ? "Generando..." : "Resumen PDF"}</button><button type="button" onClick={() => void downloadPdf(record.id, "prescription")} disabled={!details.prescriptions.length || Boolean(downloadingDocument)} className="rounded-md border border-blue-200 px-2.5 py-1.5 font-medium text-blue-700 disabled:opacity-40">Receta PDF</button><button type="button" onClick={() => void downloadPdf(record.id, "tests")} disabled={!tests.length || Boolean(downloadingDocument)} className="rounded-md border border-indigo-200 px-2.5 py-1.5 font-medium text-indigo-700 disabled:opacity-40">Orden PDF</button></div>
                    </div>}
                  </article>;
                })}</div>}
              </div>
            </aside>
          </div>
        )}

        {showFollowUp && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><div className="flex items-start justify-between"><div><h3 className="text-lg font-bold">Programar seguimiento</h3><p className="text-sm text-slate-500">{patientName} · consulta del {current ? formatDate(current.consultation_date) : ""}</p></div><button type="button" onClick={() => setShowFollowUp(false)} className="text-2xl text-slate-400">×</button></div><div className="mt-5 space-y-4"><label className="block"><span className="mb-1 block text-sm font-medium">Fecha y hora</span><input type="datetime-local" value={followUp.due_at} onChange={(event) => setFollowUp({ ...followUp, due_at: event.target.value })} className="w-full rounded-lg border px-3 py-2" /></label><label className="block"><span className="mb-1 block text-sm font-medium">Motivo</span><input value={followUp.reason} onChange={(event) => setFollowUp({ ...followUp, reason: event.target.value })} placeholder="Revisar resultados de laboratorio" className="w-full rounded-lg border px-3 py-2" /></label><label className="block"><span className="mb-1 block text-sm font-medium">Prioridad</span><select value={followUp.priority} onChange={(event) => setFollowUp({ ...followUp, priority: event.target.value as FollowUpForm["priority"] })} className="w-full rounded-lg border px-3 py-2"><option value="low">Baja</option><option value="normal">Normal</option><option value="high">Alta</option><option value="urgent">Urgente</option></select></label><label className="block"><span className="mb-1 block text-sm font-medium">Notas</span><textarea value={followUp.notes} onChange={(event) => setFollowUp({ ...followUp, notes: event.target.value })} rows={3} placeholder="Indicaciones para el seguimiento" className="w-full rounded-lg border px-3 py-2" /></label>{followUpError && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{followUpError}</div>}<div className="flex justify-end gap-3 border-t pt-4"><button type="button" onClick={() => setShowFollowUp(false)} className="rounded-lg border px-4 py-2">Cancelar</button><button type="button" onClick={() => void createFollowUp()} disabled={savingFollowUp} className="rounded-lg bg-amber-600 px-5 py-2 font-medium text-white disabled:opacity-50">{savingFollowUp ? "Programando..." : "Programar seguimiento"}</button></div></div></div></div>}
      </div>
    </div>
  );
}
