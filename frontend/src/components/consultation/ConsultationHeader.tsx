import type { Appointment } from "../../types/appointment";

type Props = { appointment: Appointment; specialtyName: string; onBack: () => void };

/** Presents the active appointment identity and the existing page-level back action. */
export default function ConsultationHeader({ appointment, specialtyName, onBack }: Props) {
  return <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver a la agenda</button><h2 className="mt-2 text-2xl font-bold">Consulta médica</h2><p className="mt-1 text-sm text-slate-500">La consulta queda vinculada automáticamente con la cita, médico, centro y especialidad.</p></div><div className="rounded-lg bg-teal-50 px-4 py-2 text-sm text-teal-900"><strong>Cita #{appointment.id}</strong><br />{appointment.appointment_date} · {appointment.appointment_time.slice(0, 5)}<br /><span className="font-semibold">{specialtyName}</span></div></div>;
}
