import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { QueueCallPolicy, QueueLine } from "../../types/queue";

export function QueueCallPolicySettings({ line }: { line: QueueLine }) {
  const [policy, setPolicy] = useState<QueueCallPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void api.get<QueueCallPolicy>(`/queue-lines/${line.id}/call-policy`)
      .then(({ data }) => { if (active) setPolicy(data); })
      .catch(() => { if (active) setError("No se pudo cargar la política de llamada."); });
    return () => { active = false; };
  }, [line.id]);
  async function save() {
    if (!policy || busy) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.put<QueueCallPolicy>(`/queue-lines/${line.id}/call-policy`, {
        call_mode: policy.call_mode, preparation_seconds: policy.preparation_seconds,
        start_consultation_can_call: policy.start_consultation_can_call,
      });
      setPolicy(data);
    } catch (reason: any) { setError(reason?.response?.data?.detail || "No se pudo guardar la política."); }
    finally { setBusy(false); }
  }
  return <div className="mt-3 grid gap-2 rounded border p-3 text-sm sm:col-span-5 sm:grid-cols-3" aria-label={`Política de llamadas ${line.name}`}>
    <label>Modo de llamada<select className="mt-1 w-full rounded border p-2" disabled={!policy} value={policy?.call_mode ?? "manual"}
      onChange={(event) => setPolicy((current) => current && ({ ...current, call_mode: event.target.value as QueueCallPolicy["call_mode"] }))}>
      <option value="manual">Manual</option><option value="assisted">Asistido</option><option value="automatic">Automático</option>
    </select></label>
    <label>Tiempo de preparación (segundos)<input className="mt-1 w-full rounded border p-2" type="number" min={0} max={3600}
      disabled={!policy} value={policy?.preparation_seconds ?? 60}
      onChange={(event) => setPolicy((current) => current && ({ ...current, preparation_seconds: Number(event.target.value) }))} /></label>
    <label className="flex items-center gap-2"><input type="checkbox" disabled={!policy} checked={policy?.start_consultation_can_call ?? false}
      onChange={(event) => setPolicy((current) => current && ({ ...current, start_consultation_can_call: event.target.checked }))} />Permitir que “Iniciar consulta” llame al turno</label>
    <button type="button" className="rounded border px-3 py-2 disabled:opacity-50" disabled={!policy || busy || policy.preparation_seconds < 0 || policy.preparation_seconds > 3600}
      onClick={() => void save()}>Guardar política</button>
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </div>;
}
