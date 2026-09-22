import { useCallback, useEffect, useRef, useState } from "react";

import { Modal } from "../../ui";
import HistoricalConsultationProjection from "./HistoricalConsultationProjection";
import ConsultationHeader from "./ConsultationHeader";
import { consultationModuleRegistry, defaultWorkspaceModules, isKnownConsultationModule } from "./consultationModuleRegistry";
import { api } from "../../services/api";
import { clinicalApi, clinicalErrorMessage, isReadAborted, isRevisionConflict } from "../../services/clinicalApi";
import { loadHistoricalConsultationDetails } from "../../services/historicalConsultation";
import { useConsultationBootstrap } from "../../hooks/useConsultationBootstrap";
import { useConsultationDirtyState } from "../../hooks/useConsultationDirtyState";
import type { NavigationGuardRegistrar } from "../../navigation/navigation";
import type { Appointment } from "../../types/appointment";
import type { ClinicalHistory, ClinicalHistoryContent, ConsultationContext, Diagnosis, Prescription, RequestedTest, VitalSigns } from "../../types/clinical";
import type { HistoricalConsultationDetails } from "../../types/historicalConsultation";
import type { User } from "../../types/user";

type Props = { appointment: Appointment; onBack: () => void; registerNavigationGuard?: NavigationGuardRegistrar };
type PreviousDetails = { consultation: ClinicalHistory; details: HistoricalConsultationDetails };

