import { useEffect, useMemo, useState } from "react";

import { api } from "../../services/api";
import type { LaboratoryOrder, LaboratoryTest, MedicalStudy, StudyOrder } from "../../types/clinicalOrder";

type Props = {
  historyId: number;
  specialtyId: number;
  completed: boolean;
  allowAdditional?: boolean;
  onOrdersChanged?: () => void | Promise<void>;
};

type StudyDetails = { region_description: string; contrast: "yes" | "no" | "not_applicable"; clinical_notes: string };

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("es-DO");
}

export default function ClinicalOrdersSection({ historyId, specialtyId, completed, allowAdditional = false, onOrdersChanged }: Props) {
  const [tests, setTests] = useState<LaboratoryTest[]>([]);
  const [studies, setStudies] = useState<MedicalStudy[]>([]);
  const [laboratoryOrders, setLaboratoryOrders] = useState<LaboratoryOrder[]>([]);
  const [studyOrders, setStudyOrders] = useState<StudyOrder[]>([]);
  const [testQuery, setTestQuery] = useState("");
  const [studyQuery, setStudyQuery] = useState("");
  const [selectedTests, setSelectedTests] = useState<number[]>([]);
  const [selectedStudies, setSelectedStudies] = useState<number[]>([]);
  const [studyDetails, setStudyDetails] = useState<Record<number, StudyDetails>>({});
  const [laboratoryNotes, setLaboratoryNotes] = useState("");
  const [studyNotes, setStudyNotes] = useState("");
  const [editingLaboratoryId, setEditingLaboratoryId] = useState<number | null>(null);
  const [editingStudyId, setEditingStudyId] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [additionalKind, setAdditionalKind] = useState<"laboratory" | "study" | null>(null);

  async function load() {
    try {
      const [testResponse, studyResponse, laboratoryResponse, ordersResponse] = await Promise.all([
        api.get<LaboratoryTest[]>("/laboratory-tests"),
        api.get<MedicalStudy[]>("/clinical-catalog/studies", { params: { specialty_id: specialtyId } }),
        api.get<LaboratoryOrder[]>(`/clinical-history/${historyId}/laboratory-orders`),
        api.get<StudyOrder[]>(`/clinical-history/${historyId}/study-orders`),
      ]);
      setTests(testResponse.data);
      setStudies(studyResponse.data);
      setLaboratoryOrders(laboratoryResponse.data);
      setStudyOrders(ordersResponse.data);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible cargar las órdenes clínicas.");
    }
  }

  useEffect(() => { void load(); }, [historyId, specialtyId]);

  const groupedTests = useMemo(() => {
    const query = testQuery.trim().toLocaleLowerCase();
    return tests.filter((item) => !query || `${item.name} ${item.category}`.toLocaleLowerCase().includes(query))
      .reduce<Record<string, LaboratoryTest[]>>((groups, item) => {
        (groups[item.category] ||= []).push(item);
        return groups;
      }, {});
  }, [tests, testQuery]);

  const filteredStudies = useMemo(() => {
    const query = studyQuery.trim().toLocaleLowerCase();
    return studies.filter((item) => !query || `${item.name} ${item.category}`.toLocaleLowerCase().includes(query));
  }, [studies, studyQuery]);

  function toggleTest(id: number) {
    setSelectedTests((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  function toggleStudy(id: number) {
    setSelectedStudies((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setStudyDetails((current) => ({
      ...current,
      [id]: current[id] || { region_description: "", contrast: "not_applicable", clinical_notes: "" },
    }));
  }

  async function saveLaboratoryOrder() {
    if (!selectedTests.length) return setError("Seleccione al menos una prueba de laboratorio.");
    setBusy("laboratory-save"); setError(""); setMessage("");
    const payload = { items: selectedTests.map((laboratory_test_id) => ({ laboratory_test_id })), notes: laboratoryNotes.trim() || null };
    try {
      if (editingLaboratoryId) await api.put(`/clinical-history/${historyId}/laboratory-orders/${editingLaboratoryId}`, payload);
      else await api.post(`/clinical-history/${historyId}/laboratory-orders${completed ? "/additional" : ""}`, payload);
      setSelectedTests([]); setLaboratoryNotes(""); setEditingLaboratoryId(null);
      setAdditionalKind(null);
      await load();
      await onOrdersChanged?.();
      setMessage("Orden de laboratorio guardada correctamente.");
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible guardar la orden de laboratorio.");
    } finally { setBusy(""); }
  }

  function editLaboratoryOrder(order: LaboratoryOrder) {
    setEditingLaboratoryId(order.id);
    setSelectedTests(order.items.map((item) => item.laboratory_test_id));
    setLaboratoryNotes(order.notes || "");
  }

  async function saveStudyOrder() {
    if (!selectedStudies.length) return setError("Seleccione al menos un estudio o procedimiento.");
    setBusy("study-save"); setError(""); setMessage("");
    const payload = {
      items: selectedStudies.map((medical_study_id) => ({
        medical_study_id,
        region_description: studyDetails[medical_study_id]?.region_description.trim() || null,
        contrast: studyDetails[medical_study_id]?.contrast || "not_applicable",
        clinical_notes: studyDetails[medical_study_id]?.clinical_notes.trim() || null,
      })),
      notes: studyNotes.trim() || null,
    };
    try {
      if (editingStudyId) await api.put(`/clinical-history/${historyId}/study-orders/${editingStudyId}`, payload);
      else await api.post(`/clinical-history/${historyId}/study-orders${completed ? "/additional" : ""}`, payload);
      setSelectedStudies([]); setStudyDetails({}); setStudyNotes(""); setEditingStudyId(null);
      setAdditionalKind(null);
      await load();
      await onOrdersChanged?.();
      setMessage("Orden de estudios guardada correctamente.");
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible guardar la orden de estudios.");
    } finally { setBusy(""); }
  }

  function editStudyOrder(order: StudyOrder) {
    setEditingStudyId(order.id);
    setSelectedStudies(order.items.map((item) => item.medical_study_id));
    setStudyDetails(Object.fromEntries(order.items.map((item) => [item.medical_study_id, {
      region_description: item.region_description || "", contrast: item.contrast, clinical_notes: item.clinical_notes || "",
    }])));
    setStudyNotes(order.notes || "");
  }

  async function download(kind: "laboratory" | "study", id: number) {
    setBusy(`${kind}-pdf-${id}`); setError("");
    try {
      const response = await api.get<Blob>(`/${kind === "laboratory" ? "laboratory-orders" : "study-orders"}/${id}/pdf`, { responseType: "blob" });
      downloadBlob(response.data, `${kind === "laboratory" ? "orden-laboratorio" : "orden-estudios"}-${id}.pdf`);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible generar el documento.");
    } finally { setBusy(""); }
  }

  const showLaboratoryForm = !completed || (allowAdditional && additionalKind === "laboratory");
  const showStudyForm = !completed || (allowAdditional && additionalKind === "study");

  return <div className="space-y-6">
    {completed && allowAdditional && <div className="rounded-xl border border-violet-200 bg-violet-50 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold text-violet-950">Nueva orden adicional</h3><p className="text-sm text-violet-800">Crea una orden nueva sin reabrir ni modificar la consulta finalizada.</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => setAdditionalKind((value) => value === "laboratory" ? null : "laboratory")} className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white">Laboratorio</button><button type="button" onClick={() => setAdditionalKind((value) => value === "study" ? null : "study")} className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-medium text-white">Estudio / procedimiento</button></div></div></div>}
    <section className="rounded-xl border border-cyan-200 bg-cyan-50/40 p-5">
      <div><h3 className="text-lg font-semibold text-cyan-950">Laboratorios</h3><p className="text-sm text-cyan-800">Seleccione pruebas estructuradas y genere una orden persistente.</p></div>
      {showLaboratoryForm && <div className="mt-4 space-y-4">
        <input value={testQuery} onChange={(event) => setTestQuery(event.target.value)} placeholder="Buscar prueba o categoría..." className="w-full rounded-lg border bg-white px-3 py-2" />
        <div className="max-h-72 space-y-4 overflow-y-auto rounded-lg border bg-white p-4">{Object.entries(groupedTests).map(([category, items]) => <div key={category}><p className="text-xs font-bold uppercase tracking-wide text-cyan-800">{category}</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{items.map((item) => <label key={item.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedTests.includes(item.id)} onChange={() => toggleTest(item.id)} />{item.name}</label>)}</div></div>)}</div>
        <textarea value={laboratoryNotes} onChange={(event) => setLaboratoryNotes(event.target.value)} rows={2} placeholder="Observaciones generales de la orden (opcional)" className="w-full rounded-lg border bg-white px-3 py-2" />
        <div className="flex justify-end gap-2">{editingLaboratoryId && <button type="button" onClick={() => { setEditingLaboratoryId(null); setSelectedTests([]); setLaboratoryNotes(""); }} className="rounded-lg border px-4 py-2">Cancelar edición</button>}<button type="button" onClick={() => void saveLaboratoryOrder()} disabled={busy === "laboratory-save" || !selectedTests.length} className="rounded-lg bg-cyan-700 px-4 py-2 font-medium text-white disabled:opacity-40">{busy === "laboratory-save" ? "Guardando..." : editingLaboratoryId ? "Actualizar orden" : "Guardar orden"}</button></div>
      </div>}
      <div className="mt-5 space-y-3">{laboratoryOrders.map((order) => <article key={order.id} className="rounded-lg border bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-semibold">Orden de laboratorio #{order.id}{order.is_additional && <span className="ml-2 rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800">Orden adicional</span>}</p><p className="text-xs text-slate-500">{formatDateTime(order.created_at)} · {order.doctor_name}</p></div><div className="flex gap-2">{!completed && <button type="button" onClick={() => editLaboratoryOrder(order)} className="text-sm font-medium text-cyan-700">Editar</button>}<button type="button" onClick={() => void download("laboratory", order.id)} disabled={Boolean(busy)} className="rounded-md bg-cyan-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">Descargar PDF</button></div></div><ul className="mt-3 list-disc pl-5 text-sm">{order.items.map((item) => <li key={item.id}>{item.test_name}{item.custom_note ? ` — ${item.custom_note}` : ""}</li>)}</ul>{order.notes && <p className="mt-2 text-sm"><strong>Observaciones:</strong> {order.notes}</p>}</article>)}{!laboratoryOrders.length && <p className="text-sm text-slate-500">Sin órdenes de laboratorio.</p>}</div>
    </section>

    <section className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-5">
      <div><h3 className="text-lg font-semibold text-indigo-950">Estudios y procedimientos</h3><p className="text-sm text-indigo-800">Indique modalidad, región, contraste y observaciones clínicas.</p></div>
      {showStudyForm && <div className="mt-4 space-y-4">
        <input value={studyQuery} onChange={(event) => setStudyQuery(event.target.value)} placeholder="Buscar estudio o modalidad..." className="w-full rounded-lg border bg-white px-3 py-2" />
        <div className="grid gap-2 rounded-lg border bg-white p-4 sm:grid-cols-2">{filteredStudies.map((item) => <label key={item.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedStudies.includes(item.id)} onChange={() => toggleStudy(item.id)} />{item.name}</label>)}</div>
        {selectedStudies.map((id) => { const study = studies.find((item) => item.id === id); const detail = studyDetails[id] || { region_description: "", contrast: "not_applicable", clinical_notes: "" }; return <div key={id} className="rounded-lg border bg-white p-3"><p className="font-medium">{study?.name}</p><div className="mt-2 grid gap-2 sm:grid-cols-2"><input value={detail.region_description} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, region_description: event.target.value } }))} placeholder="Región o descripción" className="rounded-lg border px-3 py-2" /><select value={detail.contrast} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, contrast: event.target.value as StudyDetails["contrast"] } }))} className="rounded-lg border px-3 py-2"><option value="not_applicable">Contraste: no aplica</option><option value="no">Sin contraste</option><option value="yes">Con contraste</option></select></div><textarea value={detail.clinical_notes} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, clinical_notes: event.target.value } }))} rows={2} placeholder="Observaciones clínicas (opcional)" className="mt-2 w-full rounded-lg border px-3 py-2" /></div>; })}
        <textarea value={studyNotes} onChange={(event) => setStudyNotes(event.target.value)} rows={2} placeholder="Observaciones generales de la orden (opcional)" className="w-full rounded-lg border bg-white px-3 py-2" />
        <div className="flex justify-end gap-2">{editingStudyId && <button type="button" onClick={() => { setEditingStudyId(null); setSelectedStudies([]); setStudyDetails({}); setStudyNotes(""); }} className="rounded-lg border px-4 py-2">Cancelar edición</button>}<button type="button" onClick={() => void saveStudyOrder()} disabled={busy === "study-save" || !selectedStudies.length} className="rounded-lg bg-indigo-700 px-4 py-2 font-medium text-white disabled:opacity-40">{busy === "study-save" ? "Guardando..." : editingStudyId ? "Actualizar orden" : "Guardar orden"}</button></div>
      </div>}
      <div className="mt-5 space-y-3">{studyOrders.map((order) => <article key={order.id} className="rounded-lg border bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-semibold">Orden de estudios #{order.id}{order.is_additional && <span className="ml-2 rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800">Orden adicional</span>}</p><p className="text-xs text-slate-500">{formatDateTime(order.created_at)} · {order.doctor_name}</p></div><div className="flex gap-2">{!completed && <button type="button" onClick={() => editStudyOrder(order)} className="text-sm font-medium text-indigo-700">Editar</button>}<button type="button" onClick={() => void download("study", order.id)} disabled={Boolean(busy)} className="rounded-md bg-indigo-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">Descargar PDF</button></div></div><ul className="mt-3 list-disc pl-5 text-sm">{order.items.map((item) => <li key={item.id}>{item.study_name}{item.region_description ? ` · ${item.region_description}` : ""}{item.contrast !== "not_applicable" ? ` · Contraste: ${item.contrast === "yes" ? "sí" : "no"}` : ""}{item.clinical_notes ? ` · ${item.clinical_notes}` : ""}</li>)}</ul>{order.notes && <p className="mt-2 text-sm"><strong>Observaciones:</strong> {order.notes}</p>}</article>)}{!studyOrders.length && <p className="text-sm text-slate-500">Sin órdenes de estudios.</p>}</div>
    </section>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {message && <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}
  </div>;
}
