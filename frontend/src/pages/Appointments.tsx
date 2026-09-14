import { useEffect, useMemo, useRef, useState } from "react";
import type { Appointment } from "../types/appointment";
import type { Patient } from "../types/patient";
import type { User } from "../types/user";
import { Alert, Button, Card, LoadingState, PageHeader } from "../ui";
import { api } from "../services/api";
import { announceNotificationsChanged } from "../services/notificationEvents";
import ClinicalHistoryPanel from "../components/patients/ClinicalHistoryPanel";
import { AgendaFiltersPanel, AgendaStatusLegend } from "../components/agenda/AgendaFiltersPanel";
import { AgendaMiniCalendar } from "../components/agenda/AgendaMiniCalendar";
import { AgendaMonthPanel } from "../components/agenda/AgendaMonthPanel";
import { AgendaMonthView } from "../components/agenda/AgendaMonthView";
import {
  AgendaDayView,
  AgendaDoctorsView,
  AgendaWeekView,
} from "../components/agenda/AgendaViews";
import { AppointmentDrawer } from "../components/agenda/AppointmentDrawer";
import { AppointmentForm } from "../components/agenda/AppointmentForm";
import {
  addDays,
  addMonths,
  appointmentRules,
  filterAppointments,
  isoDate,
  rangeForView,
  reconcileFilters,
  type AgendaFilters,
  type AgendaScope,
  type AgendaView,
} from "../components/agenda/agenda";