export default function ConsultationWorkspace({ appointment, onBack, registerNavigationGuard }: Props) {
  const bootstrap = useConsultationBootstrap(appointment.id);
  const { dirtySections, hasDirtyChanges, setSectionDirty, clearDirty } = useConsultationDirtyState(appointment.id);
  const [context, setContext] = useState<ConsultationContext | null>(null);
  const [vitalSigns, setVitalSigns] = useState<VitalSigns | null>(null);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [requestedTests, setRequestedTests] = useState<RequestedTest[]>([]);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [loadingVitalSigns, setLoadingVitalSigns] = useState(false);
  const [downloadingSummaryPdf, setDownloadingSummaryPdf] = useState(false);
  const [downloadingPrescriptionPdf, setDownloadingPrescriptionPdf] = useState(false);
  const [downloadingTestsPdf, setDownloadingTestsPdf] = useState(false);
  const [saved, setSaved] = useState<ClinicalHistory | null>(null);
  const [error, setError] = useState("");
  const [revisionConflict, setRevisionConflict] = useState(false);
  const [completionModalOpen, setCompletionModalOpen] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  const [previousDetails, setPreviousDetails] = useState<PreviousDetails | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loadingPreviousId, setLoadingPreviousId] = useState<number | null>(null);
  const previousRequestGeneration = useRef(0);
  const previousRequestController = useRef<AbortController | null>(null);
  const isCompleted = saved?.status === "completed";
  const previousConsultations = context?.previous_consultations.filter((item) => item.appointment_id !== context.appointment_id) || [];
  const workspaceModules = [...(context?.workspace?.modules ?? defaultWorkspaceModules)].sort((left, right) => left.position - right.position);
  const unknownModuleKeys = workspaceModules.filter((module) => !isKnownConsultationModule(module.key)).map((module) => module.key);

  const setAnamnesisDirty = useCallback((dirty: boolean) => setSectionDirty("anamnesis", dirty), [setSectionDirty]);
  const setVitalSignsDirty = useCallback((dirty: boolean) => setSectionDirty("vital-signs", dirty), [setSectionDirty]);
  const setDiagnosesDirty = useCallback((dirty: boolean) => setSectionDirty("diagnoses", dirty), [setSectionDirty]);
  const setPrescriptionsDirty = useCallback((dirty: boolean) => setSectionDirty("prescriptions", dirty), [setSectionDirty]);
  const setOrdersDirty = useCallback((dirty: boolean) => setSectionDirty("orders", dirty), [setSectionDirty]);
  const requestLeave = useCallback((proceed: () => void) => {
    if (!hasDirtyChanges) { proceed(); return; }
    setPendingNavigation(() => proceed);
  }, [hasDirtyChanges]);

  useEffect(() => {
    registerNavigationGuard?.(requestLeave);
    return () => registerNavigationGuard?.(null);
  }, [requestLeave, registerNavigationGuard]);

  useEffect(() => {
    let active = true;
    void api.get<User>("/auth/me").then(({ data }) => { if (active) setCurrentUser(data); }).catch(() => { if (active) setCurrentUser(null); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    previousRequestGeneration.current += 1;
    previousRequestController.current?.abort();
    previousRequestController.current = null;
    setPreviousDetails(null);
    setLoadingPreviousId(null);
    setContext(null);
    setSaved(null);
    setDiagnoses([]);
    setPrescriptions([]);
    setRequestedTests([]);
    setVitalSigns(null);
    setLoadingVitalSigns(true);
    setRevisionConflict(false);
    setCompletionModalOpen(false);
    setPendingNavigation(null);
    setError("");
    return () => {
      previousRequestGeneration.current += 1;
      previousRequestController.current?.abort();
      previousRequestController.current = null;
    };
  }, [appointment.id, appointment.reason]);

  useEffect(() => {
    if (bootstrap.loading) return;
    if (bootstrap.error) { setError(bootstrap.error); return; }
    if (!bootstrap.context) return;
    setContext(bootstrap.context);
    setSaved(bootstrap.history);
    setDiagnoses(bootstrap.diagnoses);
    setPrescriptions(bootstrap.prescriptions);
    setRequestedTests(bootstrap.requestedTests);
    setVitalSigns(bootstrap.vitalSigns);
    setLoadingVitalSigns(false);
  }, [bootstrap.loading, bootstrap.error, bootstrap.context, bootstrap.history, bootstrap.diagnoses, bootstrap.prescriptions, bootstrap.requestedTests, bootstrap.vitalSigns, bootstrap.version]);

  async function saveHistory(form: ClinicalHistoryContent) {
    if (!context || isCompleted) return;
    setSaving(true);
    setError("");
    try {
      const data = saved
        ? await clinicalApi.updateHistory(saved.id, { ...form, expected_revision: saved.revision })
        : await clinicalApi.createHistory(context.patient_id, { ...form, appointment_id: context.appointment_id });
      setSaved(data);
      setRevisionConflict(false);
      setContext((current) => current ? {
        ...current,
        previous_consultations: current.previous_consultations.some((item) => item.id === data.id)
          ? current.previous_consultations.map((item) => item.id === data.id ? data : item)
          : [data, ...current.previous_consultations],
      } : current);
    } catch (reason: unknown) {
      if (isRevisionConflict(reason)) setRevisionConflict(true);
      else setError(clinicalErrorMessage(reason, "No fue posible guardar la consulta."));
    } finally {
      setSaving(false);
    }
  }

  async function reloadServerVersion() {
    if (hasDirtyChanges && !window.confirm("Recargar la versión del servidor descartará los cambios locales sin guardar. ¿Desea continuar?")) return;
    setError("");
    const loaded = await bootstrap.reload();
    if (loaded) { clearDirty(); setRevisionConflict(false); }
  }

  function openCompletionModal() {
    if (!saved || isCompleted || saving || completing || hasDirtyChanges) return;
    setError("");
    setCompletionModalOpen(true);
  }

  async function completeConsultation() {
    if (hasDirtyChanges) { setError("Guarde o descarte los cambios pendientes antes de finalizar."); return; }
    if (!saved || isCompleted || completing) return;
    setCompleting(true);
    setError("");
    try {
      const data = await clinicalApi.completeHistory(saved.id);
      setSaved(data);
      setContext((current) => current ? { ...current, appointment_status: "completed", previous_consultations: current.previous_consultations.map((item) => item.id === data.id ? data : item) } : current);
      setCompletionModalOpen(false);
    } catch (reason: unknown) {
      setError(clinicalErrorMessage(reason, "No fue posible finalizar la consulta."));
    } finally {
      setCompleting(false);
    }
  }

  async function downloadPrescriptionPdf() {
    if (!saved || !prescriptions.length) return;
    setDownloadingPrescriptionPdf(true); setError("");
    try { downloadBlob(await clinicalApi.getPrescriptionPdf(saved.id), `receta-${saved.id}.pdf`); }
    catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible generar la receta PDF.")); }
    finally { setDownloadingPrescriptionPdf(false); }
  }

  async function downloadRequestedTestsPdf() {
    if (!saved || !requestedTests.length) return;
    setDownloadingTestsPdf(true); setError("");
    try { downloadBlob(await clinicalApi.getRequestedTestsPdf(saved.id), `orden-estudios-${saved.id}.pdf`); }
    catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible generar la orden PDF.")); }
    finally { setDownloadingTestsPdf(false); }
  }

  async function downloadSummaryPdf() {
    if (!saved) return;
    setDownloadingSummaryPdf(true); setError("");
    try { downloadBlob(await clinicalApi.getSummaryPdf(saved.id), `resumen-consulta-${saved.id}.pdf`); }
    catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible generar el resumen de consulta.")); }
    finally { setDownloadingSummaryPdf(false); }
  }

  async function viewPrevious(consultation: ClinicalHistory) {
    const generation = ++previousRequestGeneration.current;
    previousRequestController.current?.abort();
    const controller = new AbortController();
    previousRequestController.current = controller;
    setLoadingPreviousId(consultation.id); setError(""); setPreviousDetails(null);
    try {
      const details = await loadHistoricalConsultationDetails(consultation.id, { signal: controller.signal });
      if (generation !== previousRequestGeneration.current) return;
      setPreviousDetails({ consultation, details });
    } catch (reason: any) {
      if (generation !== previousRequestGeneration.current || isReadAborted(reason)) return;
      setError(reason?.response?.data?.detail || "No fue posible cargar el historial anterior.");
    } finally {
      if (generation === previousRequestGeneration.current) { setLoadingPreviousId(null); previousRequestController.current = null; }
    }
  }

  async function downloadPreviousSummary(historyId: number) {
    setError("");
    try { downloadBlob(await clinicalApi.getSummaryPdf(historyId), `resumen-consulta-${historyId}.pdf`); }
    catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible generar el resumen anterior.")); }
  }

  const leaveConsultation = () => requestLeave(onBack);

  function discardChangesAndLeave() {
    const proceed = pendingNavigation;
    setPendingNavigation(null);
    proceed?.();
  }

  if (bootstrap.loading) return <section><button type="button" onClick={leaveConsultation} className="text-sm font-medium text-teal-700 hover:underline">← Volver a la agenda</button><p role="status" className="mt-6 text-slate-500">Cargando contexto de atención...</p></section>;

  return <section className="min-w-0">
    <ConsultationHeader appointment={appointment} specialtyName={context?.specialty_name ?? appointment.specialty_name} onBack={leaveConsultation} />
    {revisionConflict && <div role="alert" className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><p className="font-semibold">La consulta fue modificada en otra sesión o pestaña.</p><p className="mt-1">Los cambios locales no fueron guardados y permanecen visibles. Atlas no volverá a enviarlos automáticamente.</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => void reloadServerVersion()} disabled={bootstrap.refreshing} className="rounded-lg bg-amber-800 px-3 py-2 font-medium text-white disabled:opacity-50">{bootstrap.refreshing ? "Recargando..." : "Recargar versión del servidor"}</button><button type="button" onClick={() => setRevisionConflict(false)} className="rounded-lg border border-amber-400 bg-white px-3 py-2 font-medium text-amber-900">Continuar revisando mis cambios</button></div></div>}
    {error && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {bootstrap.refreshing && <p role="status" aria-live="polite" className="mt-4 rounded-lg bg-sky-50 p-3 text-sm text-sky-800">Recargando la versión actual del servidor...</p>}
    {saved && <div role="status" aria-live="polite" className={`mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg p-3 text-sm ${isCompleted ? "bg-slate-200 text-slate-800" : "bg-emerald-50 text-emerald-800"}`}><span>{isCompleted ? "Consulta finalizada y bloqueada en modo de solo lectura." : hasDirtyChanges ? "Consulta en progreso · hay cambios locales pendientes." : "Consulta guardada correctamente."}</span><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void downloadSummaryPdf()} disabled={downloadingSummaryPdf} className="rounded-lg border border-emerald-300 bg-white px-3 py-2 font-medium text-emerald-800 disabled:opacity-40">{downloadingSummaryPdf ? "Generando resumen..." : "Descargar resumen PDF"}</button>{!isCompleted && <button type="button" onClick={openCompletionModal} disabled={completing || saving || hasDirtyChanges} aria-describedby={hasDirtyChanges ? "consultation-pending-completion" : undefined} className="rounded-lg bg-slate-900 px-3 py-2 font-medium text-white disabled:opacity-40">Finalizar consulta</button>}</div>{!isCompleted && hasDirtyChanges && <p id="consultation-pending-completion" className="w-full rounded-md bg-amber-100 p-2 text-amber-900">Guarde o descarte los cambios pendientes antes de finalizar.</p>}</div>}
    <div data-consultation-layout="adaptive" className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(17rem,20rem)]"><div data-consultation-modules className="min-w-0 space-y-6">
      {unknownModuleKeys.length > 0 && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-5 text-sm text-red-800"><p className="font-semibold">La plantilla clínica contiene módulos que esta versión de Atlas no reconoce.</p><p className="mt-1 break-words">No se ignoraron silenciosamente: {unknownModuleKeys.join(", ")}. Solicite la actualización de la configuración antes de continuar.</p></div>}
      {context && workspaceModules.filter((module) => isKnownConsultationModule(module.key)).map((module) => <div key={`${context.workspace?.template_id ?? "legacy"}:${module.key}`} data-consultation-module={module.key}>{consultationModuleRegistry[module.key as keyof typeof consultationModuleRegistry].render({ appointment, bootstrapVersion: bootstrap.version, context, saved, completed: Boolean(isCompleted), saving, vitalSigns, loadingVitalSigns, setVitalSigns, diagnoses, setDiagnoses, prescriptions, setPrescriptions, setError, currentUser, downloadingPrescriptionPdf, downloadPrescriptionPdf, saveHistory, onAnamnesisDirty: setAnamnesisDirty, onVitalSignsDirty: setVitalSignsDirty, onDiagnosesDirty: setDiagnosesDirty, onPrescriptionsDirty: setPrescriptionsDirty, onOrdersDirty: setOrdersDirty })}</div>)}
      {requestedTests.length > 0 && <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">Solicitudes heredadas</h3><p className="text-sm text-slate-500">Solicitudes registradas con el formato anterior de Atlas.</p></div><button type="button" onClick={() => void downloadRequestedTestsPdf()} disabled={downloadingTestsPdf} className="rounded-lg border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-700 disabled:opacity-40">{downloadingTestsPdf ? "Generando PDF..." : "Descargar orden PDF"}</button></div><ul className="mt-4 space-y-2">{requestedTests.map((item) => <li key={item.id} className="break-words rounded-lg bg-slate-50 p-3 text-sm font-medium">{item.test_name}</li>)}</ul></section>}
    </div><aside data-consultation-context className="min-w-0 space-y-4"><div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Contexto de atención</h3><dl className="mt-3 space-y-3 text-sm"><div><dt className="text-slate-500">Paciente</dt><dd className="break-words font-semibold">{appointment.patient_name}</dd></div><div><dt className="text-slate-500">Fecha de nacimiento</dt><dd className="font-semibold">{appointment.patient_date_of_birth}</dd></div>{context?.patient_blood_type && <div><dt className="text-slate-500">Tipo sanguíneo declarado/registrado (ficha actual)</dt><dd className="break-words">{context.patient_blood_type} · No equivale a confirmación de laboratorio</dd></div>}<div><dt className="text-slate-500">Médico</dt><dd className="break-words font-semibold">{appointment.doctor_name}</dd></div><div><dt className="text-slate-500">Centro</dt><dd className="break-words font-semibold">{appointment.center_name ? `${appointment.center_name}${appointment.center_city ? ` · ${appointment.center_city}` : ""}` : "Sin centro"}</dd></div><div><dt className="text-slate-500">Motivo</dt><dd className="break-words">{appointment.reason || "—"}</dd></div></dl></div><div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Consultas anteriores</h3>{previousConsultations.length ? <div className="mt-3 space-y-3">{previousConsultations.slice(0, 5).map((item) => <div key={item.id} className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">{item.consultation_date}</p><p className="mt-1 break-words text-slate-600">{item.reason_for_visit || "Sin motivo registrado"}</p><button type="button" onClick={() => void viewPrevious(item)} disabled={loadingPreviousId === item.id} className="mt-2 font-medium text-teal-700 hover:underline disabled:opacity-50">{loadingPreviousId === item.id ? "Cargando..." : "Ver historial completo"}</button></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No hay consultas anteriores.</p>}</div></aside></div>
    {previousDetails && <PreviousConsultationModal details={previousDetails} onClose={() => setPreviousDetails(null)} onDownload={() => void downloadPreviousSummary(previousDetails.consultation.id)} />}
    {completionModalOpen && <CompletionConfirmationModal completing={completing} onClose={() => { if (!completing) setCompletionModalOpen(false); }} onConfirm={() => void completeConsultation()} />}
    {pendingNavigation && <UnsavedChangesModal onClose={() => setPendingNavigation(null)} onConfirm={discardChangesAndLeave} />}
    <span className="sr-only" aria-live="polite">{dirtySections.size ? `${dirtySections.size} secciones con cambios sin guardar` : "Sin cambios pendientes"}</span>
  </section>;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}

function PreviousConsultationModal({ details, onClose, onDownload }: { details: PreviousDetails; onClose: () => void; onDownload: () => void }) {
  const item = details.consultation;
  return <Modal open onClose={onClose} title={`Consulta del ${item.consultation_date}`} description="Historial anterior · solo lectura" closeLabel="Cerrar historial anterior" className="!w-[min(64rem,calc(100vw-2rem))]"><HistoricalConsultationProjection history={item} details={details.details} onSummaryPdf={onDownload} /></Modal>;
}

function CompletionConfirmationModal({ completing, onClose, onConfirm }: { completing: boolean; onClose: () => void; onConfirm: () => void }) {
  return <Modal open onClose={onClose} closeDisabled={completing} title="Finalizar consulta" closeLabel="Cerrar confirmación de finalización"
    footer={<><button type="button" onClick={onClose} disabled={completing} className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-slate-700 disabled:opacity-50">Cancelar</button><button type="button" onClick={onConfirm} disabled={completing} className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50">{completing ? "Finalizando..." : "Finalizar consulta"}</button></>}>
    <p className="text-slate-900">¿Desea finalizar esta consulta?</p>
    <p className="mt-2 text-sm text-slate-600">Después de finalizarla, la consulta quedará en modo de solo lectura y no podrá modificar su contenido clínico.</p>
  </Modal>;
}

function UnsavedChangesModal({ onClose, onConfirm }: { onClose: () => void; onConfirm: () => void }) {
  return <Modal open onClose={onClose} title="Cambios sin guardar" closeLabel="Continuar editando"
    footer={<><button type="button" onClick={onClose} className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-slate-700">Continuar editando</button><button type="button" onClick={onConfirm} className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white">Salir sin guardar</button></>}>
    <p className="text-slate-900">Hay cambios sin guardar en esta consulta.</p>
    <p className="mt-2 text-sm text-slate-600">Si sale ahora, los cambios pendientes se perderán.</p>
  </Modal>;
}
