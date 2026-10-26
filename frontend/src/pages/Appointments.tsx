import { useEffect, useId, useMemo, useRef, useState } from "react";
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
import type {ClinicalFollowUp} from "../components/FollowUpInbox";
import { AppointmentContactPanel } from "../components/agenda/AppointmentContactPanel";
import { QueueArrivalPanel } from "../components/agenda/QueueArrivalPanel";
import { AppointmentArrivalAction } from "../components/agenda/AppointmentArrivalAction";
import type { ArrivalLookup } from "../components/agenda/queueArrival";
import type { QueueLine, QueueTicket } from "../types/queue";
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
  initialCreate?: boolean;
  initialFollowUp?: ClinicalFollowUp | null;
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
  initialCreate = false,
  initialFollowUp,
  canAccessClinical,
  onAttendAppointment,
}: Props) {
  const [view, setView] = useState<AgendaView>("day");
  const [followUpUsed,setFollowUpUsed]=useState(false);
  const [showContacts, setShowContacts] = useState(false);
  const [showArrivals, setShowArrivals] = useState(false);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const filtersId = useId();
  const arrivalsId = useId();
  const contactsId = useId();
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
    initialPatient || initialCreate ? "new" : null,
  );
  const [addendum, setAddendum] = useState<Appointment | null>(null);
  const [mutating, setMutating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const [arrivalLookupState, setArrivalLookupState] = useState<{ key: string; data: ArrivalLookup }>({
    key: "", data: { lines: [], tickets: [], loading: false, error: "" },
  });
  const generation = useRef(0);
  const range = rangeForView(date, view);
  const rangeKey = `${range.start}/${range.end}/${refresh}`;
  const today = isoDate(new Date());
  const ticketLookupDay = view === "day" ? date : today;
  const arrivalLookup = arrivalLookupState.key === rangeKey
    ? arrivalLookupState.data
    : { lines: [], tickets: [], loading: true, error: "" };

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
        setMonthDetail((current) => current ? (appointments.data.find((item) => item.id === current.id) ?? null) : null);
        setWeekDetail((current) => current ? (appointments.data.find((item) => item.id === current.id) ?? null) : null);
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
    if (!items.some((item) => item.schedule_mode === "queue" && item.appointment_date === ticketLookupDay && canAccessArrivalPair(item)) ||
      !user.is_active || !(user.roles.includes("secretary") || user.roles.includes("admin")) ||
      user.access_scope === "platform" || user.membership_state && user.membership_state !== "active" ||
      user.permissions && !user.permissions.includes("patients:access") ||
      user.denied_permissions?.includes("patients:access")) {
      setArrivalLookupState({ key: rangeKey, data: { lines: [], tickets: [], loading: false, error: "" } });
      return;
    }
    let active = true;
    setArrivalLookupState({ key: rangeKey, data: { lines: [], tickets: [], loading: true, error: "" } });
    void Promise.all([
      api.get<QueueLine[]>("/queue-lines", { params: { active_only: true } }),
      api.get<QueueTicket[]>("/queue-tickets", { params: { day: ticketLookupDay } }),
    ]).then(([lines, tickets]) => {
      if (active) setArrivalLookupState({ key: rangeKey, data: { lines: lines.data, tickets: tickets.data, loading: false, error: "" } });
    }).catch((reason) => {
      if (active) setArrivalLookupState({ key: rangeKey, data: { lines: [], tickets: [], loading: false, error: errorMessage(reason) } });
    });
    return () => { active = false; };
  }, [items, scope.centers, scope.doctors, rangeKey, ticketLookupDay, user.is_active, user.roles,
    user.access_scope, user.membership_state, user.permissions, user.denied_permissions]);
  useEffect(() => {
    if (initialPatient) setEditor("new");
  }, [initialPatient]);
  const visible = useMemo(
    () => filterAppointments(items, filters),
    [items, filters],
  );
  const pausePairs = useMemo(() => scope.doctors
    .filter((doctor) => !filters.doctorId || doctor.id === Number(filters.doctorId))
    .flatMap((doctor) => doctor.center_ids
      .filter((centerId) => !filters.centerId || centerId === Number(filters.centerId))
      .map((centerId) => ({ centerId, doctorId: doctor.id, doctorName: doctor.full_name }))),
  [scope.doctors, filters.centerId, filters.doctorId]);
  function canAccessArrivalPair(appointment: Appointment) {
    return appointment.center_id !== null &&
      scope.centers.some((center) => center.id === appointment.center_id) &&
      scope.doctors.some((doctor) => doctor.id === appointment.doctor_id &&
        doctor.center_ids.includes(appointment.center_id!));
  }
  function arrivalChanged() {
    setRefresh((current) => current + 1);
  }
  function renderArrivalAction(appointment: Appointment) {
    if (appointment.center_id === null ||
      appointment.appointment_date !== today || !["scheduled", "confirmed"].includes(appointment.status) ||
      !canAccessArrivalPair(appointment) || !(user.roles.includes("secretary") || user.roles.includes("admin"))) return null;
    return <AppointmentArrivalAction appointment={appointment} user={user} canAccessPair
      busy={mutating || loading || loadedKey !== rangeKey} onChanged={arrivalChanged}
      lookup={arrivalLookup} presentation="row" />;
  }
  function chooseDate(next: string) {
    setFiltersExpanded(false);
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
  const navigationDate = new Date(`${date}T00:00:00`);
  const navigationDateLabel = view === "month"
    ? new Intl.DateTimeFormat("es-DO", { month: "long", year: "numeric" }).format(navigationDate)
    : new Intl.DateTimeFormat("es-DO", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(navigationDate);
  const panelDay = view === "month" ? monthDay : view === "week" ? weekDay : view === "doctors" ? directDay : null;
  const panelDetail = view === "month" ? monthDetail : view === "week" ? weekDetail : view === "doctors" ? directDetail : null;
  const panelShowBack = view === "month" || (view === "week" && weekFromList);
  return (
    <div className={`atlas-page agenda-page${showContacts || showArrivals ? " agenda-page--operational-expanded" : ""}`}>
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
      <div className="agenda-controls-stack" aria-label="Navegación y controles de Agenda" data-atlas-block-id="agenda.controls">
      <div className="agenda-date-navigation" role="group" aria-label="Navegación de fechas" data-atlas-block-id="agenda.date-navigation">
          <Button
            variant="outline"
            aria-label="Fecha anterior"
            onClick={() => chooseDate(view === "month" ? addMonths(date, -1) : addDays(date, view === "week" ? -7 : -1))}
          >‹</Button>
          <div className="agenda-date-context"><strong>{activeLabel}</strong><span>{navigationDateLabel}</span></div>
          <Button
            variant="outline"
            aria-label="Fecha siguiente"
            onClick={() => chooseDate(view === "month" ? addMonths(date, 1) : addDays(date, view === "week" ? 7 : 1))}
          >›</Button>
      </div>
      <div className="agenda-view-controls" aria-label="Controles de vista de Agenda" data-atlas-block-id="agenda.view-controls">
        <div className="agenda-today-action">
          <Button
            variant="outline"
            aria-label="Ir a hoy"
            onClick={() => chooseDate(isoDate(new Date()))}
          >
            Hoy
          </Button>
        </div>
        <div
          className="agenda-view-switch"
          role="group"
          aria-label="Modo de visualización de Agenda"
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
              aria-current={view === id ? "true" : undefined}
              onClick={() => chooseView(id)}
            >
              {label}
            </Button>
          ))}
        </div>
        <Button className="agenda-mobile-filter-toggle" variant="outline" aria-expanded={filtersExpanded} aria-controls={filtersId} onClick={() => setFiltersExpanded((current) => !current)}>Calendario y filtros</Button>
      </div>
      {error && <Alert tone="danger" title="Agenda no disponible">{error}</Alert>}
      </div>
      <div className="agenda-operational-panels" aria-label="Paneles operativos de Agenda">
        <section className={`agenda-contacts-block${showContacts ? " is-expanded" : ""}`} aria-label="Contactos previos" data-atlas-block-id="agenda.contacts">
          <button className="agenda-operational-toggle agenda-operational-toggle--contacts" type="button" aria-expanded={showContacts} aria-controls={contactsId} onClick={() => setShowContacts((value) => !value)}>
            <span className="agenda-operational-toggle-icon" aria-hidden="true">↗</span><span className="agenda-operational-toggle-copy"><strong>Contactos previos</strong><small>Seguimiento de intentos de contacto</small></span><span className="agenda-operational-chevron" aria-hidden="true" />
          </button>
          <div id={contactsId} className="agenda-operational-panel" hidden={!showContacts}>
            {showContacts && <AppointmentContactPanel initialDate={addDays(date, 1)} centerId={filters.centerId ? Number(filters.centerId) : undefined} doctorId={filters.doctorId ? Number(filters.doctorId) : undefined} canRecord={user.roles.includes("secretary") || user.roles.includes("admin")} />}
          </div>
        </section>
        {(user.roles.includes("secretary") || user.roles.includes("admin") || user.roles.includes("doctor")) && <section className={`agenda-arrivals-block${showArrivals ? " is-expanded" : ""}`} aria-label="Bloque de llegadas y turnos" data-atlas-block-id="agenda.arrivals">
          <button className="agenda-operational-toggle agenda-operational-toggle--arrivals" type="button" aria-expanded={showArrivals} aria-controls={arrivalsId} onClick={() => setShowArrivals((value) => !value)}>
            <span className="agenda-operational-toggle-icon" aria-hidden="true">◷</span><span className="agenda-operational-toggle-copy"><strong>Llegadas y turnos</strong><small>Operación de sala, pausas y llamado de pacientes</small></span><span className="agenda-operational-chevron" aria-hidden="true" />
          </button>
          <div id={arrivalsId} className="agenda-operational-panel agenda-arrivals-content" hidden={!showArrivals}>
            {showArrivals && <QueueArrivalPanel initialDate={date} centerId={filters.centerId ? Number(filters.centerId) : undefined} doctorId={filters.doctorId ? Number(filters.doctorId) : undefined} canRecord={user.roles.includes("secretary") || user.roles.includes("admin")} canOperate={user.roles.includes("secretary") || user.roles.includes("admin") || user.roles.includes("doctor")} canStart={user.roles.includes("doctor") || user.roles.includes("admin")} canComplete={canAccessClinical} currentUserId={user.id} showPauses={import.meta.env.VITE_PROVIDER_PAUSES_ENABLED === "true"} canManagePauses={user.roles.includes("admin") || (user.roles.includes("doctor") && canAccessClinical)} pauseAdmin={user.roles.includes("admin")} pausePairs={pausePairs} showCallPolicy={import.meta.env.VITE_QUEUE_CALL_POLICY_ENABLED === "true"} showWaitingRooms={import.meta.env.VITE_WAITING_ROOMS_ENABLED === "true"} refreshKey={refresh} />}
          </div>
        </section>}
      </div>
      <div className={`agenda-layout${view === "month" ? " agenda-layout--month" : view === "week" ? " agenda-layout--week" : view === "day" ? " agenda-layout--day" : " agenda-layout--doctors"}${panelDay ? " agenda-layout--panel" : ""}`}>
        <aside id={filtersId} className={`agenda-sidebar${!filtersExpanded ? " agenda-sidebar--collapsed" : ""}`} data-atlas-block-id="agenda.sidebar">
          <div className="agenda-personalizable-block" id="agenda.calendar" data-atlas-block-id="agenda.calendar"><AgendaMiniCalendar selectedDate={date} onSelect={chooseDate} /></div>
          <div className="agenda-personalizable-block" id="agenda.filters" data-atlas-block-id="agenda.filters"><AgendaFiltersPanel
            filters={filters}
            centers={scope.centers}
            doctors={scope.doctors}
            onChange={(next) => setFilters(reconcileFilters(next, scope))}
            onClear={() => setFilters(emptyFilters)}
          /></div>
          <div className="agenda-personalizable-block" id="agenda.legend" data-atlas-block-id="agenda.legend"><AgendaStatusLegend /></div>
        </aside>
        <section className="agenda-schedule" aria-label="Citas del período seleccionado" aria-live="polite" data-atlas-block-id="agenda.schedule">
          {loading || loadedKey !== rangeKey ? (
            <Card>
              <LoadingState label="Cargando citas del período seleccionado…" />
            </Card>
          ) : view === "day" ? (
            <AgendaDayView
              appointments={visible}
              date={date}
              onSelect={selectAppointment}
              renderArrivalAction={renderArrivalAction}
              ticketFor={(appointment) => arrivalLookup.tickets.find((ticket) => ticket.appointment_id === appointment.id) ?? null}
            />
          ) : view === "week" ? (
            <AgendaWeekView
              appointments={visible}
              date={date}
              onSelect={(item) => { setWeekDay(item.appointment_date); setWeekDetail(item); setWeekFromList(false); }}
              onSelectDay={(day) => { setWeekDay(day); setWeekDetail(null); setWeekFromList(true); }}
              renderArrivalAction={renderArrivalAction}
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
        {panelDay && <AgendaMonthPanel day={panelDay} appointments={visible.filter((item) => item.appointment_date === panelDay)} detail={panelDetail} showBack={panelShowBack} user={user} canAccessClinical={canAccessClinical} busy={mutating || loading || loadedKey !== rangeKey} error={actionError} canAccessArrivalPair={panelDetail ? canAccessArrivalPair(panelDetail) : false} onArrivalChanged={arrivalChanged} renderArrivalAction={renderArrivalAction} onClose={() => { if (!mutating) { setMonthDay(null); setMonthDetail(null); setWeekDay(null); setWeekDetail(null); setWeekFromList(false); setDirectDay(null); setDirectDetail(null); } }} onBack={() => { setMonthDetail(null); setWeekDetail(null); }} onSelect={(item) => { if (view === "week") setWeekDetail(item); else if (view === "month") setMonthDetail(item); else setDirectDetail(item); }} onEdit={(item) => { setMonthDetail(null); setWeekDetail(null); setEditor(item); }} onAttend={onAttendAppointment} onSetStatus={(item, status) => void updateStatus(item, status)} onDelete={(item) => void remove(item)} onAddAddendum={(item) => { setMonthDetail(null); setWeekDetail(null); setDirectDetail(null); setAddendum(item); }} />}
      </div>
      <AppointmentDrawer
        appointment={directDetail}
        open={view === "day" && Boolean(directDetail)}
        user={user}
        canAccessClinical={canAccessClinical}
        canAccessArrivalPair={directDetail ? canAccessArrivalPair(directDetail) : false}
        onArrivalChanged={arrivalChanged}
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
          initialFollowUp={editor === "new" && !followUpUsed ? initialFollowUp : null}
          appointment={editor === "new" ? null : editor}
          initialPatient={editor === "new" ? initialPatient : null}
          date={date}
          centers={scope.centers}
          user={user}
          onClose={() => setEditor(null)}
          onSaved={(item)=>{setFollowUpUsed(true);handleSaved(item);}}
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