type Props = {
  user: User;
  onBack: () => void;
  initialPatient?: Patient | null;
  canAccessClinical: boolean;
  onAttendAppointment: (appointment: Appointment) => void;
};
const emptyFilters: AgendaFilters = {
  centerId: "",
  doctorId: "",
  specialtyId: "",
  status: "",
};
function errorMessage(reason: any) {
  return typeof reason?.response?.data?.detail === "string"
    ? reason.response.data.detail
    : "No fue posible realizar la operación. Inténtelo de nuevo.";
}
function asInput(appointment: Appointment, status: Appointment["status"]) {
  return {
    patient_id: appointment.patient_id,
    doctor_id: appointment.doctor_id,
    center_id: appointment.center_id,
    specialty_id: appointment.specialty_id,
    appointment_date: appointment.appointment_date,
    appointment_time: appointment.appointment_time,
    reason: appointment.reason,
    status,
    notes: appointment.notes,
  };
}
export default function Appointments({
  user,
  onBack,
  initialPatient,
  canAccessClinical,
  onAttendAppointment,
}: Props) {
  const [view, setView] = useState<AgendaView>("day");
  const [date, setDate] = useState(isoDate(new Date()));
  const [items, setItems] = useState<Appointment[]>([]);
  const [scope, setScope] = useState<AgendaScope>({ centers: [], doctors: [] });
  const [filters, setFilters] = useState(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [directDay, setDirectDay] = useState<string | null>(null);
  const [directDetail, setDirectDetail] = useState<Appointment | null>(null);
  const [monthDay, setMonthDay] = useState<string | null>(null);
  const [monthDetail, setMonthDetail] = useState<Appointment | null>(null);
  const [weekDay, setWeekDay] = useState<string | null>(null);
  const [weekDetail, setWeekDetail] = useState<Appointment | null>(null);
  const [weekFromList, setWeekFromList] = useState(false);
  const [editor, setEditor] = useState<Appointment | null | "new">(
    initialPatient ? "new" : null,
  );
  const [addendum, setAddendum] = useState<Appointment | null>(null);
  const [mutating, setMutating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const generation = useRef(0);
  const range = rangeForView(date, view);
  const rangeKey = `${range.start}/${range.end}/${refresh}`;

  useEffect(() => {
    const request = ++generation.current;
    setLoading(true);
    setError("");
    setItems([]);
    void Promise.all([
      api.get<Appointment[]>("/appointments", {
        params: { start: range.start, end: range.end },
      }),
      api.get<AgendaScope>("/appointments/scope-options"),
    ])
      .then(([appointments, options]) => {
        if (request !== generation.current) return;
        setItems(appointments.data);
        setScope(options.data);
        setFilters((current) => reconcileFilters(current, options.data));
        setDirectDetail((current) => current ? (appointments.data.find((item) => item.id === current.id) ?? null) : null);
      })
      .catch((reason) => {
        if (request !== generation.current) return;
        setItems([]);
        setDirectDay(null);
        setDirectDetail(null);
        setError(errorMessage(reason));
      })
      .finally(() => {
        if (request === generation.current) {
          setLoading(false);
          setLoadedKey(rangeKey);
        }
      });
    return () => {
      generation.current += 1;
    };
  }, [range.start, range.end, refresh]);
  useEffect(() => {
    if (initialPatient) setEditor("new");
  }, [initialPatient]);
  const visible = useMemo(
    () => filterAppointments(items, filters),
    [items, filters],
  );
  function chooseDate(next: string) {
    setDirectDay(null);
    setDirectDetail(null);
    setMonthDay(null);
    setMonthDetail(null);
    setWeekDay(null);
    setWeekDetail(null);
    setWeekFromList(false);
    setActionError("");
    setDate(next);
  }
  function chooseView(next: AgendaView) {
    setDirectDay(null);
    setDirectDetail(null);
    setMonthDay(null);
    setMonthDetail(null);
    setWeekDay(null);
    setWeekDetail(null);
    setWeekFromList(false);
    setActionError("");
    setView(next);
  }
  function selectAppointment(item: Appointment) {
    setActionError("");
    setDirectDay(item.appointment_date);
    setDirectDetail(item);
  }
  async function updateStatus(
    appointment: Appointment,
    status: Appointment["status"],
  ) {
    if (mutating || loading || loadedKey !== rangeKey) return;
    setMutating(true);
    setActionError("");
    // Invalidate a refresh already in flight so it cannot overwrite this mutation.
    generation.current += 1;
    try {
      const { data } = await api.put<Appointment>(
        `/appointments/${appointment.id}`,
        asInput(appointment, status),
      );
      announceNotificationsChanged();
      setItems((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      );
      setDirectDetail(data);
      setMonthDetail(data);
      setWeekDetail(data);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setMutating(false);
    }
  }
  function handleSaved(saved: Appointment) {
    generation.current += 1;
    setEditor(null);
    setActionError("");
    announceNotificationsChanged();
    setDate(saved.appointment_date);
    if (view === "month") { setMonthDay(saved.appointment_date); setMonthDetail(saved); }
    else if (view === "week") { setWeekDay(saved.appointment_date); setWeekDetail(saved); setWeekFromList(false); }
    else { setDirectDay(saved.appointment_date); setDirectDetail(saved); }
    setRefresh((current) => current + 1);
  }
  async function remove(appointment: Appointment) {
    if (
      mutating ||
      loading ||
      loadedKey !== rangeKey ||
      !appointmentRules(appointment, user).canDelete ||
      !window.confirm("¿Eliminar esta cita?")
    )
      return;
    setMutating(true);
    setActionError("");
    generation.current += 1;
    try {
      await api.delete(`/appointments/${appointment.id}`);
      setItems((current) =>
        current.filter((item) => item.id !== appointment.id),
      );
      setDirectDay(null);
      setDirectDetail(null);
      setMonthDetail(null);
      setWeekDetail(null);
      announceNotificationsChanged();
      setRefresh((current) => current + 1);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setMutating(false);
    }
  }
  const activeLabel =
    view === "day" ? "Día" : view === "week" ? "Semana" : view === "month" ? "Mes" : "Médicos";
  const panelDay = view === "month" ? monthDay : view === "week" ? weekDay : view === "doctors" ? directDay : null;
  const panelDetail = view === "month" ? monthDetail : view === "week" ? weekDetail : view === "doctors" ? directDetail : null;
  const panelShowBack = view === "month" || (view === "week" && weekFromList);
  return (
    <div className="atlas-page agenda-page">
      <PageHeader
        title="Agenda"
        description="Citas con datos reales dentro de su alcance."
        actions={
          <div className="atlas-actions">
            <Button variant="outline" onClick={onBack}>
              Volver al dashboard
            </Button>
            <Button onClick={() => setEditor("new")}>+ Nueva cita</Button>
          </div>
        }
      />
      <div className="agenda-toolbar">
        <div className="atlas-actions">
          <Button
            variant="outline"
            onClick={() => chooseDate(isoDate(new Date()))}
          >
            Hoy
          </Button>
          <Button
            variant="outline"
            aria-label="Fecha anterior"
            onClick={() => chooseDate(view === "month" ? addMonths(date, -1) : addDays(date, view === "week" ? -7 : -1))}
          >
            ‹
          </Button>
          <strong>{activeLabel}</strong>
          <Button
            variant="outline"
            aria-label="Fecha siguiente"
            onClick={() => chooseDate(view === "month" ? addMonths(date, 1) : addDays(date, view === "week" ? 7 : 1))}
          >
            ›
          </Button>
        </div>
        <div
          className="atlas-actions"
          role="group"
          aria-label="Vista de Agenda"
        >
          {(
            [
              ["day", "Día"],
              ["week", "Semana"],
              ["month", "Mes"],
              ["doctors", "Médicos"],
            ] as const
          ).map(([id, label]) => (
            <Button
              key={id}
              variant={view === id ? "primary" : "outline"}
              aria-pressed={view === id}
              onClick={() => chooseView(id)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      {error && (
        <Alert tone="danger" title="Agenda no disponible">
          {error}
        </Alert>
      )}
      <div className={`agenda-layout${view === "month" ? " agenda-layout--month" : view === "week" ? " agenda-layout--week" : view === "day" ? " agenda-layout--day" : " agenda-layout--doctors"}${panelDay ? " agenda-layout--panel" : ""}`}>
        <aside className="agenda-sidebar">
          <AgendaMiniCalendar selectedDate={date} onSelect={chooseDate} />
          <AgendaFiltersPanel
            filters={filters}
            centers={scope.centers}
            doctors={scope.doctors}
            onChange={(next) => setFilters(reconcileFilters(next, scope))}
            onClear={() => setFilters(emptyFilters)}
          />
          <AgendaStatusLegend />
        </aside>
        <section aria-label="Citas del período seleccionado" aria-live="polite">
          {loading || loadedKey !== rangeKey ? (
            <Card>
              <LoadingState label="Cargando citas del período seleccionado…" />
            </Card>
          ) : view === "day" ? (
            <AgendaDayView
              appointments={visible}
              date={date}
              onSelect={selectAppointment}
            />
          ) : view === "week" ? (
            <AgendaWeekView
              appointments={visible}
              date={date}
              onSelect={(item) => { setWeekDay(item.appointment_date); setWeekDetail(item); setWeekFromList(false); }}
              onSelectDay={(day) => { setWeekDay(day); setWeekDetail(null); setWeekFromList(true); }}
            />
          ) : view === "month" ? (
            <AgendaMonthView appointments={visible} date={date} selectedDay={monthDay} onSelectDay={(day) => { setMonthDay(day); setMonthDetail(null); }} onSelectAppointment={(item) => { setMonthDay(item.appointment_date); setMonthDetail(item); }} />
          ) : (
            <AgendaDoctorsView
              appointments={visible}
              onSelect={selectAppointment}
            />
          )}
        </section>
        {panelDay && <AgendaMonthPanel day={panelDay} appointments={visible.filter((item) => item.appointment_date === panelDay)} detail={panelDetail} showBack={panelShowBack} user={user} canAccessClinical={canAccessClinical} busy={mutating || loading || loadedKey !== rangeKey} error={actionError} onClose={() => { if (!mutating) { setMonthDay(null); setMonthDetail(null); setWeekDay(null); setWeekDetail(null); setWeekFromList(false); setDirectDay(null); setDirectDetail(null); } }} onBack={() => { setMonthDetail(null); setWeekDetail(null); }} onSelect={(item) => { if (view === "week") setWeekDetail(item); else if (view === "month") setMonthDetail(item); else setDirectDetail(item); }} onEdit={(item) => { setMonthDetail(null); setWeekDetail(null); setDirectDetail(null); setEditor(item); }} onAttend={onAttendAppointment} onSetStatus={(item, status) => void updateStatus(item, status)} onDelete={(item) => void remove(item)} onAddAddendum={(item) => { setMonthDetail(null); setWeekDetail(null); setDirectDetail(null); setAddendum(item); }} />}
      </div>
      <AppointmentDrawer
        appointment={directDetail}
        open={view === "day" && Boolean(directDetail)}
        user={user}
        canAccessClinical={canAccessClinical}
        onClose={() => { if (!mutating) { setActionError(""); setDirectDay(null); setDirectDetail(null); } }}
        onEdit={(item) => { setDirectDetail(null); setEditor(item); }}
        onAttend={onAttendAppointment}
        onSetStatus={(item, status) => void updateStatus(item, status)}
        onDelete={(item) => void remove(item)}
        onAddAddendum={(item) => { setDirectDetail(null); setAddendum(item); }}
        busy={mutating || loading || loadedKey !== rangeKey}
        error={actionError}
      />
      {editor !== null && (
        <AppointmentForm
          appointment={editor === "new" ? null : editor}
          initialPatient={editor === "new" ? initialPatient : null}
          date={date}
          centers={scope.centers}
          user={user}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
      {addendum && (
        <ClinicalHistoryPanel
          patientId={addendum.patient_id}
          patientName={addendum.patient_name}
          user={user}
          initialAddendumHistoryId={addendum.clinical_history_id}
          onClose={() => setAddendum(null)}
        />
      )}
    </div>
  );
}
