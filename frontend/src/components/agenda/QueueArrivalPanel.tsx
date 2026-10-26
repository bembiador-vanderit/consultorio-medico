import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { Appointment } from "../../types/appointment";
import type { QueueLine, QueueTicket, QueueTicketEvent } from "../../types/queue";
import type { WaitingRoom } from "../../types/waitingRoom";
import { ProviderPauseCard } from "./ProviderPauseCard";
import { QueueCallCard } from "./QueueCallCard";
import { matchingArrivalLines } from "./queueArrival";

const stamp = (value: string) => new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`)
  .toLocaleTimeString("es-DO", { hour: "2-digit", minute: "2-digit" });
const message = (error: any) => error?.response?.data?.detail || "No fue posible completar la operación.";
const statusLabel: Record<QueueTicket["status"], string> = {
  waiting: "Esperando", called: "Llamado", in_service: "En consulta", completed: "Completado",
  no_response: "Sin respuesta", left: "Se retiró",
};
const disabledAction = "disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-100";
const callAction = `rounded border border-teal-700 bg-teal-700 px-3 py-2 text-sm font-medium text-white enabled:hover:bg-teal-800 ${disabledAction}`;
const startAction = `rounded border border-indigo-700 bg-indigo-700 px-3 py-2 text-sm font-medium text-white enabled:hover:bg-indigo-800 ${disabledAction}`;
const noResponseAction = `rounded border border-amber-700 bg-amber-700 px-3 py-2 text-sm font-medium text-white enabled:hover:bg-amber-800 ${disabledAction}`;
const leftAction = `rounded border border-rose-700 bg-rose-700 px-3 py-2 text-sm font-medium text-white enabled:hover:bg-rose-800 ${disabledAction}`;
const historyAction = "rounded border border-sky-700 bg-sky-700 px-3 py-2 text-sm font-medium text-white hover:bg-sky-800";

export function QueueArrivalPanel({ initialDate, centerId, doctorId, canRecord, canOperate = canRecord, canStart = false, canComplete = false, currentUserId, showPauses = false, canManagePauses = false, pauseAdmin = false, pausePairs, showCallPolicy = false, showWaitingRooms = false, refreshKey = 0 }: {
  initialDate: string; centerId?: number; doctorId?: number; canRecord: boolean; canOperate?: boolean; canStart?: boolean;
  canComplete?: boolean; currentUserId?: number; showPauses?: boolean; canManagePauses?: boolean; pauseAdmin?: boolean;
  pausePairs?: { centerId: number; doctorId: number; doctorName: string }[]; showCallPolicy?: boolean; showWaitingRooms?: boolean; refreshKey?: number;
}) {
  const [day, setDay] = useState(initialDate);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [lines, setLines] = useState<QueueLine[]>([]);
  const [rooms, setRooms] = useState<WaitingRoom[]>([]);
  const [roomId, setRoomId] = useState("");
  const [tickets, setTickets] = useState<QueueTicket[]>([]);
  const [chosenLines, setChosenLines] = useState<Record<number, number>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [history, setHistory] = useState<Record<number, QueueTicketEvent[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => setDay(initialDate), [initialDate]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const params = { ...(centerId ? { center_id: centerId } : {}), ...(doctorId ? { doctor_id: doctorId } : {}) };
    void Promise.all([
      api.get<Appointment[]>("/appointments", { params: { start: day, end: day, ...params } }),
      api.get<QueueLine[]>("/queue-lines", { params: { active_only: true, ...params } }),
      api.get<QueueTicket[]>("/queue-tickets", { params: { day, ...params } }),
      showWaitingRooms ? api.get<WaitingRoom[]>("/waiting-rooms", { params: centerId ? { center_id: centerId } : {} }) : Promise.resolve(null),
    ]).then(([a, l, t, r]) => { if (active) { setAppointments(a.data); setLines(l.data); setTickets(t.data); if (r) setRooms(r.data); } })
      .catch((reason) => { if (active) { setAppointments([]); setLines([]); setTickets([]); setError(message(reason)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [day, centerId, doctorId, refresh, showWaitingRooms, refreshKey]);

  async function perform(ticketId: number, action: "call" | "recall" | "start" | "complete" | "no-response" | "left") {
    if (busyId !== null) return;
    setBusyId(ticketId); setError("");
    try {
      await api.post(`/queue-tickets/${ticketId}/${action}`);
      setHistory((current) => { const copy = { ...current }; delete copy[ticketId]; return copy; });
      setRefresh((value) => value + 1);
    }
    catch (reason) { setError(message(reason)); }
    finally { setBusyId(null); }
  }

  async function callNext(lineId: number) {
    if (busyId !== null) return;
    setBusyId(-lineId); setError("");
    try { await api.post(`/queue-lines/${lineId}/call-next`, null, { params: { day } }); setRefresh((value) => value + 1); }
    catch (reason) { setError(message(reason)); }
    finally { setBusyId(null); }
  }

  async function arrive(appointment: Appointment, lineId: number) {
    if (busyId !== null || !lineId) return;
    setBusyId(appointment.id); setError("");
    try { await api.post(`/queue-tickets/arrivals/${appointment.id}`, { queue_line_id: lineId }); setRefresh((value) => value + 1); }
    catch (reason) { setError(message(reason)); }
    finally { setBusyId(null); }
  }

  async function loadHistory(ticketId: number) {
    if (history[ticketId]) { setHistory((current) => { const copy = { ...current }; delete copy[ticketId]; return copy; }); return; }
    try { const { data } = await api.get<QueueTicketEvent[]>(`/queue-tickets/${ticketId}/events`); setHistory((current) => ({ ...current, [ticketId]: data })); }
    catch (reason) { setError(message(reason)); }
  }

  const ticketByAppointment = new Map(tickets.map((ticket) => [ticket.appointment_id, ticket]));
  const selectedRoom = rooms.find((room) => String(room.id) === roomId);
  const visibleLines = selectedRoom ? lines.filter((line) => selectedRoom.queue_lines.some((item) => item.id === line.id)) : lines;
  const expected = appointments.filter((item) => item.schedule_mode === "queue" &&
    (["scheduled", "confirmed"].includes(item.status) || ticketByAppointment.has(item.id)) &&
    (!selectedRoom || (ticketByAppointment.has(item.id)
      ? visibleLines.some((line) => line.id === ticketByAppointment.get(item.id)?.queue_line_id)
      : visibleLines.some((line) => line.center_id === item.center_id && line.doctor_id === item.doctor_id))))
    .sort((a, b) => {
      const first = ticketByAppointment.get(a.id); const second = ticketByAppointment.get(b.id);
      if (first && second) return first.sequence_number - second.sequence_number || first.id - second.id;
      return first ? -1 : second ? 1 : 0;
    });
  const visiblePausePairs = pausePairs ?? lines.filter((line, index, all) =>
    all.findIndex((item) => item.center_id === line.center_id && item.doctor_id === line.doctor_id) === index,
  ).map((line) => ({ centerId: line.center_id, doctorId: line.doctor_id, doctorName: line.doctor_name }));
  return <section className="agenda-arrivals-panel" aria-label="Llegadas y turnos">
    <header className="agenda-arrivals-panel-header"><div><p className="agenda-panel-eyebrow">Operación de sala</p><h2>Llegadas y turnos</h2><p>Gestiona presencia, disponibilidad y llamado explícito de pacientes.</p></div></header>
    <div className="agenda-arrivals-context" aria-label="Contexto operativo"><label>Fecha <input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>
      {showWaitingRooms && rooms.length > 0 && <label>Sala de espera <select value={roomId} onChange={(event) => setRoomId(event.target.value)}><option value="">Todas las salas autorizadas</option>{rooms.filter((room) => room.is_active).map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>}
    </div>
    {showPauses && <section className="agenda-arrivals-section agenda-arrivals-pauses" aria-label="Pausas operativas"><header><span className="agenda-arrivals-section-icon" aria-hidden="true">Ⅱ</span><div><h3>Pausas operativas</h3><p>Disponibilidad de médicos y pausas activas.</p></div></header><div className="agenda-arrivals-cards agenda-arrivals-cards--pauses">{visiblePausePairs.map((pair) =>
      <ProviderPauseCard key={`${pair.centerId}-${pair.doctorId}`} centerId={pair.centerId} doctorId={pair.doctorId} doctorName={pair.doctorName} canManage={canManagePauses && (pauseAdmin || pair.doctorId === currentUserId)} isAdmin={pauseAdmin} />)}</div>
      {visiblePausePairs.length === 0 && <p className="agenda-arrivals-empty">No hay médicos y centros disponibles en este contexto.</p>}</section>}
    <section className="agenda-arrivals-section agenda-arrivals-calling" aria-label="Llamado de turnos"><header><span className="agenda-arrivals-section-icon" aria-hidden="true">↗</span><div><h3>Llamado de turnos</h3><p>Estado de la línea y pacientes en espera.</p></div></header>
    {showCallPolicy && visibleLines.length > 0 && <div className="agenda-arrivals-cards agenda-arrivals-cards--calling">{visibleLines.map((line) => <QueueCallCard key={line.id} line={line} day={day} canOperate={canOperate} onChanged={() => setRefresh((value) => value + 1)} />)}</div>}
    {!showCallPolicy && canOperate && visibleLines.length > 0 && <div className="agenda-arrivals-call-actions">{visibleLines.map((line) => <button key={line.id} type="button" className={callAction} disabled={busyId !== null} onClick={() => void callNext(line.id)}>Llamar siguiente · {line.name}</button>)}</div>}
    {!loading && visibleLines.length === 0 && <p className="agenda-arrivals-empty">No hay líneas de llamado disponibles en este contexto.</p>}</section>
    {error && <p role="alert" className="agenda-arrivals-error">{error}</p>}
    <section className="agenda-arrivals-section agenda-arrivals-expected" aria-label="Pacientes previstos y llegadas"><header><span className="agenda-arrivals-section-icon" aria-hidden="true">◷</span><div><h3>Pacientes previstos</h3><p>Presencia y estado de turnos de la fecha seleccionada.</p></div><span className="agenda-arrivals-count">{expected.length}</span></header>
    {loading ? <p className="agenda-arrivals-loading">Cargando pacientes previstos…</p> : <div className="agenda-arrivals-cards agenda-arrivals-cards--patients">
      {expected.map((appointment) => {
        const ticket = ticketByAppointment.get(appointment.id);
        const available = matchingArrivalLines(appointment, visibleLines);
        const lineId = chosenLines[appointment.id] ?? (available.length === 1 ? available[0].id : 0);
        const directStartAllowed = ticket ? available.some((line) => line.id === ticket.queue_line_id && line.call_on_consultation_start) : false;
        return <article key={appointment.id} className="agenda-arrivals-patient-card">
          <strong className="block">{appointment.patient_name}</strong>
          <p className="text-sm">Teléfono: {appointment.patient_phone || "Sin teléfono"}</p>
          <p className="mt-1 text-sm text-slate-600">{appointment.doctor_name} · {appointment.center_name} · {appointment.appointment_date}</p>
          {ticket ? <>
            <p className="mt-2 text-sm"><strong>Turno: {ticket.public_code}</strong> · Llegó: {stamp(ticket.arrived_at)} · Estado: {statusLabel[ticket.status]}</p>
            {ticket.consultation_started_at && <p className="text-sm text-slate-600">Inicio de consulta: {stamp(ticket.consultation_started_at)}</p>}
            {ticket.consultation_finished_at && <p className="text-sm text-slate-600">Finalización: {stamp(ticket.consultation_finished_at)}</p>}
            {canOperate && <div className="mt-2 flex flex-wrap gap-2">
              {ticket.status === "waiting" && !showCallPolicy && <button type="button" className={callAction} disabled={busyId !== null} onClick={() => void perform(ticket.id, "call")}>Llamar</button>}
              {ticket.status === "called" && <><button type="button" className={callAction} disabled={busyId !== null} onClick={() => void perform(ticket.id, "recall")}>Volver a llamar</button><button type="button" className={noResponseAction} disabled={busyId !== null} onClick={() => void perform(ticket.id, "no-response")}>Sin respuesta</button></>}
              {canStart && (ticket.status === "called" || (ticket.status === "waiting" && directStartAllowed)) && <button type="button" className={startAction} disabled={busyId !== null} onClick={() => void perform(ticket.id, "start")}>Iniciar consulta</button>}
              {canComplete && ticket.doctor_id === currentUserId && ticket.status === "in_service" && <button type="button" className={startAction} disabled={busyId !== null} onClick={() => { if (window.confirm("¿Finalizar la consulta de este paciente?")) void perform(ticket.id, "complete"); }}>Finalizar consulta</button>}
              {(ticket.status === "waiting" || ticket.status === "called") && <button type="button" className={leftAction} disabled={busyId !== null} onClick={() => void perform(ticket.id, "left")}>Se retiró</button>}
              <button type="button" className={historyAction} onClick={() => void loadHistory(ticket.id)}>{history[ticket.id] ? "Ocultar historial" : "Ver historial"}</button>
            </div>}
            {history[ticket.id] && <ol className="mt-2 space-y-1 text-xs text-slate-600">{history[ticket.id].map((event) => <li key={event.id}>{event.event_type} · {stamp(event.occurred_at)}{event.call_source === "automatic" ? " · llamada automática" : event.actor_user_id ? ` · usuario ${event.actor_user_id}` : ""}</li>)}</ol>}
          </> : canRecord && ["scheduled", "confirmed"].includes(appointment.status) ? <div className="mt-3 flex flex-wrap items-end gap-2">
            {available.length > 1 && <label className="text-sm">Línea <select className="ml-2 rounded border p-2" value={lineId || ""} onChange={(event) => setChosenLines((current) => ({ ...current, [appointment.id]: Number(event.target.value) }))}><option value="">Seleccione</option>{available.map((line) => <option key={line.id} value={line.id}>{line.name} ({line.prefix})</option>)}</select></label>}
            <button type="button" className={callAction} disabled={!lineId || busyId !== null} onClick={() => void arrive(appointment, lineId)}>{busyId === appointment.id ? "Registrando…" : "Registrar llegada"}</button>
            {available.length === 0 && <span className="text-xs text-amber-800">Sin línea activa para este médico y centro.</span>}
          </div> : <p className="mt-2 text-sm text-slate-600">Llegada pendiente</p>}
        </article>;
      })}
      {expected.length === 0 && <p className="agenda-arrivals-empty">No hay citas por turnos previstas para esta fecha y filtros.</p>}
    </div>}
    </section>
  </section>;
}
