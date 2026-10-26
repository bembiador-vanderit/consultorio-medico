import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { User } from "../../types/user";
import type { ClinicalDocumentKind, ClinicalPatientDocument } from "../../types/clinicalPatientDocument";
import { preoperativeSections } from "./fields";
import PhysicalExamSection from "./PhysicalExamSection";
import ClinicalFormRunner from "./ClinicalFormRunner";
import "./clinicalDocumentsPanel.css";

type Scope = { centers: { id: number; name: string }[]; doctors: { id: number; full_name: string; center_ids: number[] }[] };
type Context = { centerId: number; doctorId: number; appointmentId?: number | null; clinicalHistoryId?: number | null };
type PatientIdentity = { dateOfBirth: string; documentNumber?: string | null; phone?: string | null };
type Props = { patientId: number; patientName: string; user: User; context?: Context; patientIdentity?: PatientIdentity; patientSelectionToken?: string | null; allowCreate?: boolean };
const labels: Record<ClinicalDocumentKind, string> = { preoperative: "Evaluación médica preoperatoria", physical_exam: "Examen físico" };
const statuses = { draft: "Borrador", pending_evaluation: "Pendiente de evaluación", completed: "Completada", signed: "Firmada" };

function message(reason: unknown): string {
  const detail = (reason as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "No se pudo completar la operación.";
}

function masked(value?: string | null) {
  const digits = value?.replace(/\D/g, "") ?? "";
  return digits ? `•••${digits.slice(-4)}` : "No registrado";
}

export default function ClinicalDocumentsPanel({ patientId, patientName, user, context, patientIdentity, patientSelectionToken, allowCreate = true }: Props) {
  const permissions = user.permissions ?? [];
  const isDoctor = user.roles.includes("doctor");
  const [secretaryCaps, setSecretaryCaps] = useState<{ start_preoperative: boolean; start_physical_exam: boolean; prepare_administrative: boolean } | null>(null);
  const configurableSecretary = import.meta.env.VITE_CLINICAL_FORM_DESIGNER_ENABLED === "true" && user.roles.includes("secretary") && !user.roles.includes("admin") && !user.roles.includes("doctor");
  const canCreatePreop = allowCreate && (configurableSecretary ? !!secretaryCaps?.start_preoperative : permissions.includes("clinical_documents:create"));
  const canCreateExam = allowCreate && (configurableSecretary ? !!secretaryCaps?.start_physical_exam : permissions.includes("clinical_documents:create"));
  const canCreate = canCreatePreop || canCreateExam;
  const canPrepare = configurableSecretary ? !!secretaryCaps?.prepare_administrative : permissions.includes("clinical_documents:prepare");
  const canEditClinical = user.roles.includes("doctor") && permissions.includes("clinical:access") && permissions.includes("clinical_documents:edit_clinical");
  const canSign = canEditClinical && permissions.includes("clinical_documents:sign");
  const [documents, setDocuments] = useState<ClinicalPatientDocument[]>([]);
  const [scope, setScope] = useState<Scope | null>(null);
  const [centerId, setCenterId] = useState<number | null>(context?.centerId ?? null);
  const [doctorId, setDoctorId] = useState<number | null>(context?.doctorId ?? (isDoctor ? user.id : null));
  const [patientConfirmed, setPatientConfirmed] = useState(false);
  const [active, setActive] = useState<ClinicalPatientDocument | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const doctors = useMemo(() => scope?.doctors.filter((doctor) => doctor.center_ids.includes(centerId ?? -1)) ?? [], [scope, centerId]);
  const permittedCenters = useMemo(() => scope?.centers.filter((center) =>
    scope.doctors.some((doctor) => doctor.center_ids.includes(center.id) && (!isDoctor || doctor.id === user.id))) ?? [], [scope, isDoctor, user.id]);
  const prepared = context && canEditClinical
    ? documents.filter((row) => row.doctor_id === context.doctorId && row.center_id === context.centerId &&
        row.appointment_id === null && row.clinical_history_id === null &&
        (row.status === "draft" || row.status === "pending_evaluation") &&
        !documents.some((current) => current.kind === row.kind && current.appointment_id === context.appointmentId &&
          (current.status === "draft" || current.status === "pending_evaluation"))) : [];

  useEffect(() => {
    if (!context && isDoctor && permittedCenters.length === 1) setCenterId(permittedCenters[0].id);
  }, [context?.centerId, isDoctor, permittedCenters]);

  useEffect(() => {
    if (!configurableSecretary) return;
    let live = true;
    api.get<typeof secretaryCaps>("/clinical-forms/capabilities/me").then(({ data }) => { if (live) setSecretaryCaps(data); })
      .catch(() => { if (live) setSecretaryCaps(null); });
    return () => { live = false; };
  }, [configurableSecretary]);

  useEffect(() => {
    let live = true;
    setActive(null); setDocuments([]); setError(""); setCenterId(context?.centerId ?? null);
    setDoctorId(context?.doctorId ?? (isDoctor ? user.id : null)); setPatientConfirmed(false);
    setLoading(true);
    api.get<ClinicalPatientDocument[]>(`/clinical-documents/patients/${patientId}`).then(({ data }) => {
      if (live) setDocuments(data);
    }).catch((reason) => {
      const status = (reason as { response?: { status?: number } })?.response?.status;
      // A newly selected patient may have no prior appointment or document yet.
      // Creation still requires the server-validated selection proof.
      if (live && !(status === 404 && patientSelectionToken)) setError(message(reason));
    }).finally(() => { if (live) setLoading(false); });
    if (!context) api.get<Scope>("/appointments/scope-options").then(({ data }) => {
      if (live) setScope(data);
    }).catch((reason) => { if (live) setError(message(reason)); });
    return () => { live = false; };
  }, [patientId, context?.centerId, context?.doctorId, patientSelectionToken, isDoctor, user.id]);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  function changeDocument(next: ClinicalPatientDocument | null) {
    if (dirty && !window.confirm("Hay cambios sin guardar. ¿Desea descartarlos?")) return;
    setActive(next); setValues(next?.values ?? {}); setDirty(false); setError(""); setNotice("");
  }
  function changeValue(key: string, value: string) {
    setValues((current) => ({ ...current, [key]: value })); setDirty(true);
  }
  async function refresh() {
    const { data } = await api.get<ClinicalPatientDocument[]>(`/clinical-documents/patients/${patientId}`);
    setDocuments(data);
  }
  async function open(row: ClinicalPatientDocument) {
    if (dirty && !window.confirm("Hay cambios sin guardar. ¿Desea descartarlos?")) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.get<ClinicalPatientDocument>(`/clinical-documents/${row.kind}/${row.id}`);
      setActive(data); setValues(data.values ?? {}); setDirty(false); setNotice("");
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function create(kind: ClinicalDocumentKind) {
    if (!context && !patientConfirmed) { setError("Confirme la identidad del paciente antes de iniciar el documento."); return; }
    if (!centerId || !doctorId) { setError("Seleccione centro y médico."); return; }
    setBusy(true); setError("");
    try {
      const { data, status } = await api.post<ClinicalPatientDocument>(`/clinical-documents/${kind}`, {
        patient_id: patientId, center_id: centerId, doctor_id: doctorId,
        appointment_id: context?.appointmentId ?? null, clinical_history_id: context?.clinicalHistoryId ?? null,
        patient_selection_token: patientSelectionToken ?? null,
      });
      setActive(data); setValues(data.values ?? {}); setDirty(false);
      setNotice(status === 200
        ? `Existe ${kind === "preoperative" ? "una evaluación" : "un examen físico"} pendiente. Continúe en el mismo documento.`
        : "Borrador listo para continuar.");
      await refresh();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function linkPrepared(row: ClinicalPatientDocument) {
    if (!context?.appointmentId) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post<ClinicalPatientDocument>(`/clinical-documents/${row.kind}/${row.id}/link-context`, {
        expected_revision: row.revision, appointment_id: context.appointmentId,
        clinical_history_id: context.clinicalHistoryId ?? null,
      });
      setActive(data); setValues(data.values ?? {}); setDirty(false);
      setNotice("Documento preparado vinculado a esta consulta."); await refresh();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!active || !dirty) return;
    setBusy(true); setError("");
    try {
      const payload = canEditClinical ? values : active.template_admin_fields
        ? Object.fromEntries(active.template_admin_fields.map((field) => [field.key, values[field.key] ?? ""]))
        : { procedimiento: values.procedimiento ?? "" };
      const { data } = await api.put<ClinicalPatientDocument>(`/clinical-documents/${active.kind}/${active.id}`, { expected_revision: active.revision, values: payload });
      setActive(data); setValues(data.values ?? values); setDirty(false); setNotice("Borrador guardado."); await refresh();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function transition(action: "submit" | "complete" | "sign") {
    if (!active) return;
    if (dirty) { setError("Guarde el borrador antes de cambiar el estado."); return; }
    setBusy(true); setError("");
    try {
      const { data } = await api.post<ClinicalPatientDocument>(`/clinical-documents/${active.kind}/${active.id}/${action}`, { expected_revision: active.revision });
      setActive(data); setValues(data.values ?? {}); setNotice(`Estado: ${statuses[data.status]}.`); await refresh();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function printPdf() {
    if (!active) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.get<Blob>(`/clinical-documents/${active.kind}/${active.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const link = document.createElement("a"); link.href = url; link.download = `${active.kind}-${active.id}.pdf`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  const clinicalReadOnly = !canEditClinical || active?.doctor_id !== user.id || active?.status === "signed";
  const administrativeReadOnly = !canPrepare || active?.status === "signed" || active?.status === "completed";
  const shown = context ? documents.filter((row) => row.doctor_id === context.doctorId && row.center_id === context.centerId &&
    (context.appointmentId ? row.appointment_id === context.appointmentId : row.clinical_history_id === context.clinicalHistoryId)) : documents;
  const documentModal = active?.kind === "preoperative" || active?.template_source === "versioned";
  return <section className="min-w-0 rounded-xl border bg-white p-4 shadow-sm sm:p-5" aria-label="Evaluaciones y documentos clínicos">
    <h3 className="text-lg font-semibold text-slate-900">Evaluaciones y documentos clínicos</h3>
    <p className="mt-1 text-sm text-slate-600">{patientName} · La evaluación preoperatoria y el examen físico son documentos independientes.</p>
    {error && <p role="alert" className="mt-3 rounded-md bg-red-50 p-2 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="mt-3 rounded-md bg-emerald-50 p-2 text-sm text-emerald-800">{notice}</p>}
    {!context && canCreate && <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2">
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm sm:col-span-2" aria-label="Confirmar paciente">
        <strong>Confirmar paciente</strong><p>{patientName}</p>
        {patientIdentity ? <p>Documento: {masked(patientIdentity.documentNumber)} · Nacimiento: {`**/**/${patientIdentity.dateOfBirth.slice(0, 4)}`} · Teléfono: {masked(patientIdentity.phone)}</p>
          : <p>Cargando datos de identidad para confirmar...</p>}
        {patientConfirmed ? <p role="status">Paciente confirmado. No podrá cambiarse en el documento iniciado.</p>
          : <button type="button" className="mt-2 rounded-md border border-teal-700 px-3 py-2 text-teal-800 disabled:opacity-50" disabled={!patientIdentity} onClick={() => setPatientConfirmed(true)}>Confirmar paciente</button>}
      </div>
      {(!isDoctor || permittedCenters.length > 1) && <label className="text-sm font-medium">Centro *<select className="mt-1 w-full rounded-md border p-2" value={centerId ?? ""} required aria-required="true" onChange={(event) => { setCenterId(Number(event.target.value) || null); if (!isDoctor) setDoctorId(null); }}><option value="">Seleccione centro</option>{permittedCenters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      {isDoctor ? <p className="text-sm">Médico responsable: <strong>{user.full_name}</strong></p>
        : <label className="text-sm font-medium">Médico responsable *<select className="mt-1 w-full rounded-md border p-2" value={doctorId ?? ""} required aria-required="true" onChange={(event) => setDoctorId(Number(event.target.value) || null)}><option value="">Seleccione médico</option>{doctors.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label>}
      {isDoctor && permittedCenters.length === 1 && <p className="text-sm">Centro: <strong>{permittedCenters[0].name}</strong></p>}
      <p className="text-xs text-slate-500 sm:col-span-2">* Campos obligatorios</p>
    </div>}
    {canCreate && <div className="mt-3 flex flex-wrap gap-2">
      {canCreatePreop && <button type="button" className="rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={busy || !centerId || !doctorId || (!context && !patientConfirmed)} onClick={() => void create("preoperative")}>Nueva evaluación preoperatoria</button>}
      {canCreateExam && <button type="button" className="rounded-md border border-teal-700 px-3 py-2 text-sm font-medium text-teal-800 disabled:opacity-50" disabled={busy || !centerId || !doctorId || (!context && !patientConfirmed)} onClick={() => void create("physical_exam")}>Nuevo examen físico</button>}
    </div>}
    {prepared.length > 0 && <div className="mt-3 rounded-md border border-teal-200 bg-teal-50 p-3 text-sm">
      <strong>{prepared.length === 1 ? "Existe un documento preparado" : "Existen varios documentos preparados"}</strong>
      <p>{prepared.length === 1 ? "Seleccione Continuar para vincularlo a esta consulta." : "Elija explícitamente el documento correcto; Atlas no vincula uno automáticamente."}</p>
      {prepared.map((row) => <button key={`${row.kind}-${row.id}`} type="button" className="mr-2 mt-2 rounded-md border border-teal-700 px-3 py-2 text-teal-800 disabled:opacity-50" disabled={busy} onClick={() => void linkPrepared(row)}>
        Continuar {labels[row.kind]} · {row.document_date}
      </button>)}
    </div>}
    <div className="mt-4">
      <h4 className="font-semibold">Historial del paciente</h4>
      {loading ? <p className="text-sm text-slate-600">Cargando documentos...</p> : shown.length === 0 ? <p className="text-sm text-slate-600">No hay documentos clínicos en este contexto.</p> : <ul className="mt-2 space-y-2">{shown.map((row) => <li key={`${row.kind}-${row.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm">
        <span><strong>{labels[row.kind]}</strong> · {row.document_date} · {statuses[row.status]}<br /><span className="text-slate-600">{row.doctor_name} · {row.center_name} · Iniciado por {row.created_by_name}</span></span>
        <button type="button" className="rounded-md border px-3 py-2 font-medium text-teal-800 disabled:opacity-50" disabled={busy} onClick={() => void open(row)}>{row.status === "draft" || row.status === "pending_evaluation" ? "Continuar" : "Ver"}</button>
      </li>)}</ul>}
    </div>
    {active && <div className={documentModal ? "clinical-document-overlay" : "mt-5 min-w-0 border-t pt-4"}
      role={documentModal ? "dialog" : undefined} aria-modal={documentModal ? "true" : undefined}
      aria-label={documentModal ? labels[active.kind] : undefined} data-clinical-document-form>
      <div className={documentModal ? "clinical-document-dialog" : ""} data-clinical-document-shell>
      <header className={documentModal ? "clinical-document-heading" : "flex flex-wrap items-start justify-between gap-2"}>
        <div><h4 className="text-lg font-semibold">{labels[active.kind]}</h4><p className="text-sm text-slate-600">{statuses[active.status]} · {active.document_date} · {active.doctor_name} · {active.center_name}</p></div>
        <button type="button" className="rounded-md border px-3 py-2 text-sm" onClick={() => changeDocument(null)}>Cerrar documento</button>
      </header>
      <div className={documentModal ? "clinical-document-scroll" : ""} data-clinical-document-scroll={documentModal ? "" : undefined} tabIndex={documentModal ? 0 : undefined}>
      {documentModal && error && <p role="alert" className="mt-3 rounded-md bg-red-50 p-2 text-sm text-red-800">{error}</p>}
      {documentModal && notice && <p role="status" className="mt-3 rounded-md bg-emerald-50 p-2 text-sm text-emerald-800">{notice}</p>}
      {active.patient_profile && <dl className={documentModal ? "clinical-document-patient" : "mt-3 grid gap-2 rounded-md bg-slate-50 p-3 text-sm sm:grid-cols-2"}><div><dt>Paciente</dt><dd className="font-medium">{active.patient_profile.patient_name}</dd></div><div><dt>Nacimiento</dt><dd>{active.patient_profile.date_of_birth ?? "—"}</dd></div><div><dt>Edad al documento</dt><dd>{active.patient_profile.age_at_document ?? "—"}</dd></div><div><dt>Sexo registrado</dt><dd>{active.patient_profile.sex ?? "—"}</dd></div><div><dt>Ocupación</dt><dd>{active.patient_profile.occupation ?? "—"}</dd></div><div><dt>Teléfono</dt><dd>{active.patient_profile.phone ?? "—"}</dd></div><div><dt>Documento</dt><dd>{active.patient_profile.document_number ?? "—"}</dd></div><div><dt>Dirección</dt><dd>{active.patient_profile.address ?? "—"}</dd></div><div><dt>Seguro</dt><dd>{active.patient_profile.insurance_company ?? "—"}</dd></div><div><dt>Plan</dt><dd>{active.patient_profile.insurance_plan ?? "—"}</dd></div></dl>}
      {!active.patient_profile && <p className="mt-3 text-sm text-slate-600">Los campos clínicos solo son visibles para el médico autorizado.</p>}
      {active.template_admin_fields && !canEditClinical && active.template_admin_fields.map((field) => <label key={field.key} className="mt-4 block text-sm font-medium">{field.label}<textarea className="mt-1 block w-full rounded-md border p-2" rows={field.type === "text_long" ? 3 : 1} value={values[field.key] ?? ""} disabled={administrativeReadOnly} onChange={(event) => changeValue(field.key, event.target.value)} /></label>)}
      {!active.template_definition && !active.template_admin_fields && active.kind === "preoperative" && !canEditClinical && <label className="mt-4 block text-sm font-medium">Procedimiento previsto<textarea className="mt-1 block w-full rounded-md border p-2" rows={2} value={values.procedimiento ?? ""} disabled={administrativeReadOnly} onChange={(event) => changeValue("procedimiento", event.target.value)} /></label>}
      {canEditClinical && active.values && active.template_definition && <div className="mt-4"><ClinicalFormRunner definition={active.template_definition} values={values} profile={active.patient_profile} documentDate={active.document_date} onChange={changeValue} readOnly={clinicalReadOnly} /></div>}
      {canEditClinical && active.values && !active.template_definition && <div className="mt-4 space-y-3">
        {active.kind === "preoperative" ? <>
          {preoperativeSections.slice(0, 4).map(([title, fields]) => <DocumentSection key={title} title={title} fields={fields} values={values} onChange={changeValue} readOnly={clinicalReadOnly} />)}
          <details className="rounded-md border p-3"><summary className="cursor-pointer font-semibold">Examen físico</summary><div className="mt-3"><PhysicalExamSection values={values} onChange={changeValue} readOnly={clinicalReadOnly} /></div></details>
          {preoperativeSections.slice(4).map(([title, fields]) => <DocumentSection key={title} title={title} fields={fields} values={values} onChange={changeValue} readOnly={clinicalReadOnly} />)}
        </> : <details className="rounded-md border p-3" open><summary className="cursor-pointer font-semibold">Examen físico</summary><div className="mt-3"><PhysicalExamSection values={values} onChange={changeValue} readOnly={clinicalReadOnly} /></div></details>}
      </div>}
      {dirty && <p className="mt-3 text-sm text-amber-800">Hay cambios sin guardar.</p>}
      {active.template_definition && canEditClinical && <p className="mt-2 text-xs text-slate-600">Impresión: todas las páginas o página actual (seleccione el número en el diálogo de su impresora). Este documento contiene {active.template_definition.pages.length} páginas; puede usar hojas separadas o doble cara si la impresora lo permite.</p>}
      {active.status === "signed" && <p className="mt-2 text-sm text-slate-600">Firmado por el médico autenticado. Documento de solo lectura; una corrección futura requiere un mecanismo de enmienda auditada.</p>}
      </div>
      <footer className={documentModal ? "clinical-document-footer" : "mt-4 flex flex-wrap gap-2"}>
        {!clinicalReadOnly || (canPrepare && !administrativeReadOnly) ? <button type="button" className="rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={!dirty || busy} onClick={() => void save()}>Guardar borrador</button> : null}
        {canPrepare && active.status === "draft" && <button type="button" className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={dirty || busy} onClick={() => void transition("submit")}>Enviar a evaluación</button>}
        {!clinicalReadOnly && (active.status === "draft" || active.status === "pending_evaluation") && <button type="button" className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={dirty || busy} onClick={() => void transition("complete")}>Completar</button>}
        {canSign && !clinicalReadOnly && active.status === "completed" && <button type="button" className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={() => void transition("sign")}>Firmar</button>}
        {canEditClinical && active.values && <button type="button" className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={() => void printPdf()}>Descargar PDF</button>}
      </footer>
      </div>
    </div>}
  </section>;
}

function DocumentSection({ title, fields, values, onChange, readOnly }: { title: string; fields: readonly (readonly [string, string])[]; values: Record<string, string>; onChange: (key: string, value: string) => void; readOnly: boolean }) {
  return <details className="rounded-md border p-3"><summary className="cursor-pointer font-semibold">{title}</summary><div className="mt-3 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
    {fields.map(([key, label]) => <label key={key} className="min-w-0 text-sm font-medium text-slate-700">{label}<textarea className="mt-1 block w-full min-w-0 rounded-md border border-slate-300 p-2 text-slate-900 disabled:bg-slate-100" rows={key === "recomendaciones" ? 4 : 1} value={values[key] ?? ""} maxLength={5000} disabled={readOnly} onChange={(event) => onChange(key, event.target.value)} /></label>)}
  </div></details>;
}
