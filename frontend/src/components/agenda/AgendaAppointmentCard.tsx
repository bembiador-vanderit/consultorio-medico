import type { CSSProperties, MouseEvent } from "react";
import type { Appointment } from "../../types/appointment";
import { appointmentStatusLabels, formatTime } from "./agenda";

type Variant = "day" | "week" | "month" | "doctor" | "list";
type Props = {
  appointment: Appointment;
  variant: Variant;
  onSelect: (appointment: Appointment) => void;
  style?: CSSProperties;
};

export function AgendaAppointmentCard({ appointment, variant, onSelect, style }: Props) {
  const label = appointmentStatusLabels[appointment.status];
  const statusClass = `agenda-appointment-card--${appointment.status}`;
  const select = (event?: MouseEvent<HTMLButtonElement>) => {
    if (variant === "month") event?.stopPropagation();
    onSelect(appointment);
  };
  if (variant === "week") return <button type="button" className={`agenda-week-appointment-card ${statusClass}`} style={style} onClick={() => select()} aria-label={`Ver cita ${appointment.patient_name}, ${formatTime(appointment.appointment_time)}, ${label}`}><time>{formatTime(appointment.appointment_time)}</time><span className="agenda-week-appointment-summary"><strong>{appointment.patient_name}</strong><span>{appointment.reason || "Sin motivo registrado"}</span><span>{appointment.specialty_name}</span><span className="agenda-event-status">{label}</span></span></button>;
  if (variant === "month") return <button type="button" className={`agenda-month-entry ${statusClass}`} onClick={select} aria-label={`Ver cita de ${appointment.patient_name} a las ${formatTime(appointment.appointment_time)}`}><time>{formatTime(appointment.appointment_time)}</time><span>{appointment.patient_name}</span><span className="agenda-event-status">{label}</span></button>;
  if (variant === "list") return <button type="button" className={`agenda-day-list-item ${statusClass}`} onClick={() => select()}><time>{formatTime(appointment.appointment_time)}</time><span><strong>{appointment.patient_name}</strong><span>{appointment.specialty_name}</span></span><span className="agenda-event-status">{label}</span></button>;
  return <button type="button" className={`agenda-appointment-card agenda-appointment-card--${variant} ${statusClass}`} onClick={() => select()} aria-label={`Ver cita de ${appointment.patient_name} a las ${formatTime(appointment.appointment_time)}`}><time className="agenda-appointment-time">{formatTime(appointment.appointment_time)}</time><span className="agenda-appointment-content"><strong>{appointment.patient_name}</strong><span>{appointment.reason || "Sin motivo registrado"}</span><span className="agenda-appointment-meta">{appointment.specialty_name}</span>{appointment.coverage_id && <span className="agenda-coverage">Cobertura</span>}</span><span className="agenda-event-status">{label}</span></button>;
}
