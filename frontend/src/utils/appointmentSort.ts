import type { Appointment } from "../types/appointment";

export type AppointmentSortKey = "dateTime" | "patient" | "doctor" | "center" | "status";
export type SortDirection = "asc" | "desc";

const collator = new Intl.Collator("es", { numeric: true, sensitivity: "base" });

function sortValue(appointment: Appointment, key: AppointmentSortKey, statusLabels: Record<string, string>) {
  if (key === "dateTime") return `${appointment.appointment_date}T${appointment.appointment_time}`;
  if (key === "patient") return appointment.patient_name;
  if (key === "doctor") return appointment.doctor_name;
  if (key === "center") return `${appointment.center_name ?? ""} ${appointment.center_city ?? ""}`;
  return statusLabels[appointment.status] ?? appointment.status;
}

export function sortAppointments(
  appointments: Appointment[],
  key: AppointmentSortKey,
  direction: SortDirection,
  statusLabels: Record<string, string>,
) {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...appointments].sort((left, right) => {
    const comparison = collator.compare(sortValue(left, key, statusLabels), sortValue(right, key, statusLabels));
    return comparison !== 0 ? comparison * multiplier : (left.id - right.id) * multiplier;
  });
}
