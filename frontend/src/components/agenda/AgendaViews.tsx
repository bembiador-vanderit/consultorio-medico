import { useEffect, useId, useState, type CSSProperties, type ReactNode } from "react";
import type { Appointment } from "../../types/appointment";
import { Card, EmptyState } from "../../ui";
import { AgendaAppointmentCard } from "./AgendaAppointmentCard";
import {
  addDays,
  appointmentStatusLabels,
  formatDate,
  formatTimelineHour,
  formatTime,
  sortByTime,
  startOfWeek,
  timeToMinutes,
  weekTimelineBounds,
} from "./agenda";

function NoAppointments({ description }: { description: string }) {
  return <div className="agenda-empty-state">
    <span className="agenda-empty-state-icon" aria-hidden="true"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13H4V6a1 1 0 0 1 1-1Z" /><path d="M8 13h3m-3 3h6" /></svg></span>
    <EmptyState title="No hay citas para esta fecha" description={description} />
  </div>;
}
export function AgendaDayView({
  appointments,
  date,
  onSelect,
  renderArrivalAction,
  ticketFor,
}: {
  appointments: Appointment[];
  date: string;
  onSelect: (appointment: Appointment) => void;
  renderArrivalAction?: (appointment: Appointment) => ReactNode;
  ticketFor?: (appointment: Appointment) => { public_code: string; status: string } | null;
}) {
  const headingId = useId();
  const timed = sortByTime(appointments.filter((item) => item.schedule_mode !== "queue"));
  const queued = [...appointments.filter((item) => item.schedule_mode === "queue")].sort((a, b) => (a.daily_booking_order ?? a.id) - (b.daily_booking_order ?? b.id));
  return (
    <section className="agenda-day" aria-labelledby={headingId}>
      <header className="agenda-view-heading">
        <div>
          <h3 id={headingId} className="atlas-section-title">
            {formatDate(date)}
          </h3>
          <p className="atlas-muted">Citas por hora y por turno, según la modalidad de cada jornada.</p>
        </div>
        <span className="atlas-help">{appointments.length} citas</span>
      </header>
      {timed.length > 0 && <div className="agenda-day-grid" role="grid" aria-label="Agenda diaria por hora">
        <span>Hora</span><span>Cita</span>
        {timed.length ? (
          timed.map((appointment) => (
            <div className="agenda-day-row" role="row" key={appointment.id}><time>{formatTime(appointment.appointment_time)}</time><AgendaAppointmentCard appointment={appointment} variant="day" onSelect={onSelect} arrivalAction={renderArrivalAction?.(appointment)} /></div>
          ))
        ) : (
          <NoAppointments description="No hay citas para esta fecha dentro de tu alcance." />
        )}
      </div>}
      {queued.length > 0 && <div className="agenda-queue-day" aria-label="Citas por turno">
        <h4 className="atlas-card-title">Por turno</h4>
        <div className="agenda-queue-table-head"><span>Orden de agenda</span><span>Paciente</span><span>Turno</span><span>Estado</span></div>
        {queued.map((appointment) => <div className="agenda-queue-table-row" key={appointment.id}>
          <span>{appointment.daily_booking_order ?? "—"}</span>
          <AgendaAppointmentCard appointment={appointment} variant="day" onSelect={onSelect} arrivalAction={renderArrivalAction?.(appointment)} />
          <span>{ticketFor?.(appointment)?.public_code ?? "—"}</span><span>{ticketFor?.(appointment)?.status === "waiting" ? "En espera" : appointmentStatusLabels[appointment.status]}</span>
        </div>)}
      </div>}
      {!appointments.length && <NoAppointments description="No hay citas para esta fecha dentro de tu alcance." />}
    </section>
  );
}
export function AgendaWeekView({
  appointments,
  date,
  onSelect,
  onSelectDay,
  renderArrivalAction,
}: {
  appointments: Appointment[];
  date: string;
  onSelect: (appointment: Appointment) => void;
  onSelectDay: (day: string) => void;
  renderArrivalAction?: (appointment: Appointment) => ReactNode;
}) {
  const start = startOfWeek(date);
  const [mobile, setMobile] = useState(() => !window.matchMedia("(min-width: 640px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 640px)");
    const change = () => setMobile(!media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const timeline = weekTimelineBounds(appointments.filter((item) => item.schedule_mode !== "queue"));
  const queued = appointments.filter((item) => item.schedule_mode === "queue");
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
      {mobile ? <div className="agenda-week-mobile">{days.filter((day) => appointments.some((item) => item.appointment_date === day)).map((day) => <AgendaDayView key={day} date={day} appointments={appointments.filter((item) => item.appointment_date === day)} onSelect={onSelect} renderArrivalAction={renderArrivalAction} />)}</div> : timeline ? <div className="agenda-week-grid" style={{ "--agenda-week-hours": String(timeline.hours) } as CSSProperties} role="grid" aria-label="Agenda semanal por hora">
        <span className="agenda-week-time-heading">Hora</span>
        {days.map((day) => <button key={day} type="button" className="agenda-week-day-heading" onClick={() => onSelectDay(day)} aria-label={`Ver citas de ${formatDate(day)}`}><span>{formatDate(day, { weekday: "short" })}</span><strong>{formatDate(day, { day: "numeric" })}</strong></button>)}
        {Array.from({ length: timeline.hours }, (_, index) => <time className="agenda-week-time-label" key={index} style={{ gridRow: index + 2 }}>{formatTimelineHour(timeline.startMinutes + index * 60)}</time>)}
        {days.map((day, dayIndex) => {
          const entries = sortByTime(appointments.filter((item) => item.appointment_date === day && item.schedule_mode !== "queue" && item.appointment_time !== null));
          const lanes = new Map<string, Appointment[]>();
          entries.forEach((item) => lanes.set(item.appointment_time!, [...(lanes.get(item.appointment_time!) ?? []), item]));
          return <div className="agenda-week-day" key={day} style={{ gridColumn: dayIndex + 2, gridRow: `2 / span ${timeline.hours}` }}>
            {entries.map((item) => {
              const sameTime = lanes.get(item.appointment_time!) ?? [item];
              const lane = sameTime.findIndex((entry) => entry.id === item.id);
              const position = ((timeToMinutes(item.appointment_time!) - timeline.startMinutes) / (timeline.endMinutes - timeline.startMinutes)) * 100;
              return <AgendaAppointmentCard key={item.id} appointment={item} variant="week" onSelect={onSelect} arrivalAction={renderArrivalAction?.(item)} style={{ top: `${position}%`, left: `calc(${(lane / sameTime.length) * 100}% + 2px)`, width: `calc(${100 / sameTime.length}% - 4px)` }} />;
            })}
          </div>;
        })}
      </div> : null}
      {!mobile && queued.length > 0 && <div className="agenda-week-queue" aria-label="Citas por turno de la semana">{days.map((day) => {
        const entries = queued.filter((item) => item.appointment_date === day).sort((a, b) => (a.daily_booking_order ?? a.id) - (b.daily_booking_order ?? b.id));
        return entries.length > 0 ? <div className="agenda-week-queue-day" key={day}><button type="button" onClick={() => onSelectDay(day)}>{formatDate(day, { weekday: "short", day: "numeric" })}: {entries.length} {entries.length === 1 ? "cita" : "citas"} por turno</button>
          {entries.map((item) => <AgendaAppointmentCard key={item.id} appointment={item} variant="week" onSelect={onSelect} arrivalAction={renderArrivalAction?.(item)} />)}</div> : null;
      })}</div>}
      {!appointments.length && <Card><NoAppointments description="No hay citas registradas en esta semana dentro de tu alcance." /></Card>}
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
                <AgendaAppointmentCard key={item.id} appointment={item} variant="doctor" onSelect={onSelect} />
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
