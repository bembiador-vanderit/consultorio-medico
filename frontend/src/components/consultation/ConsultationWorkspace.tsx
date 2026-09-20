import { useEffect, useRef, useState } from "react";

import ClinicalOrdersSection from "../clinical/ClinicalOrdersSection";
import HistoricalConsultationProjection from "./HistoricalConsultationProjection";
import ConsultationHeader from "./ConsultationHeader";
import AnamnesisModule from "./AnamnesisModule";
import DiagnosesModule from "./DiagnosesModule";
import PrescriptionsModule from "./PrescriptionsModule";
import VitalSignsModule from "./VitalSignsModule";
import { api } from "../../services/api";
import { clinicalApi, clinicalErrorMessage, isReadAborted } from "../../services/clinicalApi";
import { loadHistoricalConsultationDetails } from "../../services/historicalConsultation";
import { useConsultationBootstrap } from "../../hooks/useConsultationBootstrap";
import type { Appointment } from "../../types/appointment";
import type { ClinicalHistory, ClinicalHistoryContent, ConsultationContext, Diagnosis, Prescription, RequestedTest, VitalSigns } from "../../types/clinical";
import type { HistoricalConsultationDetails } from "../../types/historicalConsultation";
import type { User } from "../../types/user";

type Props = { appointment: Appointment; onBack: () => void };
type PreviousDetails = { consultation: ClinicalHistory; details: HistoricalConsultationDetails };

