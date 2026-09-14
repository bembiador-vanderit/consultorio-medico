import { useEffect, useRef, useState } from "react";
import type { Appointment, AppointmentInput } from "../../types/appointment";
import type { Patient } from "../../types/patient";
import type { User } from "../../types/user";
import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  Select,
  Textarea,
} from "../../ui";
import { api } from "../../services/api";

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
  date,
  centers,
  user,
  onClose,
  onSaved,
}: {
  appointment: Appointment | null;
  initialPatient?: Patient | null;
  date: string;
  centers: Center[];
  user: User;
  onClose: () => void;
  onSaved: (item: Appointment) => void;
}) {
  const [form, setForm] = useState<AppointmentInput>(() =>
    appointment
      ? {
          patient_id: appointment.patient_id,
          doctor_id: appointment.doctor_id,
          center_id: appointment.center_id,
          specialty_id: appointment.specialty_id,
          appointment_date: appointment.appointment_date,
          appointment_time: appointment.appointment_time.slice(0, 5),
          reason: appointment.reason || "",
          status: appointment.status,
          notes: appointment.notes || "",
        }
      : blank(date, initialPatient),
  );
  const existingPatient = appointment
    ? {
        id: appointment.patient_id,
        first_name:
          appointment.patient_name.split(" ")[0] || appointment.patient_name,
        last_name: appointment.patient_name.split(" ").slice(1).join(" "),
        date_of_birth: appointment.patient_date_of_birth,
        phone_masked: null,
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
  const [birthDate, setBirthDate] = useState(
    initialPatient?.date_of_birth ?? appointment?.patient_date_of_birth ?? "",
  );
  const [results, setResults] = useState<Identity[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const requested = useRef(0);
  const rules = appointmentRules(appointment, user);
  const locked = rules.identityLocked;
  const [loadingDoctors, setLoadingDoctors] = useState(false);
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
    if (
      patient ||
      query.trim().length < 4 ||
      !birthDate ||
      (user.roles.includes("secretary") &&
        !user.roles.includes("admin") &&
        (!form.center_id || !form.doctor_id))
    ) {
      setResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void api
        .get<Identity[]>("/patients/identity-search", {
          params: {
            date_of_birth: birthDate,
            phone: query.includes("@") ? undefined : query.trim(),
            email: query.includes("@") ? query.trim() : undefined,
            center_id: form.center_id || undefined,
            doctor_id: form.doctor_id || undefined,
          },
        })
        .then(({ data }) => setResults(data))
        .catch(() => setResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [patient, query, birthDate, form.center_id, form.doctor_id]);
  const selectedDoctor = doctors.find((item) => item.id === form.doctor_id);
  function patch(values: Partial<AppointmentInput>) {
    setForm((current) => ({ ...current, ...values }));
  }
  async function save() {
    if (saving || rules.completed) return;
    if (
      !form.patient_id ||
      !form.center_id ||
      !form.doctor_id ||
      !form.specialty_id ||
      !form.appointment_date ||
      !form.appointment_time
    ) {
      setError("Complete paciente, centro, médico y especialidad.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, patient_selection_token: patient?.selection_token };
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
  return (
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
            disabled={rules.completed || loadingDoctors}
            onClick={() => void save()}
          >
            Guardar cita
          </Button>
        </>
      }
    >
      <div className="agenda-form">
        {error && (
          <Alert tone="danger" title="No se pudo guardar">
            {error}
          </Alert>
        )}
        <section aria-label="Paciente">
          {patient ? (
            <div className="agenda-selected-patient">
              <span>
                {patient.first_name} {patient.last_name}
              </span>
              {!locked && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setPatient(null);
                    patch({ patient_id: 0 });
                    setQuery("");
                    setBirthDate("");
                  }}
                >
                  Cambiar
                </Button>
              )}
            </div>
          ) : (
            <>
              <FormField label="Teléfono o correo exacto" required>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Teléfono o correo exacto"
                />
              </FormField>
              <FormField label="Fecha de nacimiento" required>
                <Input
                  type="date"
                  value={birthDate}
                  onChange={(e) => setBirthDate(e.target.value)}
                  aria-label="Fecha de nacimiento"
                />
              </FormField>
              {results.map((item) => (
                <button
                  type="button"
                  className="agenda-patient-result"
                  key={item.id}
                  onClick={() => {
                    setPatient(item);
                    setQuery(`${item.first_name} ${item.last_name}`);
                    patch({ patient_id: item.id });
                  }}
                >
                  {item.first_name} {item.last_name} · {item.date_of_birth}
                </button>
              ))}
            </>
          )}
        </section>
        <div className="agenda-form-grid">
          <FormField label="Centro" required>
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
          <FormField label="Médico" required>
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
          <FormField label="Fecha" required>
            <Input
              disabled={rules.scheduleLocked}
              type="date"
              value={form.appointment_date}
              onChange={(e) => patch({ appointment_date: e.target.value })}
            />
          </FormField>
          <FormField label="Hora" required>
            <Input
              disabled={rules.scheduleLocked}
              type="time"
              value={form.appointment_time}
              onChange={(e) => patch({ appointment_time: e.target.value })}
            />
          </FormField>
          <FormField label="Especialidad" required>
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
                <option value={appointment.specialty_id}>
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
  );
}
