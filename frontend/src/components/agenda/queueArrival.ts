import type { Appointment } from "../../types/appointment";
import type { QueueLine, QueueTicket } from "../../types/queue";

export const queueTicketStatusLabel: Record<QueueTicket["status"], string> = {
  waiting: "En espera",
  called: "Llamado",
  in_service: "En consulta",
  completed: "Completado",
  no_response: "Sin respuesta",
  left: "Se retiró",
};

export type ArrivalLookup = {
  lines: QueueLine[];
  tickets: QueueTicket[];
  loading: boolean;
  error: string;
};

export function matchingArrivalLines(appointment: Appointment, lines: QueueLine[]) {
  return lines.filter((line) => line.is_active && line.center_id === appointment.center_id &&
    line.doctor_id === appointment.doctor_id &&
    (line.specialty_id === null || line.specialty_id === appointment.specialty_id));
}
