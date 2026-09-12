import type { Appointment } from "../../types/appointment";

export type AgendaView = "day" | "week" | "doctors";
export type AgendaFilters = { centerId: string; doctorId: string; specialtyId: string; status: string };

export const appointmentStatusLabels: Record<Appointment["status"], string> = {
  scheduled: "Programada", confirmed: "Confirmada", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió",
};
export const appointmentStatusTone: Record<Appointment["status"], "info" | "success" | "neutral" | "danger" | "warning"> = {
  scheduled: "info", confirmed: "success", completed: "neutral", cancelled: "danger", no_show: "warning",
};
export const weekDayLabels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export function isoDate(value: Date) { return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 10); }
export function parseDate(value: string) { return new Date(`${value}T12:00:00`); }
export function startOfWeek(value: string) { const date = parseDate(value); const shift = (date.getDay() + 6) % 7; date.setDate(date.getDate() - shift); return isoDate(date); }
export function addDays(value: string, days: number) { const date = parseDate(value); date.setDate(date.getDate() + days); return isoDate(date); }
export function rangeForView(date: string, view: AgendaView) { return view === "week" ? { start: startOfWeek(date), end: addDays(startOfWeek(date), 6) } : { start: date, end: date }; }
export function formatDate(value: string, options: Intl.DateTimeFormatOptions = { weekday: "long", day: "numeric", month: "long" }) { return new Intl.DateTimeFormat("es-DO", options).format(parseDate(value)); }
export function formatTime(value: string) { return value.slice(0, 5); }
export function sortByTime(items: Appointment[]) { return [...items].sort((a, b) => `${a.appointment_date}T${a.appointment_time}`.localeCompare(`${b.appointment_date}T${b.appointment_time}`) || a.id - b.id); }
export function filterAppointments(items: Appointment[], filters: AgendaFilters) { return sortByTime(items).filter((item) =>
  (!filters.centerId || String(item.center_id) === filters.centerId)
  && (!filters.doctorId || String(item.doctor_id) === filters.doctorId)
  && (!filters.specialtyId || String(item.specialty_id) === filters.specialtyId)
  && (!filters.status || item.status === filters.status),
); }