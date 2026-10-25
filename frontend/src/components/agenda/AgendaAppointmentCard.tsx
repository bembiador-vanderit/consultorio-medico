import type { CSSProperties, MouseEvent, ReactNode } from "react";
import type { Appointment } from "../../types/appointment";
import { appointmentStatusLabels, formatTime } from "./agenda";

type Variant = "day" | "week" | "month" | "doctor" | "list";
type Props = {
  appointment: Appointment;
  variant: Variant;
  onSelect: (appointment: Appointment) => void;
  style?: CSSProperties;
  arrivalAction?: ReactNode;
};

export function AgendaAppointmentCard({ appointment, variant, onSelect, style, arrivalAction }: Props) {
  const label = appointment.schedule_mode === "timed" && appointment.arrived_at && ["scheduled", "confirmed"].includes(appointment.status)
    ? appointment.has_clinical_history ? "En atención" : "Llegó · En espera"
    : appointmentStatusLabels[appointment.status];
  const phone = appointment.patient_phone?.trim() || "Sin teléfono";
  const timing = appointment.schedule_mode === "queue"
    ? variant === "day" ? "Cita por turno"
      : variant === "month" ? `Por turno · orden ${appointment.daily_booking_order ?? "—"}`
        : `Cita por turno · Orden de agenda ${appointment.daily_booking_order ?? "—"}`
    : formatTime(appointment.appointment_time);
  const statusClass = `agenda-appointment-card--${appointment.status}`;
  const select = (event?: MouseEvent<HTMLButtonElement>) => {
    if (variant === "month") event?.stopPropagation();
    onSelect(appointment);
  };
  if (variant === "week") {
    const card = <button type="button" className={`agenda-week-appointment-card ${statusClass}`} style={arrivalAction ? undefined : style} onClick={() => select()} aria-label={`Ver cita ${appointment.patient_name}, ${timing}, ${label}`}><time>{timing}</time><span className="agenda-week-appointment-summary"><strong>{appointment.patient_name}</strong><span className="agenda-patient-phone">{phone}</span><span>{appointment.reason || "Sin motivo registrado"}</span><span>{appointment.specialty_name}</span><span className="agenda-event-status">{label}</span></span></button>;
    return arrivalAction ? <div className="agenda-appointment-entry agenda-appointment-entry--week" style={style}>{card}<div className="agenda-inline-arrival">{arrivalAction}</div></div> : card;
  }
  if (variant === "month") return <button type="button" className={`agenda-month-entry ${statusClass}`} onClick={select} aria-label={`Ver cita de ${appointment.patient_name}, ${timing}`}><time>{timing}</time><strong>{appointment.patient_name}</strong><span className="agenda-patient-phone">{phone}</span><span className="agenda-event-status">{label}</span></button>;
  if (variant === "list") {
    const card = <button type="button" className={`agenda-day-list-item ${statusClass}`} onClick={() => select()}><time>{timing}</time><span><strong>{appointment.patient_name}</strong><span className="agenda-patient-phone">{phone}</span><span>{appointment.specialty_name}</span></span><span className="agenda-event-status">{label}</span></button>;
    return arrivalAction ? <div className="agenda-appointment-entry agenda-appointment-entry--list">{card}<div className="agenda-inline-arrival">{arrivalAction}</div></div> : card;
  }
  const card = <button type="button" className={`agenda-appointment-card agenda-appointment-card--${variant} ${statusClass}`} onClick={() => select()} aria-label={`Ver cita de ${appointment.patient_name}, ${timing}`}><time className="agenda-appointment-time">{timing}</time><span className="agenda-appointment-content"><strong>{appointment.patient_name}</strong><span className="agenda-patient-phone">{phone}</span><span>{appointment.reason || "Sin motivo registrado"}</span><span className="agenda-appointment-meta">{appointment.specialty_name}</span>{appointment.coverage_id && <span className="agenda-coverage">Cobertura</span>}</span><span className="agenda-event-status">{label}</span></button>;
  return arrivalAction ? <div className={`agenda-appointment-entry agenda-appointment-entry--${variant}`}>{card}<div className="agenda-inline-arrival">{arrivalAction}</div></div> : card;
}
