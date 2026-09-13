import type { CSSProperties } from "react";
import type { Appointment } from "../../types/appointment";
import { Card, EmptyState } from "../../ui";
import { AppointmentStatusBadge } from "./AppointmentStatusBadge";
import {
  addDays,
  formatDate,
  formatTimelineHour,
  formatTime,
  sortByTime,
  startOfWeek,
  timeToMinutes,
  weekTimelineBounds,
} from "./agenda";

function AppointmentCard({
  appointment,
  onSelect,
}: {
  appointment: Appointment;
  onSelect: (appointment: Appointment) => void;
}) {
  return (
    <button
      type="button"
      className="agenda-appointment-card"
      onClick={() => onSelect(appointment)}
      aria-label={`Ver cita de ${appointment.patient_name} a las ${formatTime(appointment.appointment_time)}`}
    >
      <time className="agenda-appointment-time">
        {formatTime(appointment.appointment_time)}
      </time>
      <span className="agenda-appointment-content">
        <strong>{appointment.patient_name}</strong>
        <span>{appointment.reason || "Sin motivo registrado"}</span>
        <span className="agenda-appointment-meta">
          {appointment.specialty_name} · {appointment.doctor_name}
          {appointment.center_name ? ` · ${appointment.center_name}` : ""}
        </span>
        {appointment.coverage_id && (
          <span className="agenda-coverage">
            Cobertura
            {appointment.original_doctor_name
              ? ` · original: ${appointment.original_doctor_name}`
              : ""}
          </span>
        )}
      </span>
      <AppointmentStatusBadge status={appointment.status} />
    </button>
  );
}
function NoAppointments({ description }: { description: string }) {
  return (
    <EmptyState
      title="No hay citas para esta fecha"
      description={description}
    />
  );
}
export function AgendaDayView({
  appointments,
  date,
  onSelect,
}: {
  appointments: Appointment[];
  date: string;
  onSelect: (appointment: Appointment) => void;
}) {
  return (
    <section aria-labelledby="agenda-day-heading">
      <header className="agenda-view-heading">
        <div>
          <h3 id="agenda-day-heading" className="atlas-section-title">
            {formatDate(date)}
          </h3>
          <p className="atlas-muted">Eventos ordenados por hora registrada.</p>
        </div>
        <span className="atlas-help">{appointments.length} citas</span>
      </header>
      <Card className="agenda-events">
        {appointments.length ? (
          sortByTime(appointments).map((appointment) => (
            <AppointmentCard
              key={appointment.id}
              appointment={appointment}
              onSelect={onSelect}
            />
          ))
        ) : (
          <NoAppointments description="No hay citas para esta fecha dentro de tu alcance." />
        )}
      </Card>
    </section>
  );
}
export function AgendaWeekView({
  appointments,
  date,
  onSelect,
  onSelectDay,
}: {
  appointments: Appointment[];
  date: string;
  onSelect: (appointment: Appointment) => void;
  onSelectDay: (day: string) => void;
}) {
  const start = startOfWeek(date);
  const timeline = weekTimelineBounds(appointments);
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index));
  return (
    <section className="agenda-week" aria-labelledby="agenda-week-heading">
      <header className="agenda-view-heading">
        <div>
          <h3 id="agenda-week-heading" className="atlas-section-title">
            Semana del {formatDate(start, { day: "numeric", month: "short" })}
          </h3>
          <p className="atlas-muted">Escala construida solo con horas registradas.</p>
        </div>
      </header>
      {!timeline ? <Card><NoAppointments description="No hay citas registradas en esta semana dentro de tu alcance." /></Card> : <div className="agenda-week-grid" style={{ "--agenda-week-hours": String(timeline.hours) } as CSSProperties} role="grid" aria-label="Agenda semanal por hora">
        <span className="agenda-week-time-heading">Hora</span>
        {days.map((day) => <button key={day} type="button" className="agenda-week-day-heading" onClick={() => onSelectDay(day)} aria-label={`Ver citas de ${formatDate(day)}`}><span>{formatDate(day, { weekday: "short" })}</span><strong>{formatDate(day, { day: "numeric" })}</strong></button>)}
        {Array.from({ length: timeline.hours }, (_, index) => <time className="agenda-week-time-label" key={index} style={{ gridRow: index + 2 }}>{formatTimelineHour(timeline.startMinutes + index * 60)}</time>)}
        {days.map((day, dayIndex) => {
          const entries = sortByTime(appointments.filter((item) => item.appointment_date === day));
          const lanes = new Map<string, Appointment[]>();
          entries.forEach((item) => lanes.set(item.appointment_time, [...(lanes.get(item.appointment_time) ?? []), item]));
          return <div className="agenda-week-day" key={day} style={{ gridColumn: dayIndex + 2, gridRow: `2 / span ${timeline.hours}` }}>
            {entries.map((item) => {
              const sameTime = lanes.get(item.appointment_time) ?? [item];
              const lane = sameTime.findIndex((entry) => entry.id === item.id);
              const position = ((timeToMinutes(item.appointment_time) - timeline.startMinutes) / (timeline.endMinutes - timeline.startMinutes)) * 100;
              return <button key={item.id} type="button" className={`agenda-week-appointment-card agenda-week-appointment-card--${item.status}`} style={{ top: `${position}%`, left: `calc(${(lane / sameTime.length) * 100}% + 2px)`, width: `calc(${100 / sameTime.length}% - 4px)` }} onClick={() => onSelect(item)} aria-label={`Ver cita ${item.patient_name}, ${formatTime(item.appointment_time)}, ${item.status}`}>
                <time>{formatTime(item.appointment_time)}</time><span className="agenda-week-appointment-summary"><strong>{item.patient_name}</strong><span>{item.reason || "Sin motivo registrado"}</span><span>{item.specialty_name}</span><span className="agenda-week-status">{item.status === "scheduled" ? "Programada" : item.status === "confirmed" ? "Confirmada" : item.status === "completed" ? "Completada" : item.status === "cancelled" ? "Cancelada" : "No asistió"}</span></span>
              </button>;
            })}
          </div>;
        })}
      </div>}
    </section>
  );
}
export function AgendaDoctorsView({
  appointments,
  onSelect,
}: {
  appointments: Appointment[];
  onSelect: (appointment: Appointment) => void;
}) {
  const groups = new Map<number, Appointment[]>();
  sortByTime(appointments).forEach((item) =>
    groups.set(item.doctor_id, [...(groups.get(item.doctor_id) ?? []), item]),
  );
  return (
    <section aria-labelledby="agenda-doctors-heading">
      <header className="agenda-view-heading">
        <div>
          <h3 id="agenda-doctors-heading" className="atlas-section-title">
            Citas por médico
          </h3>
          <p className="atlas-muted">
            Distribución de citas visibles; no representa disponibilidad.
          </p>
        </div>
      </header>
      {groups.size ? (
        <div className="agenda-doctors-grid">
          {[...groups].map(([doctor, entries]) => (
            <Card key={doctor} className="agenda-doctor-group">
              <h3 className="atlas-card-title">{entries[0].doctor_name}</h3>
              {entries.map((item) => (
                <AppointmentCard
                  key={item.id}
                  appointment={item}
                  onSelect={onSelect}
                />
              ))}
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <NoAppointments description="No hay citas dentro de los filtros seleccionados." />
        </Card>
      )}
    </section>
  );
}
