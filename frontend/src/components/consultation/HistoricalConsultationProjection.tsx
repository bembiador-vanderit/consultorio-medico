import ClinicalOrdersHistory from "../clinical/ClinicalOrdersHistory";
import type { HistoricalConsultationDetails } from "../../types/historicalConsultation";
import type { ClinicalHistory } from "../../types/clinical";

type Props = {
  history: ClinicalHistory;
  details: HistoricalConsultationDetails;
  compact?: boolean;
  onSummaryPdf?: () => void;
  onPrescriptionPdf?: () => void;
  onRequestedTestsPdf?: () => void;
  downloading?: string;
};

export default function HistoricalConsultationProjection({ history, details, compact = false, onSummaryPdf, onPrescriptionPdf, onRequestedTestsPdf, downloading = "" }: Props) {
  const documentActions = onSummaryPdf || onPrescriptionPdf || onRequestedTestsPdf;
  return <div className={compact ? "space-y-3" : "mt-5 space-y-4"}>
    <div className="grid gap-4 md:grid-cols-2">
      <HistoryBlock title="Motivo e historia" lines={[history.reason_for_visit, history.current_illness, history.clinical_notes]} />
      <HistoryBlock title="Antecedentes" lines={[history.personal_history, history.family_history, history.allergies, history.chronic_conditions, history.current_medications, history.previous_surgeries, history.habits]} />
      <HistoryBlock title="Signos vitales" lines={vitalSignLines(details.vitalSigns)} />
      <HistoryBlock title="Diagnósticos" lines={details.diagnoses.map((item) => `${item.is_primary ? "Principal · " : ""}${item.icd10_code ? `${item.icd10_code} · ` : ""}${item.description}`)} />
      <HistoryBlock title="Recetas" lines={details.prescriptions.map((item) => `${item.medication}${item.presentation ? ` · ${item.presentation}` : ""}${item.dose ? ` · ${item.dose}` : ""}${item.frequency ? ` · ${item.frequency}` : ""}`)} />
      <HistoryBlock title="Solicitudes heredadas" lines={details.requestedTests.map((item) => item.test_name)} />
    </div>
    <ClinicalOrdersHistory laboratoryOrders={details.laboratoryOrders} studyOrders={details.studyOrders} compact={compact} />
    <HistoricalAddendaTimeline items={details.addenda} compact={compact} />
    {documentActions && <div className="flex flex-wrap gap-2 border-t pt-3">
      {onSummaryPdf && <button type="button" onClick={onSummaryPdf} disabled={Boolean(downloading)} className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">{downloading === "summary" ? "Generando resumen..." : "Resumen PDF"}</button>}
      {onPrescriptionPdf && <button type="button" onClick={onPrescriptionPdf} disabled={!details.prescriptions.length || Boolean(downloading)} className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 disabled:opacity-40">{downloading === "prescription" ? "Generando receta..." : "Receta PDF"}</button>}
      {onRequestedTestsPdf && <button type="button" onClick={onRequestedTestsPdf} disabled={!details.requestedTests.length || Boolean(downloading)} className="rounded-lg border border-indigo-200 px-3 py-2 text-sm font-medium text-indigo-700 disabled:opacity-40">{downloading === "requested-tests" ? "Generando orden..." : "Orden PDF"}</button>}
    </div>}
  </div>;
}

export function HistoricalAddendaTimeline({ items, compact = false }: { items: HistoricalConsultationDetails["addenda"]; compact?: boolean }) {
  if (!items.length) return null;
  return <div className={compact ? "rounded-lg border border-violet-100 bg-violet-50/40 p-3" : "rounded-xl border border-violet-200 bg-violet-50/50 p-4"}>
    <h4 className="font-semibold text-violet-950">Notas adicionales posteriores al cierre</h4>
    <p className="text-xs text-violet-700">Entradas inmutables vinculadas a la consulta original.</p>
    <div className="mt-3 space-y-3">{items.map((item) => <article key={item.id} className="rounded-lg border border-violet-100 bg-white p-3 text-sm">
      <p className="text-xs font-medium text-violet-800">{new Date(item.created_at).toLocaleString("es-DO")} · {item.author_name}</p>
      {item.reason && <p className="mt-2"><strong>Motivo adicional:</strong> {item.reason}</p>}
      {item.note && <p className="mt-1 whitespace-pre-wrap"><strong>Nota adicional:</strong> {item.note}</p>}
    </article>)}</div>
  </div>;
}

function vitalSignLines(vitalSigns: HistoricalConsultationDetails["vitalSigns"]) {
  if (!vitalSigns) return [];
  return [
    `PA: ${vitalSigns.systolic_pressure ?? "—"}/${vitalSigns.diastolic_pressure ?? "—"} mmHg`,
    `FC: ${vitalSigns.heart_rate ?? "—"} lpm · FR: ${vitalSigns.respiratory_rate ?? "—"} rpm`,
    `Temperatura: ${vitalSigns.temperature_c ?? "—"} °C · SpO₂: ${vitalSigns.oxygen_saturation ?? "—"}%`,
    `Peso: ${vitalSigns.weight_kg ?? "—"} kg · Talla: ${vitalSigns.height_cm ?? "—"} cm`,
  ];
}

function HistoryBlock({ title, lines }: { title: string; lines: Array<string | null> }) {
  const visible = lines.filter((line): line is string => Boolean(line));
  return <div className="rounded-lg bg-slate-50 p-4"><h4 className="font-semibold">{title}</h4>{visible.length ? <ul className="mt-2 space-y-1 text-sm text-slate-700">{visible.map((line, index) => <li key={`${title}-${index}`}>{line}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">Sin datos registrados.</p>}</div>;
}
