import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { clinicalApi, clinicalErrorMessage } from "../../services/clinicalApi";
import type { Diagnosis } from "../../types/clinical";

type Props = {
  episodeId: number;
  historyId: number | null;
  diagnoses: Diagnosis[];
  completed: boolean;
  onChange: Dispatch<SetStateAction<Diagnosis[]>>;
  onError: (message: string) => void;
};

export default function DiagnosesModule(props: Props) {
  return <DiagnosesEditor key={`${props.episodeId}:${props.historyId ?? "new"}`} {...props} />;
}

function DiagnosesEditor({ historyId, diagnoses, completed: isCompleted, onChange: setDiagnoses, onError: setError }: Props) {
  const [diagnosis, setDiagnosis] = useState("");
  const [icd10, setIcd10] = useState("");
  const [primary, setPrimary] = useState(() => !diagnoses.some((item) => item.is_primary));
  const [savingDiagnosis, setSavingDiagnosis] = useState(false);
  // The keyed editor survives harmless rerenders, but not a different episode/history.
  // Writes keep the existing API contract; only delivery of obsolete results is cancelled.
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function addDiagnosis() { if (!historyId || isCompleted || !diagnosis.trim()) return; setSavingDiagnosis(true); setError(""); try { const data = await clinicalApi.createDiagnosis(historyId, { description: diagnosis.trim(), icd10_code: icd10.trim() || null, is_primary: primary }); if (!active.current) return; setDiagnoses((current) => primary ? [data, ...current.map((item) => ({ ...item, is_primary: false }))] : [...current, data]); setDiagnosis(""); setIcd10(""); setPrimary(false); } catch (e: unknown) { if (active.current) setError(clinicalErrorMessage(e, "No fue posible guardar el diagnóstico.")); } finally { if (active.current) setSavingDiagnosis(false); } }
  async function removeDiagnosis(id: number) { if (!historyId || isCompleted) return; try { await clinicalApi.deleteDiagnosis(historyId, id); if (!active.current) return; setDiagnoses((current) => current.filter((item) => item.id !== id)); } catch (e: unknown) { if (active.current) setError(clinicalErrorMessage(e, "No fue posible eliminar el diagnóstico.")); } }
  return <div className="rounded-xl border bg-white p-6 shadow-sm"><div className="flex items-center justify-between"><div><h3 className="text-lg font-semibold">Diagnóstico</h3><p className="text-sm text-slate-500">Uno o varios diagnósticos asociados a esta consulta.</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">CIE-10 preparado</span></div>{!historyId && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Primero guarda la consulta para agregar diagnósticos.</p>}{!isCompleted && <><div className="mt-4 grid gap-3 md:grid-cols-[1fr_160px_auto]"><input value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} placeholder="Descripción del diagnóstico" disabled={!historyId} className="rounded-lg border p-2.5" /><input value={icd10} onChange={(e) => setIcd10(e.target.value)} placeholder="Código CIE-10" disabled={!historyId} className="rounded-lg border p-2.5" /><button onClick={() => void addDiagnosis()} disabled={!historyId || savingDiagnosis || !diagnosis.trim()} className="rounded-lg bg-slate-800 px-4 py-2.5 font-medium text-white disabled:opacity-50">{savingDiagnosis ? "Guardando..." : "Agregar"}</button></div><label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} disabled={!historyId} /> Diagnóstico principal</label></>}<div className="mt-5 space-y-2">{diagnoses.map((item) => <div key={item.id} className="flex items-start justify-between rounded-lg bg-slate-50 p-3"><div><p className="font-medium">{item.description} {item.is_primary && <span className="ml-2 rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">Principal</span>}</p>{item.icd10_code && <p className="text-sm text-slate-500">CIE-10: {item.icd10_code}</p>}</div>{!isCompleted && <button onClick={() => void removeDiagnosis(item.id)} className="text-sm font-medium text-red-600 hover:underline">Eliminar</button>}</div>)}{historyId && !diagnoses.length && <p className="text-sm text-slate-500">No hay diagnósticos registrados.</p>}</div></div>;
}
