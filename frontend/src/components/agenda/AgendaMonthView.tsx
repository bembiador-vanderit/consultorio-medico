import type { Appointment } from "../../types/appointment";
import { AppointmentStatusBadge } from "./AppointmentStatusBadge";
import { addDays, formatDate, formatTime, isoDate, parseDate, sortByTime } from "./agenda";

type Props = {
  appointments: Appointment[];
  date: string;
  selectedDay: string | null;
  onSelectDay: (day: string) => void;
  onSelectAppointment: (appointment: Appointment) => void;
};

export function AgendaMonthView({ appointments, date, selectedDay, onSelectDay, onSelectAppointment }: Props) {
  const selected = parseDate(date);
  const first = new Date(selected.getFullYear(), selected.getMonth(), 1);
  const start = addDays(isoDate(first), -((first.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => addDays(start, index));
  const month = selected.getMonth();
  return <section className="agenda-month" aria-labelledby="agenda-month-heading">
    <header className="agenda-view-heading"><div><h3 id="agenda-month-heading" className="atlas-section-title">{formatDate(date, { month: "long", year: "numeric" })}</h3><p className="atlas-muted">Citas autorizadas por día. Seleccione un día para ver la lista completa.</p></div></header>
    <div className="agenda-month-grid" role="grid" aria-label="Calendario mensual">{["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"].map((label) => <span className="agenda-month-weekday" key={label}>{label}</span>)}
      {days.map((day) => {
        const inMonth = parseDate(day).getMonth() === month;
        const entries = sortByTime(appointments.filter((item) => item.appointment_date === day));
        return <div key={day} role="gridcell" tabIndex={inMonth ? 0 : -1} aria-selected={selectedDay === day} className={`agenda-month-day${inMonth ? "" : " agenda-month-day--outside"}${selectedDay === day ? " agenda-month-day--selected" : ""}`} onClick={() => inMonth && onSelectDay(day)} onKeyDown={(event) => { if (inMonth && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelectDay(day); } }}>
          <span className="agenda-month-date">{parseDate(day).getDate()}</span>
          <div className="agenda-month-entries">{entries.slice(0, 3).map((item) => <button key={item.id} type="button" className="agenda-month-entry" onClick={(event) => { event.stopPropagation(); onSelectAppointment(item); }} aria-label={`Ver cita de ${item.patient_name} a las ${formatTime(item.appointment_time)}`}><time>{formatTime(item.appointment_time)}</time><span>{item.patient_name}</span><AppointmentStatusBadge status={item.status} /></button>)}</div>
          {entries.length > 3 && <button type="button" className="agenda-month-more" onClick={(event) => { event.stopPropagation(); onSelectDay(day); }}>+{entries.length - 3} más</button>}
        </div>;
      })}
    </div>
  </section>;
}