export default function ConsultationWorkspace({ appointment, onBack }: Props) {
  const bootstrap = useConsultationBootstrap(appointment.id);
  const [context, setContext] = useState<ConsultationContext | null>(null);
  const [vitalSigns, setVitalSigns] = useState<VitalSigns | null>(null);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [requestedTests, setRequestedTests] = useState<RequestedTest[]>([]);
  const [saving, setSaving] = useState(false); const [completing, setCompleting] = useState(false); const [loadingVitalSigns, setLoadingVitalSigns] = useState(false);
  const [downloadingSummaryPdf, setDownloadingSummaryPdf] = useState(false); const [downloadingPrescriptionPdf, setDownloadingPrescriptionPdf] = useState(false); const [downloadingTestsPdf, setDownloadingTestsPdf] = useState(false);
  const [saved, setSaved] = useState<ClinicalHistory | null>(null); const [error, setError] = useState("");
  const [previousDetails, setPreviousDetails] = useState<PreviousDetails | null>(null); const [currentUser, setCurrentUser] = useState<User | null>(null); const [loadingPreviousId, setLoadingPreviousId] = useState<number | null>(null);
  const previousRequestGeneration = useRef(0);
  const previousRequestController = useRef<AbortController | null>(null);
  const isCompleted = saved?.status === "completed";
  const previousConsultations = context?.previous_consultations.filter((item) => item.appointment_id !== context.appointment_id) || [];

  useEffect(() => { void api.get<User>("/auth/me").then(({ data }) => setCurrentUser(data)).catch(() => setCurrentUser(null)); }, []);
  useEffect(() => {
    previousRequestGeneration.current += 1;
    previousRequestController.current?.abort();
    previousRequestController.current = null;
    setPreviousDetails(null);
    setLoadingPreviousId(null);
    setContext(null); setSaved(null); setDiagnoses([]); setPrescriptions([]); setRequestedTests([]); setVitalSigns(null); setLoadingVitalSigns(true); setError("");
    return () => { previousRequestGeneration.current += 1; previousRequestController.current?.abort(); previousRequestController.current = null; };
  }, [appointment.id, appointment.reason]);
  useEffect(() => {
    if (bootstrap.loading) return;
    if (bootstrap.error) { setError(bootstrap.error); return; }
    if (!bootstrap.context) return;
    setContext(bootstrap.context); setSaved(bootstrap.history); setDiagnoses(bootstrap.diagnoses); setPrescriptions(bootstrap.prescriptions); setRequestedTests(bootstrap.requestedTests); setVitalSigns(bootstrap.vitalSigns); setLoadingVitalSigns(false);
  }, [bootstrap]);

  async function saveHistory(form: ClinicalHistoryContent) {
    if (!context || isCompleted) return;
    setSaving(true); setError("");
    try {
      const data = saved ? await clinicalApi.updateHistory(saved.id, { ...form, expected_revision: saved.revision }) : await clinicalApi.createHistory(context.patient_id, { ...form, appointment_id: context.appointment_id });
      setSaved(data);
      setContext((current) => current ? { ...current, previous_consultations: current.previous_consultations.some((item) => item.id === data.id) ? current.previous_consultations.map((item) => item.id === data.id ? data : item) : [data, ...current.previous_consultations] } : current);
    } catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible guardar la consulta."));
    } finally { setSaving(false); }
  }

  async function completeConsultation() {
    if (!saved || isCompleted || !window.confirm("¿Finalizar esta consulta? Después quedará en modo de solo lectura.")) return;
    setCompleting(true); setError("");
    try {
      const data = await clinicalApi.completeHistory(saved.id);
      setSaved(data); setContext((current) => current ? { ...current, appointment_status: "completed", previous_consultations: current.previous_consultations.map((item) => item.id === data.id ? data : item) } : current);
    } catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible finalizar la consulta."));
    } finally { setCompleting(false); }
  }

  async function downloadPrescriptionPdf() {
    if (!saved || !prescriptions.length) return;
    setDownloadingPrescriptionPdf(true); setError("");
    try { const blob = await clinicalApi.getPrescriptionPdf(saved.id); downloadBlob(blob, `receta-${saved.id}.pdf`);
    } catch (reason: unknown) { setError(clinicalErrorMessage(reason, "No fue posible generar la receta PDF."));
    } finally { setDownloadingPrescriptionPdf(false); }
  }

  async function downloadRequestedTestsPdf() {
    if (!saved || !requestedTests.length) return;
    setDownloadingTestsPdf(true); setError("");
    try { const response = await api.get<Blob>(`/clinical-history/${saved.id}/requested-tests/pdf`, { responseType: "blob" }); downloadBlob(response.data, `orden-estudios-${saved.id}.pdf`);
    } catch (reason: any) { setError(reason?.response?.data?.detail || "No fue posible generar la orden PDF.");
    } finally { setDownloadingTestsPdf(false); }
  }

  async function downloadSummaryPdf() {
    if (!saved) return;
    setDownloadingSummaryPdf(true); setError("");
    try { const response = await api.get<Blob>(`/clinical-history/${saved.id}/summary/pdf`, { responseType: "blob" }); downloadBlob(response.data, `resumen-consulta-${saved.id}.pdf`);
    } catch (reason: any) { setError(reason?.response?.data?.detail || "No fue posible generar el resumen de consulta.");
    } finally { setDownloadingSummaryPdf(false); }
  }

  async function viewPrevious(consultation: ClinicalHistory) {
    const generation = ++previousRequestGeneration.current;
    previousRequestController.current?.abort();
    const controller = new AbortController();
    previousRequestController.current = controller;
    setLoadingPreviousId(consultation.id); setError("");
    setPreviousDetails(null);
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
    try { const response = await api.get<Blob>(`/clinical-history/${historyId}/summary/pdf`, { responseType: "blob" }); downloadBlob(response.data, `resumen-consulta-${historyId}.pdf`);
    } catch (reason: any) { setError(reason?.response?.data?.detail || "No fue posible generar el resumen anterior."); }
  }

  if (bootstrap.loading) return <section><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver a la agenda</button><p className="mt-6 text-slate-500">Cargando contexto de atención...</p></section>;
  return <section>
    <ConsultationHeader appointment={appointment} specialtyName={context?.specialty_name ?? appointment.specialty_name} onBack={onBack} />
    {error && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {saved && <div className={`mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg p-3 text-sm ${isCompleted ? "bg-slate-200 text-slate-800" : "bg-emerald-50 text-emerald-800"}`}><span>{isCompleted ? "Consulta finalizada y bloqueada en modo de solo lectura." : "Consulta guardada correctamente."} ID #{saved.id} · cita #{saved.appointment_id}.</span><div className="flex flex-wrap gap-2"><button onClick={() => void downloadSummaryPdf()} disabled={downloadingSummaryPdf} className="rounded-lg border border-emerald-300 bg-white px-3 py-2 font-medium text-emerald-800 disabled:opacity-40">{downloadingSummaryPdf ? "Generando resumen..." : "Descargar resumen PDF"}</button>{!isCompleted && <button onClick={() => void completeConsultation()} disabled={completing || saving} className="rounded-lg bg-slate-900 px-3 py-2 font-medium text-white disabled:opacity-40">{completing ? "Finalizando..." : "Finalizar consulta"}</button>}</div></div>}
    <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]"><div className="space-y-6">
      <AnamnesisModule episodeId={appointment.id} appointmentReason={context?.appointment_reason ?? appointment.reason} history={saved} completed={isCompleted} saving={saving} onSave={saveHistory} />
      <VitalSignsModule episodeId={appointment.id} historyId={saved?.id ?? null} vitalSigns={vitalSigns} completed={isCompleted} loading={loadingVitalSigns} onSaved={setVitalSigns} />
      <DiagnosesModule episodeId={appointment.id} historyId={saved?.id ?? null} diagnoses={diagnoses} completed={isCompleted} onChange={setDiagnoses} onError={setError} />
      <PrescriptionsModule episodeId={appointment.id} historyId={saved?.id ?? null} prescriptions={prescriptions} completed={isCompleted} onChange={setPrescriptions} onError={setError} downloadingPrescriptionPdf={downloadingPrescriptionPdf} downloadPrescriptionPdf={downloadPrescriptionPdf} />
      {saved ? <ClinicalOrdersSection historyId={saved.id} specialtyId={saved.specialty_id} completed={isCompleted} allowAdditional={Boolean(isCompleted && currentUser?.is_active && currentUser.roles.includes("doctor") && saved.doctor_id === currentUser.id)} /> : <div className="rounded-xl border border-dashed bg-white p-6 text-sm text-slate-600 shadow-sm">Guarda primero la consulta para crear órdenes estructuradas de laboratorio, estudios o procedimientos.</div>}
      {requestedTests.length > 0 && <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">Solicitudes heredadas</h3><p className="text-sm text-slate-500">Solicitudes registradas con el formato anterior de Atlas.</p></div><button type="button" onClick={() => void downloadRequestedTestsPdf()} disabled={downloadingTestsPdf} className="rounded-lg border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-700 disabled:opacity-40">{downloadingTestsPdf ? "Generando PDF..." : "Descargar orden PDF"}</button></div><ul className="mt-4 space-y-2">{requestedTests.map((item) => <li key={item.id} className="rounded-lg bg-slate-50 p-3 text-sm font-medium">{item.test_name}</li>)}</ul></section>}
    </div><aside className="space-y-4"><div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Contexto de atención</h3><dl className="mt-3 space-y-3 text-sm"><div><dt className="text-slate-500">Paciente</dt><dd className="font-semibold">{appointment.patient_name}</dd></div><div><dt className="text-slate-500">Fecha de nacimiento</dt><dd className="font-semibold">{appointment.patient_date_of_birth}</dd></div><div><dt className="text-slate-500">Documento</dt><dd className="text-slate-500">No registrado en el modelo actual</dd></div><div><dt className="text-slate-500">Médico</dt><dd className="font-semibold">{appointment.doctor_name}</dd></div><div><dt className="text-slate-500">Centro</dt><dd className="font-semibold">{appointment.center_name ? `${appointment.center_name}${appointment.center_city ? ` · ${appointment.center_city}` : ""}` : "Sin centro"}</dd></div><div><dt className="text-slate-500">Motivo</dt><dd>{appointment.reason || "—"}</dd></div></dl><div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">appointment_id: <strong>{context?.appointment_id}</strong><br />doctor_id: <strong>{context?.doctor_id}</strong><br />center_id: <strong>{context?.center_id ?? "NULL"}</strong></div></div><div className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Consultas anteriores</h3>{previousConsultations.length ? <div className="mt-3 space-y-3">{previousConsultations.slice(0, 5).map((item) => <div key={item.id} className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">{item.consultation_date}</p><p className="mt-1 text-slate-600">{item.reason_for_visit || "Sin motivo registrado"}</p><button onClick={() => void viewPrevious(item)} className="mt-2 font-medium text-teal-700 hover:underline">{loadingPreviousId === item.id ? "Cargando..." : "Ver historial completo"}</button></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No hay consultas anteriores.</p>}</div></aside></div>
    {previousDetails && <PreviousConsultationModal details={previousDetails} onClose={() => setPreviousDetails(null)} onDownload={() => void downloadPreviousSummary(previousDetails.consultation.id)} />}
  </section>;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}

function PreviousConsultationModal({ details, onClose, onDownload }: { details: PreviousDetails; onClose: () => void; onDownload: () => void }) {
  const item = details.consultation;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="dialog" aria-modal="true" aria-label="Historial clínico anterior"><div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"><div className="flex items-start justify-between gap-4"><div><h3 className="text-xl font-semibold">Consulta del {item.consultation_date}</h3><p className="text-sm text-slate-500">Historial anterior · solo lectura</p></div><button onClick={onClose} className="rounded border px-3 py-1.5 text-sm">Cerrar</button></div><HistoricalConsultationProjection history={item} details={details.details} onSummaryPdf={onDownload} /></div></div>;
}
