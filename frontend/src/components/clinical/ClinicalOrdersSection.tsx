import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../services/api";
import type { LaboratoryOrder, LaboratoryTest, MedicalStudy, StudyOrder } from "../../types/clinicalOrder";

type Props = { historyId: number; specialtyId: number | null; completed: boolean; allowAdditional?: boolean; onOrdersChanged?: () => void | Promise<void> };
type StudyDetails = { region_description: string; contrast: "yes" | "no" | "not_applicable"; clinical_notes: string };
type Composer = "chooser" | "laboratory" | "study" | null;

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}

function formatDateTime(value: string) { return new Date(value).toLocaleString("es-DO"); }
function preview(items: Array<{ test_name?: string; study_name?: string }>) {
  const names = items.map((item) => item.test_name || item.study_name || "");
  return `${names.slice(0, 3).join(" · ")}${names.length > 3 ? ` · +${names.length - 3}` : ""}`;
}

export default function ClinicalOrdersSection({ historyId, specialtyId, completed, allowAdditional = false, onOrdersChanged }: Props) {
  const [tests, setTests] = useState<LaboratoryTest[]>([]);
  const [studies, setStudies] = useState<MedicalStudy[]>([]);
  const [laboratoryOrders, setLaboratoryOrders] = useState<LaboratoryOrder[]>([]);
  const [studyOrders, setStudyOrders] = useState<StudyOrder[]>([]);
  const [testQuery, setTestQuery] = useState(""); const [studyQuery, setStudyQuery] = useState("");
  const [selectedTests, setSelectedTests] = useState<number[]>([]); const [selectedStudies, setSelectedStudies] = useState<number[]>([]);
  const [studyDetails, setStudyDetails] = useState<Record<number, StudyDetails>>({});
  const [laboratoryNotes, setLaboratoryNotes] = useState(""); const [studyNotes, setStudyNotes] = useState("");
  const [editingLaboratoryId, setEditingLaboratoryId] = useState<number | null>(null); const [editingStudyId, setEditingStudyId] = useState<number | null>(null);
  const [composer, setComposer] = useState<Composer>(null); const [expanded, setExpanded] = useState<string[]>([]); const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const generationRef = useRef(0);
  const isCurrent = (generation: number) => generation === generationRef.current;
  const creationAllowed = !completed || allowAdditional;
  const totalOrders = laboratoryOrders.length + studyOrders.length;

  function resetEditor() {
    setTestQuery(""); setStudyQuery(""); setSelectedTests([]); setSelectedStudies([]); setStudyDetails({}); setExpandedCategories([]);
    setLaboratoryNotes(""); setStudyNotes(""); setEditingLaboratoryId(null); setEditingStudyId(null); setComposer(null);
  }

  async function load(generation = generationRef.current) {
    try {
      const [testResponse, studyResponse, laboratoryResponse, studyOrderResponse] = await Promise.all([
        api.get<LaboratoryTest[]>("/laboratory-tests"),
        api.get<MedicalStudy[]>("/clinical-catalog/studies", { params: { include_all: true, ...(specialtyId ? { specialty_id: specialtyId } : {}) } }),
        api.get<LaboratoryOrder[]>(`/clinical-history/${historyId}/laboratory-orders`),
        api.get<StudyOrder[]>(`/clinical-history/${historyId}/study-orders`),
      ]);
      if (!isCurrent(generation)) return;
      setTests(testResponse.data); setStudies(studyResponse.data); setLaboratoryOrders(laboratoryResponse.data); setStudyOrders(studyOrderResponse.data);
    } catch (reason: any) { if (isCurrent(generation)) setError(reason?.response?.data?.detail || "No fue posible cargar las órdenes clínicas."); }
  }

  useEffect(() => {
    const generation = ++generationRef.current;
    resetEditor(); setExpanded([]); setBusy(""); setError(""); setMessage("");
    void load(generation);
    return () => { if (generationRef.current === generation) generationRef.current += 1; };
  }, [historyId, specialtyId]);

  const groupedTests = useMemo(() => {
    const query = testQuery.trim().toLocaleLowerCase();
    return tests.filter((item) => !query || `${item.name} ${item.category}`.toLocaleLowerCase().includes(query)).reduce<Record<string, LaboratoryTest[]>>((groups, item) => { (groups[item.category] ||= []).push(item); return groups; }, {});
  }, [tests, testQuery]);
  const selectedTestItems = useMemo(() => selectedTests.map((id) => tests.find((item) => item.id === id)).filter((item): item is LaboratoryTest => Boolean(item)), [selectedTests, tests]);
  const searchingTests = Boolean(testQuery.trim());
  const filteredStudies = useMemo(() => {
    const query = studyQuery.trim().toLocaleLowerCase();
    return studies.filter((item) => !query || `${item.name} ${item.category}`.toLocaleLowerCase().includes(query));
  }, [studies, studyQuery]);

  function openChooser() { resetEditor(); setError(""); setMessage(""); setComposer("chooser"); }
  function cancelComposer() { resetEditor(); setError(""); setMessage(""); }
  function choose(type: "laboratory" | "study") { setError(""); setMessage(""); setComposer(type); }
  function toggleTest(id: number) { setSelectedTests((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  function toggleCategory(category: string) { setExpandedCategories((current) => current.includes(category) ? current.filter((item) => item !== category) : [...current, category]); }
  function toggleStudy(id: number) {
    setSelectedStudies((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setStudyDetails((current) => ({ ...current, [id]: current[id] || { region_description: "", contrast: "not_applicable", clinical_notes: "" } }));
  }

  async function saveLaboratoryOrder() {
    if (!selectedTests.length) return setError("Seleccione al menos una prueba de laboratorio.");
    const generation = generationRef.current;
    const payload = { items: selectedTests.map((laboratory_test_id) => ({ laboratory_test_id })), notes: laboratoryNotes.trim() || null };
    setBusy("laboratory-save"); setError(""); setMessage("");
    try {
      if (editingLaboratoryId) await api.put(`/clinical-history/${historyId}/laboratory-orders/${editingLaboratoryId}`, payload);
      else await api.post(`/clinical-history/${historyId}/laboratory-orders${completed ? "/additional" : ""}`, payload);
      if (!isCurrent(generation)) return;
      resetEditor(); await load(generation); if (!isCurrent(generation)) return;
      await onOrdersChanged?.(); if (!isCurrent(generation)) return;
      setMessage("Orden de laboratorio guardada correctamente.");
    } catch (reason: any) { if (isCurrent(generation)) setError(reason?.response?.data?.detail || "No fue posible guardar la orden de laboratorio.");
    } finally { if (isCurrent(generation)) setBusy(""); }
  }

  function editLaboratoryOrder(order: LaboratoryOrder) {
    setError(""); setMessage(""); setComposer("laboratory"); setEditingStudyId(null); setEditingLaboratoryId(order.id); setExpandedCategories([]);
    setSelectedTests(order.items.map((item) => item.laboratory_test_id)); setLaboratoryNotes(order.notes || "");
    setStudyQuery(""); setSelectedStudies([]); setStudyDetails({}); setStudyNotes("");
  }

  async function saveStudyOrder() {
    if (!selectedStudies.length) return setError("Seleccione al menos un estudio o procedimiento.");
    const generation = generationRef.current;
    const payload = { items: selectedStudies.map((medical_study_id) => ({ medical_study_id, region_description: studyDetails[medical_study_id]?.region_description.trim() || null, contrast: studyDetails[medical_study_id]?.contrast || "not_applicable", clinical_notes: studyDetails[medical_study_id]?.clinical_notes.trim() || null })), notes: studyNotes.trim() || null };
    setBusy("study-save"); setError(""); setMessage("");
    try {
      if (editingStudyId) await api.put(`/clinical-history/${historyId}/study-orders/${editingStudyId}`, payload);
      else await api.post(`/clinical-history/${historyId}/study-orders${completed ? "/additional" : ""}`, payload);
      if (!isCurrent(generation)) return;
      resetEditor(); await load(generation); if (!isCurrent(generation)) return;
      await onOrdersChanged?.(); if (!isCurrent(generation)) return;
      setMessage("Orden de estudios guardada correctamente.");
    } catch (reason: any) { if (isCurrent(generation)) setError(reason?.response?.data?.detail || "No fue posible guardar la orden de estudios.");
    } finally { if (isCurrent(generation)) setBusy(""); }
  }

  function editStudyOrder(order: StudyOrder) {
    setError(""); setMessage(""); setComposer("study"); setEditingLaboratoryId(null); setEditingStudyId(order.id);
    setSelectedStudies(order.items.map((item) => item.medical_study_id)); setStudyDetails(Object.fromEntries(order.items.map((item) => [item.medical_study_id, { region_description: item.region_description || "", contrast: item.contrast, clinical_notes: item.clinical_notes || "" }]))); setStudyNotes(order.notes || "");
    setTestQuery(""); setSelectedTests([]); setExpandedCategories([]); setLaboratoryNotes("");
  }

  async function download(kind: "laboratory" | "study", id: number) {
    const generation = generationRef.current;
    setBusy(`${kind}-pdf-${id}`); setError("");
    try {
      const response = await api.get<Blob>(`/${kind === "laboratory" ? "laboratory-orders" : "study-orders"}/${id}/pdf`, { responseType: "blob" });
      if (!isCurrent(generation)) return;
      downloadBlob(response.data, `${kind === "laboratory" ? "orden-laboratorio" : "orden-estudios"}-${id}.pdf`);
    } catch (reason: any) { if (isCurrent(generation)) setError(reason?.response?.data?.detail || "No fue posible generar el documento.");
    } finally { if (isCurrent(generation)) setBusy(""); }
  }

  function toggleDetails(key: string) { setExpanded((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]); }

  return <section className="rounded-xl border bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">Órdenes clínicas</h3><p className="text-sm text-slate-500">Laboratorios, estudios y procedimientos estructurados.</p></div><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800">{totalOrders} orden{totalOrders === 1 ? "" : "es"}</span>{creationAllowed && <button type="button" onClick={openChooser} disabled={Boolean(busy)} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{completed ? "+ Nueva orden adicional" : "+ Nueva orden"}</button>}</div></div>

    {composer === "chooser" && <div className="mt-5 rounded-xl border border-teal-200 bg-teal-50 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-semibold text-teal-950">¿Qué desea solicitar?</h4><p className="text-sm text-teal-800">Elija el tipo de orden para abrir su editor.</p></div><button type="button" onClick={cancelComposer} className="rounded-lg border border-teal-300 bg-white px-3 py-2 text-sm font-medium text-teal-800">Cancelar</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><button type="button" onClick={() => choose("laboratory")} className="rounded-lg border border-cyan-200 bg-white p-4 text-left text-sm font-medium text-cyan-900">Laboratorio<span className="mt-1 block font-normal text-cyan-800">Seleccione pruebas del catálogo activo.</span></button><button type="button" onClick={() => choose("study")} className="rounded-lg border border-indigo-200 bg-white p-4 text-left text-sm font-medium text-indigo-900">Estudio / procedimiento<span className="mt-1 block font-normal text-indigo-800">Seleccione uno o más estudios estructurados.</span></button></div></div>}

    {composer === "laboratory" && <div data-clinical-orders-editor="laboratory" className="mt-5 rounded-xl border border-cyan-200 bg-cyan-50/50 p-4 pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-4"><div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"><div className="min-w-0"><h4 className="font-semibold text-cyan-950">{editingLaboratoryId ? "Editar orden de laboratorio" : completed ? "Nueva orden adicional de laboratorio" : "Nueva orden de laboratorio"}</h4><p aria-live="polite" className="text-sm text-cyan-800">{selectedTests.length} prueba{selectedTests.length === 1 ? "" : "s"} seleccionada{selectedTests.length === 1 ? "" : "s"}.</p></div><button type="button" onClick={cancelComposer} className="justify-self-start rounded-lg border border-cyan-300 bg-white px-3 py-2 text-sm font-medium text-cyan-800 sm:justify-self-end">Cancelar</button></div><div className="mt-4 space-y-4">{selectedTestItems.length > 0 && <div aria-label="Pruebas de laboratorio seleccionadas" className="flex flex-wrap items-center gap-2 rounded-lg border border-cyan-100 bg-white/80 p-2"><span className="text-xs font-medium text-cyan-900">Seleccionadas:</span>{selectedTestItems.map((item) => <button key={item.id} type="button" onClick={() => toggleTest(item.id)} aria-label={"Quitar " + item.name} className="max-w-full rounded-full border border-cyan-200 bg-cyan-50 px-2 py-1 text-left text-xs font-medium text-cyan-900">{item.name} <span aria-hidden="true">×</span></button>)}</div>}<label className="block text-sm font-medium text-cyan-950">Buscar pruebas<input aria-label="Buscar pruebas de laboratorio" value={testQuery} onChange={(event) => setTestQuery(event.target.value)} placeholder="Nombre o categoría" className="mt-1 w-full rounded-lg border bg-white px-3 py-2" /></label><div className="space-y-2 rounded-lg border bg-white p-3">{Object.entries(groupedTests).map(([category, items], index) => { const categoryOpen = searchingTests || expandedCategories.includes(category); const selectedCount = items.filter((item) => selectedTests.includes(item.id)).length; const categoryPanelId = "laboratory-category-" + index; return <section key={category} className="overflow-hidden rounded-lg border border-cyan-100"><button type="button" aria-expanded={categoryOpen} aria-controls={categoryPanelId} onClick={() => toggleCategory(category)} className="flex w-full items-center justify-between gap-3 bg-cyan-50 px-3 py-2 text-left text-xs font-bold uppercase tracking-wide text-cyan-900"><span className="min-w-0 break-words">{category}</span><span className="flex shrink-0 items-center gap-2 normal-case tracking-normal text-cyan-700">{selectedCount > 0 && <span aria-label={selectedCount + " pruebas seleccionadas en " + category} className="rounded-full bg-cyan-200 px-1.5 py-0.5 text-xs font-semibold text-cyan-900">{selectedCount}</span>}<span>{items.length} prueba{items.length === 1 ? "" : "s"} <span aria-hidden="true">{categoryOpen ? "−" : "+"}</span></span></span></button>{categoryOpen && <div id={categoryPanelId} className="grid gap-2 p-3 sm:grid-cols-2">{items.map((item) => <label key={item.id} className="flex min-w-0 items-center gap-2 text-sm"><input type="checkbox" checked={selectedTests.includes(item.id)} onChange={() => toggleTest(item.id)} /><span className="break-words">{item.name}</span></label>)}</div>}</section>; })}{!Object.keys(groupedTests).length && <p className="p-2 text-sm text-slate-500">No hay pruebas que coincidan con la búsqueda.</p>}</div><label className="block text-sm font-medium text-cyan-950">Observaciones generales<input aria-label="Observaciones generales de laboratorio" value={laboratoryNotes} onChange={(event) => setLaboratoryNotes(event.target.value)} placeholder="Opcional" className="mt-1 w-full rounded-lg border bg-white px-3 py-2" /></label><div className="flex flex-wrap justify-end"><button type="button" onClick={() => void saveLaboratoryOrder()} disabled={busy === "laboratory-save" || !selectedTests.length} className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{busy === "laboratory-save" ? "Guardando..." : editingLaboratoryId ? "Actualizar orden" : "Guardar orden"}</button></div></div></div>}

    {composer === "study" && <div data-clinical-orders-editor="study" className="mt-5 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-4"><div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"><div className="min-w-0"><h4 className="font-semibold text-indigo-950">{editingStudyId ? "Editar orden de estudios" : completed ? "Nueva orden adicional de estudios" : "Nueva orden de estudios"}</h4><p aria-live="polite" className="text-sm text-indigo-800">{selectedStudies.length} estudio{selectedStudies.length === 1 ? "" : "s"} seleccionado{selectedStudies.length === 1 ? "" : "s"}.</p></div><button type="button" onClick={cancelComposer} className="justify-self-start rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-800 sm:justify-self-end">Cancelar</button></div><div className="mt-4 space-y-4"><label className="block text-sm font-medium text-indigo-950">Buscar estudios o procedimientos<input aria-label="Buscar estudios o procedimientos" value={studyQuery} onChange={(event) => setStudyQuery(event.target.value)} placeholder="Nombre o modalidad" className="mt-1 w-full rounded-lg border bg-white px-3 py-2" /></label><div className="grid max-h-72 gap-2 overflow-y-auto rounded-lg border bg-white p-4 sm:grid-cols-2">{filteredStudies.map((item) => <label key={item.id} className="flex min-w-0 items-center gap-2 text-sm"><input type="checkbox" checked={selectedStudies.includes(item.id)} onChange={() => toggleStudy(item.id)} /><span className="min-w-0 break-words">{item.name}{specialtyId && item.recommended_specialty_ids.includes(specialtyId) ? <span className="ml-1.5 text-[10px] font-medium text-indigo-500">Recomendado</span> : null}</span></label>)}</div>{selectedStudies.length > 0 && <div className="space-y-3"><div><h5 className="text-sm font-semibold text-indigo-950">Detalles por estudio seleccionado</h5><p className="text-xs text-indigo-700">Revise los datos aplicables de cada estudio antes de guardar.</p></div>{selectedStudies.map((id) => { const study = studies.find((item) => item.id === id); const detail = studyDetails[id] || { region_description: "", contrast: "not_applicable", clinical_notes: "" }; return <div key={id} className="rounded-lg border bg-white p-3"><p className="break-words font-medium">{study?.name}</p><div className="mt-2 grid gap-2 sm:grid-cols-2"><label className="text-sm">Región o descripción<input aria-label={"Región o descripción para " + (study?.name || id)} value={detail.region_description} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, region_description: event.target.value } }))} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><label className="text-sm">Contraste<select aria-label={"Contraste para " + (study?.name || id)} value={detail.contrast} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, contrast: event.target.value as StudyDetails["contrast"] } }))} className="mt-1 w-full rounded-lg border px-3 py-2"><option value="not_applicable">No aplica</option><option value="no">Sin contraste</option><option value="yes">Con contraste</option></select></label></div><label className="mt-2 block text-sm">Observaciones clínicas<textarea aria-label={"Observaciones clínicas para " + (study?.name || id)} value={detail.clinical_notes} onChange={(event) => setStudyDetails((current) => ({ ...current, [id]: { ...detail, clinical_notes: event.target.value } }))} rows={2} className="mt-1 w-full rounded-lg border px-3 py-2" /></label></div>; })}</div>}<label className="block text-sm font-medium text-indigo-950">Observaciones generales<input aria-label="Observaciones generales de estudios" value={studyNotes} onChange={(event) => setStudyNotes(event.target.value)} placeholder="Opcional" className="mt-1 w-full rounded-lg border bg-white px-3 py-2" /></label><div className="flex flex-wrap justify-end"><button type="button" onClick={() => void saveStudyOrder()} disabled={busy === "study-save" || !selectedStudies.length} className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{busy === "study-save" ? "Guardando..." : editingStudyId ? "Actualizar orden" : "Guardar orden"}</button></div></div></div>}

    <div className="mt-5 space-y-3"><h4 className="text-sm font-semibold text-slate-700">Órdenes registradas</h4>{laboratoryOrders.map((order) => { const key = `laboratory-${order.id}`; const open = expanded.includes(key); return <article key={key} className="rounded-lg border bg-cyan-50/30 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">Orden de laboratorio #{order.id}{order.is_additional && <span className="ml-2 inline-block rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800">Orden adicional</span>}</p><p className="text-xs text-slate-500">{formatDateTime(order.created_at)} · {order.doctor_name}</p><p className="mt-2 break-words text-sm text-slate-700">{order.items.length} prueba{order.items.length === 1 ? "" : "s"} · {preview(order.items)}</p></div><div className="flex flex-wrap gap-2">{!completed && <button type="button" onClick={() => editLaboratoryOrder(order)} className="rounded-md border border-cyan-300 bg-white px-3 py-1.5 text-sm font-medium text-cyan-800">Editar</button>}<button type="button" onClick={() => void download("laboratory", order.id)} disabled={Boolean(busy)} className="rounded-md bg-cyan-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">PDF</button></div></div>{order.items.length > 3 && <button type="button" aria-expanded={open} onClick={() => toggleDetails(key)} className="mt-3 text-sm font-medium text-cyan-800">{open ? "Ocultar pruebas" : `Ver las ${order.items.length} pruebas`}</button>}{open && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{order.items.map((item) => <li key={item.id}>{item.test_name}{item.custom_note ? ` — ${item.custom_note}` : ""}</li>)}</ul>}{order.notes && <p className="mt-3 text-sm"><strong>Observaciones:</strong> {order.notes}</p>}</article>; })}{studyOrders.map((order) => { const key = `study-${order.id}`; const open = expanded.includes(key); return <article key={key} className="rounded-lg border bg-indigo-50/30 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">Orden de estudios #{order.id}{order.is_additional && <span className="ml-2 inline-block rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800">Orden adicional</span>}</p><p className="text-xs text-slate-500">{formatDateTime(order.created_at)} · {order.doctor_name}</p><p className="mt-2 break-words text-sm text-slate-700">{preview(order.items)}</p></div><div className="flex flex-wrap gap-2">{!completed && <button type="button" onClick={() => editStudyOrder(order)} className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-sm font-medium text-indigo-800">Editar</button>}<button type="button" onClick={() => void download("study", order.id)} disabled={Boolean(busy)} className="rounded-md bg-indigo-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">PDF</button></div></div>{order.items.length > 3 && <button type="button" aria-expanded={open} onClick={() => toggleDetails(key)} className="mt-3 text-sm font-medium text-indigo-800">{open ? "Ocultar estudios" : `Ver los ${order.items.length} estudios`}</button>}{open && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{order.items.map((item) => <li key={item.id}>{item.study_name}{item.region_description ? ` · ${item.region_description}` : ""}{item.contrast !== "not_applicable" ? ` · Contraste: ${item.contrast === "yes" ? "sí" : "no"}` : ""}{item.clinical_notes ? ` · ${item.clinical_notes}` : ""}</li>)}</ul>}{order.notes && <p className="mt-3 text-sm"><strong>Observaciones:</strong> {order.notes}</p>}</article>; })}{!totalOrders && <p className="text-sm text-slate-500">Sin órdenes clínicas registradas.</p>}</div>
    {error && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}{message && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}
  </section>;
}
