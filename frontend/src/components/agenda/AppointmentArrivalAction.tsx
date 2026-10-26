import { useEffect, useRef, useState } from "react";
import type { Appointment } from "../../types/appointment";
import type { QueueLine, QueueTicket } from "../../types/queue";
import type { User } from "../../types/user";
import { api } from "../../services/api";
import { Alert, Button } from "../../ui";
import { isoDate } from "./agenda";
import { matchingArrivalLines, queueTicketStatusLabel, type ArrivalLookup } from "./queueArrival";

type Props = {
  appointment: Appointment;
  user: User;
  canAccessPair: boolean;
  busy?: boolean;
  onChanged: () => void;
  lookup?: ArrivalLookup;
  presentation?: "detail" | "row";
};

function errorMessage(reason: any) {
  return typeof reason?.response?.data?.detail === "string"
    ? reason.response.data.detail
    : "No fue posible registrar la llegada.";
}

export function AppointmentArrivalAction({ appointment, user, canAccessPair, busy: parentBusy, onChanged, lookup, presentation = "detail" }: Props) {
  const [lines, setLines] = useState<QueueLine[]>([]);
  const [ticket, setTicket] = useState<QueueTicket | null>(null);
  const [selectedLineId, setSelectedLineId] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hourlyArrived, setHourlyArrived] = useState<string | null>(null);
  const processing = useRef(false);
  const canRead = user.is_active && user.access_scope !== "platform" &&
    (user.membership_state === undefined || user.membership_state === "active") &&
    (user.permissions === undefined || user.permissions.includes("patients:access")) &&
    !user.denied_permissions?.includes("patients:access") && canAccessPair;
  const canRecord = canRead && (user.roles.includes("secretary") || user.roles.includes("admin"));
  const queueAppointment = appointment.schedule_mode === "queue" && appointment.center_id !== null;

  useEffect(() => {
    setHourlyArrived(null);
    setLines([]); setTicket(null); setSelectedLineId(""); setError("");
    if (!queueAppointment || !canRead || lookup) return;
    let active = true;
    setLoading(true);
    const params = { center_id: appointment.center_id, doctor_id: appointment.doctor_id };
    void Promise.all([
      api.get<QueueLine[]>("/queue-lines", { params: { active_only: true, ...params } }),
      api.get<QueueTicket[]>("/queue-tickets", { params: { day: appointment.appointment_date, ...params } }),
    ]).then(([lineResponse, ticketResponse]) => {
      if (!active) return;
      setLines(lineResponse.data);
      setTicket(ticketResponse.data.find((item) => item.appointment_id === appointment.id) ?? null);
    }).catch((reason) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [appointment.id, appointment.appointment_date, appointment.center_id, appointment.doctor_id, queueAppointment, canRead, Boolean(lookup)]);

  if (!canRead) return null;
  if (appointment.schedule_mode === "timed") {
    const arrivedAt = appointment.arrived_at || hourlyArrived;
    const active = ["scheduled", "confirmed"].includes(appointment.status);
    if (arrivedAt) return <div role="status" className="agenda-inline-arrival-result">
      <span>✓ Llegada registrada</span><span>{appointment.clinical_history_status === "completed" || appointment.status === "completed"
        ? "Atención completada" : appointment.has_clinical_history ? "En atención" : "Llegó · En espera"}</span>
    </div>;
    if (!canRecord || !active || appointment.has_clinical_history || appointment.appointment_date !== isoDate(new Date())) return null;
    return <>
      {error && <Alert tone="danger" title="No se pudo registrar la llegada">{error}</Alert>}
      {appointment.arrival_enabled === false ? <span className="atlas-muted">Llegada por hora pendiente de activación.</span> :
        <Button loading={busy} loadingLabel="Registrando…" disabled={parentBusy} onClick={() => void registerHourlyArrival()}>Registrar llegada</Button>}
    </>;
  }
  if (!queueAppointment) return null;
  const available = matchingArrivalLines(appointment, lookup?.lines ?? lines);
  const existingTicket = (ticket?.appointment_id === appointment.id ? ticket : null) ??
    lookup?.tickets.find((item) => item.appointment_id === appointment.id) ?? null;
  const checking = lookup?.loading ?? loading;
  const lookupError = error || lookup?.error || "";
  const lineId = available.length === 1 ? available[0].id :
    available.some((line) => String(line.id) === selectedLineId) ? Number(selectedLineId) : 0;
  const eligible = canRecord && ["scheduled", "confirmed"].includes(appointment.status) &&
    appointment.appointment_date === isoDate(new Date()) && available.length > 0;
  const canOffer = eligible && !existingTicket;
  const missingLine = presentation === "row" && canRecord && !existingTicket &&
    ["scheduled", "confirmed"].includes(appointment.status) &&
    appointment.appointment_date === isoDate(new Date()) && !available.length && !checking && !lookupError;

  async function registerHourlyArrival() {
    if (!canRecord || processing.current || parentBusy || busy) return;
    processing.current = true; setBusy(true); setError("");
    try {
      const { data } = await api.post<Appointment>(`/appointments/${appointment.id}/arrival`, {});
      setHourlyArrived(data.arrived_at || null);
      onChanged();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { processing.current = false; setBusy(false); }
  }

  async function registerArrival() {
    if (!canOffer || !lineId || processing.current || busy || parentBusy) return;
    processing.current = true;
    setBusy(true); setError("");
    try {
      const { data } = await api.post<QueueTicket>(`/queue-tickets/arrivals/${appointment.id}`, { queue_line_id: lineId });
      setTicket(data);
      onChanged();
    } catch (reason: any) {
      if (reason?.response?.status === 409) {
        try {
          const { data } = await api.get<QueueTicket[]>("/queue-tickets", { params: {
            day: appointment.appointment_date, center_id: appointment.center_id, doctor_id: appointment.doctor_id,
          } });
          const existing = data.find((item) => item.appointment_id === appointment.id);
          if (existing) { setTicket(existing); onChanged(); return; }
        } catch { /* Preserve the original conflict instead of hiding a real error. */ }
      }
      setError(errorMessage(reason));
    } finally {
      processing.current = false;
      setBusy(false);
    }
  }

  if (checking) return presentation === "row" ? null : <p className="atlas-muted">Comprobando llegada…</p>;
  return <>
    {lookupError && <Alert tone="danger" title="No se pudo registrar la llegada">{lookupError}</Alert>}
    {existingTicket ? presentation === "row"
      ? <div role="status" className="agenda-inline-arrival-result"><span>✓ Llegada registrada</span><span>Turno {existingTicket.public_code}</span><span>Estado: {queueTicketStatusLabel[existingTicket.status]}</span></div>
      : <p role="status" className="atlas-muted">✓ Llegada registrada · Turno {existingTicket.public_code} · Estado: {queueTicketStatusLabel[existingTicket.status]}</p> :
      canOffer && <div className="flex flex-wrap items-end gap-2">
        {available.length > 1 && <label className="text-sm">Línea de turnos <select className="ml-2 rounded border p-2" value={lineId || ""} onChange={(event) => setSelectedLineId(event.target.value)}>
          <option value="">Seleccione</option>{available.map((line) => <option key={line.id} value={line.id}>{line.name} ({line.prefix})</option>)}
        </select></label>}
        <Button loading={busy} loadingLabel="Registrando…" disabled={parentBusy || !lineId} onClick={() => void registerArrival()}>Registrar llegada</Button>
      </div>}
    {missingLine && <span className="agenda-inline-arrival-warning" title="Este médico no tiene una línea de turnos configurada para este centro.">Este médico no tiene una línea de turnos configurada para este centro.</span>}
  </>;
}
