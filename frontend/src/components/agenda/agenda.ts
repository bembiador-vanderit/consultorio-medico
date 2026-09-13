import type { Appointment } from "../../types/appointment";
import type { User } from "../../types/user";

export type AgendaView = "day" | "week" | "doctors";
export type AgendaFilters = {
  centerId: string;
  doctorId: string;
  specialtyId: string;
  status: string;
};
export type AgendaCenter = { id: number; name: string; city?: string | null };
export type AgendaDoctor = {
  id: number;
  full_name: string;
  center_ids: number[];
  specialties: { id: number; name: string }[];
};
export type AgendaScope = { centers: AgendaCenter[]; doctors: AgendaDoctor[] };

export function filterOptions(filters: AgendaFilters, doctors: AgendaDoctor[]) {
  const visibleDoctors = doctors.filter(
    (doctor) =>
      !filters.centerId || doctor.center_ids.includes(Number(filters.centerId)),
  );
  const specialtyDoctors = visibleDoctors.filter(
    (doctor) => !filters.doctorId || String(doctor.id) === filters.doctorId,
  );
  const specialties = Array.from(
    new Map(
      specialtyDoctors
        .flatMap((doctor) => doctor.specialties)
        .map((item) => [item.id, item]),
    ).values(),
  );
  return { visibleDoctors, specialties };
}
export function reconcileFilters(
  filters: AgendaFilters,
  scope: AgendaScope,
): AgendaFilters {
  const next = { ...filters };
  if (
    next.centerId &&
    !scope.centers.some((item) => String(item.id) === next.centerId)
  )
    next.centerId = "";
  if (
    !filterOptions(next, scope.doctors).visibleDoctors.some(
      (item) => String(item.id) === next.doctorId,
    )
  )
    next.doctorId = "";
  if (
    !filterOptions(next, scope.doctors).specialties.some(
      (item) => String(item.id) === next.specialtyId,
    )
  )
    next.specialtyId = "";
  return next;
}
export function appointmentRules(appointment: Appointment | null, user: User) {
  const completed = Boolean(
    appointment &&
      (appointment.status === "completed" ||
        appointment.clinical_history_status === "completed"),
  );
  const history = Boolean(appointment?.has_clinical_history);
  const coverage = Boolean(appointment?.coverage_id);
  const pureDoctor =
    user.roles.includes("doctor") &&
    !user.roles.includes("admin") &&
    !user.roles.includes("secretary");
  const active =
    appointment?.status === "scheduled" || appointment?.status === "confirmed";
  return {
    completed,
    identityLocked: Boolean(
      appointment && (completed || history || coverage || pureDoctor),
    ),
    specialtyLocked: completed || history || coverage,
    scheduleLocked:
      completed ||
      history ||
      (coverage &&
        (!user.roles.includes("secretary") || user.roles.includes("admin"))),
    canCancel: active && !history,
    canAttend: Boolean(
      active &&
        user.is_active &&
        user.roles.includes("doctor") &&
        appointment?.doctor_id === user.id,
    ),
    canDelete: Boolean(appointment && !completed && !history && !coverage),
    canAddAddendum: Boolean(
      completed &&
        appointment?.clinical_history_id &&
        appointment.clinical_history_doctor_id === user.id &&
        user.is_active &&
        user.roles.includes("doctor"),
    ),
  };
}

export const appointmentStatusLabels: Record<Appointment["status"], string> = {
  scheduled: "Programada",
  confirmed: "Confirmada",
  completed: "Completada",
  cancelled: "Cancelada",
  no_show: "No asistió",
};
export const appointmentStatusTone: Record<
  Appointment["status"],
  "info" | "success" | "neutral" | "danger" | "warning"
> = {
  scheduled: "info",
  confirmed: "success",
  completed: "neutral",
  cancelled: "danger",
  no_show: "warning",
};
export const weekDayLabels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export function isoDate(value: Date) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 10);
}
export function parseDate(value: string) {
  return new Date(`${value}T12:00:00`);
}
export function startOfWeek(value: string) {
  const date = parseDate(value);
  const shift = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - shift);
  return isoDate(date);
}
export function addDays(value: string, days: number) {
  const date = parseDate(value);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}
export function rangeForView(date: string, view: AgendaView) {
  return view === "week"
    ? { start: startOfWeek(date), end: addDays(startOfWeek(date), 6) }
    : { start: date, end: date };
}
export function formatDate(
  value: string,
  options: Intl.DateTimeFormatOptions = {
    weekday: "long",
    day: "numeric",
    month: "long",
  },
) {
  return new Intl.DateTimeFormat("es-DO", options).format(parseDate(value));
}
export function formatTime(value: string) {
  return value.slice(0, 5);
}
export function sortByTime(items: Appointment[]) {
  return [...items].sort(
    (a, b) =>
      `${a.appointment_date}T${a.appointment_time}`.localeCompare(
        `${b.appointment_date}T${b.appointment_time}`,
      ) || a.id - b.id,
  );
}
export function filterAppointments(
  items: Appointment[],
  filters: AgendaFilters,
) {
  return sortByTime(items).filter(
    (item) =>
      (!filters.centerId || String(item.center_id) === filters.centerId) &&
      (!filters.doctorId || String(item.doctor_id) === filters.doctorId) &&
      (!filters.specialtyId ||
        String(item.specialty_id) === filters.specialtyId) &&
      (!filters.status || item.status === filters.status),
  );
}
