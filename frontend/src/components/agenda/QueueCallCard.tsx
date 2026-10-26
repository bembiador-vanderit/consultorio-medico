import { useEffect, useRef, useState } from "react";
import { api } from "../../services/api";
import type { NextCallState, QueueLine } from "../../types/queue";

const asUtc = (stamp: string) => new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(stamp) ? stamp : `${stamp}Z`).getTime();
const modeLabel = { manual: "Manual", assisted: "Asistido", automatic: "Automático" };
const reasonLabel: Record<string, string> = {
  provider_paused: "Médico en pausa · llamada bloqueada", line_inactive: "Línea inactiva",
  provider_unavailable: "Médico o centro no disponible",
  in_service: "Paciente en atención · no se puede llamar otro turno",
  already_called: "Ya hay un turno llamado", no_waiting: "No hay pacientes en espera",
  wrong_day: "La llamada solo corresponde a la jornada actual", preparing: "Preparación entre pacientes",
};

export function QueueCallCard({ line, day, canOperate, onChanged }: {
  line: QueueLine; day: string; canOperate: boolean; onChanged: () => void;
}) {
  const [state, setState] = useState<NextCallState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const previousKey = useRef<string | null>(null);
  useEffect(() => {
    let active = true;
    previousKey.current = null;
    const load = () => void api.get<NextCallState>(`/queue-lines/${line.id}/next-call-state`, { params: { day } })
      .then(({ data }) => { if (active) {
        const key = `${data.next_waiting_ticket_id}:${data.current_in_service_ticket_id}:${data.block_reason}`;
        if (previousKey.current !== null && previousKey.current !== key) onChanged();
        previousKey.current = key;
        setState(data); setReceivedAt(performance.now()); setError("");
      } })
      .catch(() => { if (active) setError("No se pudo consultar el estado de llamada."); });
    load();
    const polling = window.setInterval(load, 5000);
    const ticking = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => { active = false; window.clearInterval(polling); window.clearInterval(ticking); };
  }, [line.id, day]);
  void tick;
  const remaining = state?.ready_at && receivedAt
    ? Math.max(0, Math.ceil((asUtc(state.ready_at) - asUtc(state.server_now) - (performance.now() - receivedAt)) / 1000))
    : 0;
  async function call() {
    if (!state?.can_call || busy) return;
    setBusy(true);
    try {
      await api.post(`/queue-lines/${line.id}/call-next`, null, { params: { day } });
      setState((current) => current && ({ ...current, can_call: false, block_reason: "already_called" }));
      onChanged();
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "La llamada no pudo completarse.");
    } finally { setBusy(false); }
  }
  return <article className="agenda-queue-call-card" aria-label={`Llamadas ${line.name}`}>
    <header><div><strong>{line.doctor_name}</strong><span>{line.name} · Modo: {state ? modeLabel[state.call_mode] : "Cargando…"}</span></div><span className={`agenda-queue-call-state${state?.can_call ? " is-ready" : ""}`}>{state?.can_call ? "Listo" : "Estado operativo"}</span></header>
    {state?.next_waiting_public_code && <p>Siguiente turno: {state.next_waiting_public_code}</p>}
    {state?.block_reason === "preparing" && <p>Preparación: {String(Math.floor(remaining / 60)).padStart(2, "0")}:{String(remaining % 60).padStart(2, "0")}</p>}
    {state?.block_reason && state.block_reason !== "preparing" && <p>{reasonLabel[state.block_reason] || state.block_reason}</p>}
    {state?.can_call && <p>Siguiente turno listo</p>}
    {state?.call_mode === "automatic" && <p>Atlas llamará al siguiente turno al estar listo, si las condiciones siguen vigentes.</p>}
    {canOperate && state?.call_mode !== "automatic" && <button type="button" className="mt-2 rounded border border-teal-700 bg-teal-700 px-3 py-2 text-white enabled:hover:bg-teal-800 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-100"
      disabled={!state?.can_call || busy} onClick={() => void call()}>Llamar ahora</button>}
    {error && <p role="alert" className="agenda-arrivals-error">{error}</p>}
  </article>;
}
