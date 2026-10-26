import { useEffect, useId, useRef, useState } from "react";
import type { Appointment, AppointmentInput } from "../../types/appointment";
import type { Patient } from "../../types/patient";
import type { User } from "../../types/user";
import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  RequiredFieldsLegend,
  Select,
  Textarea,
} from "../../ui";
import { api } from "../../services/api";
import PatientForm from "../patients/PatientForm";
import type {ClinicalFollowUp} from "../FollowUpInbox";

import { appointmentRules, appointmentStatusLabels } from "./agenda";
type Center = { id: number; name: string; city?: string | null };
type Doctor = {
  id: number;
  full_name: string;
  center_ids: number[];
  specialties: { id: number; name: string }[];
};
type Identity = {
  id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone_masked: string | null;
  email_masked: string | null;
  selection_token?: string;
};
type Mode = "timed" | "queue";
type ModeOptions = {
  schedule_mode: Mode;
  allowed_timed?: boolean;
  allowed_queue?: boolean;
  default_mode?: Mode;
  queue_line_available?: boolean;
  multimode_enabled?: boolean;
};
const blank = (date: string, patient?: Patient | null): AppointmentInput => ({
  patient_id: patient?.id ?? 0,
  doctor_id: null,
  center_id: null,
  specialty_id: null,
  appointment_date: date,
  appointment_time: "08:00",
  reason: "",
  status: "scheduled",
  notes: "",
});
const labels = appointmentStatusLabels;
function message(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string"
    ? detail
    : "No fue posible guardar la cita.";
}
export function AppointmentForm({
  appointment,
  initialPatient,
  initialFollowUp,
  date,
  centers,
  user,
  onClose,
  onSaved,
}: {
  appointment: Appointment | null;
  initialPatient?: Patient | null;
  initialFollowUp?: ClinicalFollowUp | null;
  date: string;
  centers: Center[];
  user: User;
  onClose: () => void;
  onSaved: (item: Appointment) => void;
}) {
  const modeId = useId();
  const [form, setForm] = useState<AppointmentInput>(() =>
    appointment
      ? {
          patient_id: appointment.patient_id,
          doctor_id: appointment.doctor_id,
          center_id: appointment.center_id,
          specialty_id: appointment.specialty_id,
          appointment_date: appointment.appointment_date,
          appointment_time: appointment.appointment_time?.slice(0, 5) ?? null,
          reason: appointment.reason || "",
          status: appointment.status,
          notes: appointment.notes || "",
        }
      : {...blank(date, initialPatient),...(initialFollowUp?{doctor_id:initialFollowUp.doctor_id,center_id:initialFollowUp.center_id,specialty_id:initialFollowUp.specialty_id}: {})},
  );
  const existingPatient = appointment
    ? {
        id: appointment.patient_id,
        first_name:
          appointment.patient_name.split(" ")[0] || appointment.patient_name,
        last_name: appointment.patient_name.split(" ").slice(1).join(" "),
        date_of_birth: appointment.patient_date_of_birth,
        phone_masked: appointment.patient_phone ?? null,
        email_masked: null,
      }
    : null;
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [patient, setPatient] = useState<Identity | Patient | null>(
    initialPatient ?? existingPatient,
  );
  const [query, setQuery] = useState(
    initialPatient
      ? `${initialPatient.first_name} ${initialPatient.last_name}`
      : (appointment?.patient_name ?? ""),
  );
  const [results, setResults] = useState<Patient[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [creatingPatient, setCreatingPatient] = useState(false);
  const [identityQuery, setIdentityQuery] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [identityResults, setIdentityResults] = useState<Identity[]>([]);
  const [saving, setSaving] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [error, setError] = useState("");
  const requested = useRef(0);
  const rules = appointmentRules(appointment, user);
  const locked = rules.identityLocked;
  const [loadingDoctors, setLoadingDoctors] = useState(false);
  const [queueReady, setQueueReady] = useState<boolean | null>(null);
  const modeKey = form.doctor_id && form.center_id && form.appointment_date
    ? `${form.center_id}:${form.doctor_id}:${form.appointment_date}` : null;
  const originalKey = appointment ? `${appointment.center_id}:${appointment.doctor_id}:${appointment.appointment_date}` : null;
  const [modeResolution, setModeResolution] = useState<{
    key: string; options: ModeOptions | null; failed: boolean;
  } | null>(null);
  const [modeSelection, setModeSelection] = useState<{ key: string; mode: Mode } | null>(null);
  const options = modeResolution?.key === modeKey ? modeResolution.options : null;
  const sameAppointmentContext = !!appointment && modeKey === originalKey;
  const queueLineUsable = (options?.queue_line_available ?? true) || (sameAppointmentContext && appointment?.schedule_mode === "queue");
  const preferredMode = sameAppointmentContext ? appointment.schedule_mode ?? options?.default_mode ?? options?.schedule_mode : options?.default_mode ?? options?.schedule_mode;
  const effectiveMode = options ? (modeSelection?.key === modeKey ? modeSelection.mode
    : preferredMode === "queue" && !queueLineUsable ? null : preferredMode) : null;
  const modeFailed = modeResolution?.key === modeKey && modeResolution.failed;
  useEffect(() => {
    void api.get<{ booking_order_enabled: boolean }>("/appointments/queue-capabilities")
      .then(({ data }) => setQueueReady(data.booking_order_enabled))
      .catch(() => setQueueReady(false));
  }, []);
  useEffect(() => {
    if (!modeKey) return;
    let active = true;
    void api.get<ModeOptions>("/appointments/effective-mode", {
      params: { doctor_id: form.doctor_id, center_id: form.center_id, day: form.appointment_date,
        specialty_id: form.specialty_id || undefined },
    }).then(({ data }) => {
      if (active) setModeResolution({ key: modeKey, options: data, failed: false });
    }).catch(() => {
      if (active) setModeResolution({ key: modeKey, options: null, failed: true });
    });
    return () => { active = false; };
  }, [modeKey, form.doctor_id, form.center_id, form.appointment_date, form.specialty_id]);
  useEffect(() => {
    if (effectiveMode === "queue") setForm((current) => current.appointment_time === null ? current : { ...current, appointment_time: null });
  }, [effectiveMode]);
  useEffect(() => {
    const id = ++requested.current;
    if (!form.center_id || !form.appointment_date || rules.specialtyLocked) {
      setDoctors([]);
      setLoadingDoctors(false);
      return;
    }
    setLoadingDoctors(true);
    void api
      .get<Doctor[]>("/appointments/doctors", {
        params: {
          center_id: form.center_id,
          appointment_date: form.appointment_date,
        },
      })
      .then(({ data }) => {
        if (id !== requested.current) return;
        setDoctors(data);
        setForm((current) => {
          const doctor = data.find((item) => item.id === current.doctor_id);
          if (locked) return current;
          return doctor
            ? {
                ...current,
                specialty_id: doctor.specialties.some(
                  (item) => item.id === current.specialty_id,
                )
                  ? current.specialty_id
                  : doctor.specialties.length === 1
                    ? doctor.specialties[0].id
                    : null,
              }
            : { ...current, doctor_id: null, specialty_id: null };
        });
      })
      .catch((reason) => {
        if (id !== requested.current) return;
        setDoctors([]);
        setError(message(reason));
        if (!locked)
          setForm((current) => ({
            ...current,
            doctor_id: null,
            specialty_id: null,
          }));
      })
      .finally(() => {
        if (id === requested.current) setLoadingDoctors(false);
      });
    return () => {
      requested.current += 1;
    };
  }, [form.center_id, form.appointment_date, locked, rules.specialtyLocked]);
  useEffect(() => {
    if (patient || query.trim().length < 2) {
      setResults([]);
      setSearching(false);
      setSearched(false);
      setSearchError(false);
      return;
    }
    let active = true;
    setSearching(true);
    setSearched(false);
    setSearchError(false);
    const timer = window.setTimeout(() => {
      void api.get<Patient[]>("/patients", { params: { query: query.trim(), limit: 10 } })
        .then(({ data }) => { if (active) { setResults(data); setSearched(true); } })
        .catch(() => { if (active) { setResults([]); setSearchError(true); } })
        .finally(() => { if (active) setSearching(false); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [patient, query]);
  useEffect(() => {
    if (
      patient ||
      identityQuery.trim().length < 4 ||
      !birthDate ||
      (user.roles.includes("secretary") &&
        !user.roles.includes("admin") &&
        (!form.center_id || !form.doctor_id))
    ) {
      setIdentityResults([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void api
        .get<Identity[]>("/patients/identity-search", {
          params: {
            date_of_birth: birthDate,
            phone: identityQuery.includes("@") ? undefined : identityQuery.trim(),
            email: identityQuery.includes("@") ? identityQuery.trim() : undefined,
            center_id: form.center_id || undefined,
            doctor_id: form.doctor_id || undefined,
          },
        })
        .then(({ data }) => { if (active) setIdentityResults(data); })
        .catch(() => { if (active) setIdentityResults([]); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [patient, identityQuery, birthDate, form.center_id, form.doctor_id]);
  const selectedDoctor = doctors.find((item) => item.id === form.doctor_id);
  function patch(values: Partial<AppointmentInput>) {
    setForm((current) => ({ ...current, ...values }));
  }
  function selectPatient(value: Identity | Patient) {
    setPatient(value);
    patch({ patient_id: value.id });
    setQuery(`${value.first_name} ${value.last_name}`);
    setError("");
    setResults([]);
    setIdentityResults([]);
  }
  async function save() {
    if (saving || rules.completed) return;
    setAttempted(true);
    if (!form.patient_id) {
      setError("Seleccione un paciente.");
      return;
    }
    if (
      !form.center_id ||
      !form.doctor_id ||
      !form.specialty_id ||
      !form.appointment_date ||
      !effectiveMode ||
      (effectiveMode === "timed" && !form.appointment_time) ||
      (effectiveMode === "queue" && (queueReady !== true || !queueLineUsable))
    ) {
      setError("Complete centro, médico, fecha, especialidad y tipo de cita.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, appointment_time: effectiveMode === "queue" ? null : form.appointment_time,
        ...(!appointment&&initialFollowUp?{follow_up_id:initialFollowUp.id}:{}),
        ...(options?.multimode_enabled ? { schedule_mode: effectiveMode } : {}),
        patient_selection_token: patient?.selection_token };
      const response = appointment
        ? await api.put<Appointment>(`/appointments/${appointment.id}`, payload)
        : await api.post<Appointment>("/appointments", payload);
      onSaved(response.data);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }
  return <>
    <Modal
      open
      onClose={onClose}
      title={appointment ? "Editar cita" : "Nueva cita"}
      description="Los campos se validan con las reglas existentes de Atlas."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            loading={saving}
            disabled={rules.completed || loadingDoctors || !effectiveMode || (effectiveMode === "queue" && (queueReady !== true || !queueLineUsable))}
            onClick={() => void save()}
          >
            Guardar cita
          </Button>
        </>
      }
    >
      <div className="agenda-form">
        <RequiredFieldsLegend />
        {error && (
          <Alert tone="danger" title="No se pudo guardar">
            {error}
          </Alert>
        )}
        <section aria-label="Paciente">
          {patient ? (
            <div className="agenda-selected-patient">
              <div><strong>Paciente</strong><span>{patient.first_name} {patient.last_name}</span>
                <span>{"phone" in patient ? patient.phone || "Sin teléfono" : patient.phone_masked || "Sin teléfono"}</span></div>
              {!locked && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setPatient(null);
                    patch({ patient_id: 0 });
                    setQuery("");
                    setIdentityQuery("");
                    setBirthDate("");
                  }}
                >
                  Cambiar
                </Button>
              )}
            </div>
          ) : (
            <>
              <FormField label="Paciente" required error={attempted && !form.patient_id ? "Este campo es obligatorio." : undefined}>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Buscar por nombre, cédula, teléfono o correo..."
                  autoComplete="off"
                />
              </FormField>
              {query.trim().length >= 2 && <div className="agenda-patient-results" aria-label="Resultados de pacientes" aria-live="polite">
                {searching ? <p className="atlas-muted">Buscando pacientes…</p> : searchError ? <p role="alert">No fue posible buscar pacientes. Intente de nuevo.</p> : results.length ? results.map((item) => (
                  <button type="button" className="agenda-patient-result" key={item.id} onClick={() => selectPatient(item)}>
                    <strong>{item.first_name} {item.last_name}</strong><span>Tel.: {item.phone || "Sin teléfono"}</span>
                  </button>
                )) : searched ? <p className="atlas-muted">No se encontró el paciente.</p> : null}
              </div>}
              <Button variant="outline" size="sm" onClick={() => setCreatingPatient(true)}>+ Crear nuevo paciente</Button>
              <details className="agenda-patient-verification">
                <summary>Verificar paciente por teléfono o correo exacto</summary>
                <p className="atlas-muted">Si no aparece en la búsqueda, verifique su identidad con fecha de nacimiento. La búsqueda habitual solo muestra pacientes dentro de su alcance autorizado.</p>
                <FormField label="Teléfono o correo exacto">
                  <Input value={identityQuery} onChange={(e) => setIdentityQuery(e.target.value)} placeholder="Teléfono o correo exacto" />
                </FormField>
                <FormField label="Fecha de nacimiento">
                  <Input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} aria-label="Fecha de nacimiento" />
                </FormField>
                {identityResults.map((item) => <button type="button" className="agenda-patient-result" key={item.id} onClick={() => selectPatient(item)}>
                  <strong>{item.first_name} {item.last_name}</strong><span>Tel.: {item.phone_masked || "Sin teléfono"}</span>
                </button>)}
              </details>
            </>
          )}
        </section>
        <div className="agenda-form-grid">
          <FormField label="Centro" required error={attempted && !form.center_id ? "Este campo es obligatorio." : undefined}>
            <Select
              disabled={locked}
              value={form.center_id || ""}
              onChange={(e) =>
                patch({
                  center_id: Number(e.target.value) || null,
                  doctor_id: null,
                  specialty_id: null,
                })
              }
            >
              <option value="">Seleccione…</option>
              {locked &&
                appointment?.center_id &&
                !centers.some((item) => item.id === appointment.center_id) && (
                  <option value={appointment.center_id}>
                    {appointment.center_name || "Centro registrado"}
                  </option>
                )}
              {centers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Médico" required error={attempted && !form.doctor_id ? "Este campo es obligatorio." : undefined}>
            <Select
              disabled={locked || !form.center_id || loadingDoctors}
              value={form.doctor_id || ""}
              onChange={(e) => {
                const doctor = doctors.find(
                  (item) => item.id === Number(e.target.value),
                );
                patch({
                  doctor_id: doctor?.id ?? null,
                  specialty_id:
                    doctor?.specialties.length === 1
                      ? doctor.specialties[0].id
                      : null,
                });
              }}
            >
              <option value="">Seleccione…</option>
              {locked && appointment && (
                <option value={appointment.doctor_id}>
                  {appointment.doctor_name}
                </option>
              )}
              {!locked &&
                doctors.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.full_name}
                  </option>
                ))}
            </Select>
          </FormField>
          <fieldset className="agenda-appointment-mode" disabled={!options?.multimode_enabled || rules.scheduleLocked}>
            <legend>Tipo de cita</legend>
            <div className="agenda-appointment-mode-options">
              <label className={effectiveMode === "timed" ? "is-selected" : ""}>
                <input id={`${modeId}-timed`} type="radio" name={modeId} value="timed" checked={effectiveMode === "timed"}
                  disabled={options?.allowed_timed === false} onChange={() => setModeSelection({ key: modeKey!, mode: "timed" })} />
                Por hora{effectiveMode === "timed" ? " ✓" : ""}
              </label>
              <label className={effectiveMode === "queue" ? "is-selected" : ""}>
                <input id={`${modeId}-queue`} type="radio" name={modeId} value="queue" checked={effectiveMode === "queue"}
                  disabled={options?.allowed_queue === false || !queueLineUsable || queueReady !== true}
                  onChange={() => setModeSelection({ key: modeKey!, mode: "queue" })} />
                Por turno{effectiveMode === "queue" ? " ✓" : ""}
              </label>
            </div>
            {!modeKey && <p className="atlas-muted">Seleccione centro, médico y fecha para conocer el tipo de cita.</p>}
            {modeKey && !effectiveMode && !modeFailed && <p className="atlas-muted">{options ? "Seleccione una modalidad disponible." : "Consultando el tipo de cita…"}</p>}
            {modeFailed && <p role="alert" className="text-sm text-red-700">No se pudo consultar el tipo de cita para esta jornada.</p>}
            {options?.allowed_queue && !options.queue_line_available && <p role="alert" className="text-sm text-amber-800">Configure una línea de turnos para utilizar esta modalidad.</p>}
          </fieldset>
          <FormField label="Fecha" required error={attempted && !form.appointment_date ? "Este campo es obligatorio." : undefined}>
            <Input
              disabled={rules.scheduleLocked}
              type="date"
              value={form.appointment_date}
              onChange={(e) => patch({ appointment_date: e.target.value })}
            />
          </FormField>
          {effectiveMode === "queue" ? <p className="atlas-muted">Cita por turno. El turno se asigna al registrar llegada.{queueReady === false ? " La captura sin hora no está disponible en este momento." : ""}</p> : effectiveMode === "timed" ? <FormField label="Hora" required error={attempted && !form.appointment_time ? "Este campo es obligatorio." : undefined}>
            <Input
              disabled={rules.scheduleLocked}
              type="time"
              value={form.appointment_time ?? ""}
              onChange={(e) => patch({ appointment_time: e.target.value })}
            />
          </FormField> : null}
          <FormField label="Especialidad" required error={attempted && !form.specialty_id ? "Este campo es obligatorio." : undefined}>
            <Select
              disabled={
                rules.specialtyLocked || !form.doctor_id || loadingDoctors
              }
              value={form.specialty_id || ""}
              onChange={(e) =>
                patch({ specialty_id: Number(e.target.value) || null })
              }
            >
              <option value="">Seleccione…</option>
              {rules.specialtyLocked && appointment && (
                <option value={appointment.specialty_id ?? ""}>
                  {appointment.specialty_name}
                </option>
              )}
              {!rules.specialtyLocked &&
                selectedDoctor?.specialties.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField label="Estado">
            <Select
              disabled={rules.completed}
              value={form.status}
              onChange={(e) =>
                patch({ status: e.target.value as Appointment["status"] })
              }
            >
              {Object.entries(labels)
                .filter(
                  ([id]) =>
                    rules.completed ||
                    (id !== "completed" &&
                      (!appointment?.has_clinical_history ||
                        (id !== "cancelled" && id !== "no_show"))),
                )
                .map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
            </Select>
          </FormField>
        </div>
        <FormField label="Motivo">
          <Input
            disabled={rules.completed}
            value={form.reason || ""}
            onChange={(e) => patch({ reason: e.target.value })}
          />
        </FormField>
        <FormField label="Observaciones">
          <Textarea
            disabled={rules.completed}
            value={form.notes || ""}
            onChange={(e) => patch({ notes: e.target.value })}
          />
        </FormField>
      </div>
    </Modal>
    {creatingPatient && <PatientForm patient={null} user={user} onClose={() => setCreatingPatient(false)}
      onSaved={(value) => { selectPatient(value); setCreatingPatient(false); }}
      onExistingSelected={(value) => { selectPatient(value); setCreatingPatient(false); }} />}
  </>;
}
