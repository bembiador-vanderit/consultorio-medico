import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api } from "../services/api";
import PatientForm from "../components/patients/PatientForm";
import PatientInsurancePanel from "../components/patients/PatientInsurancePanel";
import ClinicalHistoryPanel from "../components/patients/ClinicalHistoryPanel";
import { Alert, Button, Card, Drawer, EmptyState, FormField, Input, LoadingState, Modal, PageHeader, Select } from "../ui";
import type { Patient } from "../types/patient";
import type { User } from "../types/user";
import { NavigationIcon } from "../layouts/NavigationIcon";
import "./patients.css";

type Props = { onBack: () => void; onPatientChanged: () => void; onScheduleAppointment: (patient: Patient) => void; user: User };
type PatientSortKey = "name" | "dateOfBirth" | "phone" | "email";
const collator = new Intl.Collator("es", { numeric: true, sensitivity: "base" });

export function patientAge(dateOfBirth: string, now = new Date()): number | null {
  const birth = new Date(`${dateOfBirth}T00:00:00`);
  if (!Number.isFinite(birth.getTime()) || birth > now) return null;
  const birthdayPending = now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  return now.getFullYear() - birth.getFullYear() - Number(birthdayPending);
}
const birthLabel = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" });
const ageLabel = (patient: Patient) => { const age = patientAge(patient.date_of_birth); return age === null ? "Edad no disponible" : `${age} años`; };
const fullName = (patient: Patient) => `${patient.first_name} ${patient.last_name}`;
function Avatar({ patient }: { patient: Patient }) {
  return <span className="patients-avatar" aria-hidden="true">{patient.first_name.trim().slice(0, 1)}{patient.last_name.trim().slice(0, 1)}</span>;
}
function errorMessage(reason: unknown) {
  const detail = (reason as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "No fue posible cargar los pacientes.";
}

export default function Patients({ onBack, onPatientChanged, onScheduleAppointment, user }: Props) {
  const canAccessClinical = user.roles.includes("doctor");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Patient | null>(null);
  const [desktop, setDesktop] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  const [detailOpen, setDetailOpen] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Patient | null>(null);
  const [insurancePatient, setInsurancePatient] = useState<Patient | null>(null);
  const [historyPatient, setHistoryPatient] = useState<Patient | null>(null);
  const [sort, setSort] = useState<{ key: PatientSortKey; direction: "asc" | "desc" } | null>(null);
  const request = useRef(0);
  const rowRefs = useRef(new Map<number, HTMLButtonElement>());

  async function loadPatients(search = "") {
    const id = ++request.current;
    setLoading(true); setError(""); setAppliedQuery(search.trim());
    try {
      const { data } = await api.get<Patient[]>("/patients", { params: { query: search.trim() || undefined, limit: 100 } });
      if (id !== request.current) return;
      setPatients(data);
      setSelected((current) => {
        const updated = data.find((patient) => patient.id === current?.id);
        return updated ? { ...updated, selection_token: current?.selection_token } : null;
      });
    } catch (reason) {
      if (id === request.current) { setError(errorMessage(reason)); setPatients([]); setSelected(null); }
    } finally { if (id === request.current) setLoading(false); }
  }
  useEffect(() => { void loadPatients(); return () => { request.current++; }; }, []);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const change = () => { setDesktop(media.matches); if (media.matches) setDetailOpen(false); };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);

  const sortedPatients = useMemo(() => {
    if (!sort) return patients;
    const direction = sort.direction === "asc" ? 1 : -1;
    return [...patients].sort((a, b) => {
      const value = (patient: Patient) => sort.key === "name" ? fullName(patient) : sort.key === "dateOfBirth" ? patient.date_of_birth : patient[sort.key] ?? "";
      return (collator.compare(value(a), value(b)) || a.id - b.id) * direction;
    });
  }, [patients, sort]);

  function selectPatient(patient: Patient) { setSelected(patient); if (!desktop) setDetailOpen(true); }
  function createPatient() { setEditing(null); setShowForm(true); }
  function handleSaved(patient: Patient) {
    const saved = { ...patient, selection_token: patient.selection_token ?? editing?.selection_token };
    setShowForm(false); setSelected(saved); onPatientChanged();
    if (!editing && (user.roles.includes("doctor") || user.roles.includes("secretary"))) onScheduleAppointment(saved);
    else void loadPatients(appliedQuery);
  }
  function detail() {
    if (!selected) return <EmptyState title="Selecciona un paciente para ver su información" description="Su ficha y acciones aparecerán aquí." />;
    return <div className="patients-detail-content">
      <div className="patients-detail-summary"><div className="patients-identity"><Avatar patient={selected} /><div><p className="atlas-caption">Ficha del paciente</p><h3 className="atlas-section-title" title={fullName(selected)}>{fullName(selected)}</h3><p className="atlas-muted">{ageLabel(selected)}</p></div></div>
      <dl className="patients-facts">
        <div><dt>Fecha de nacimiento</dt><dd>{birthLabel(selected.date_of_birth)}</dd></div>
        <div><dt>Teléfono</dt><dd>{selected.phone || "Sin teléfono registrado"}</dd></div>
        <div><dt>Correo</dt><dd>{selected.email || "Sin correo registrado"}</dd></div>
      </dl></div>
      <div className="patients-quick-actions" aria-label="Acciones del paciente">
        <Button icon={<NavigationIcon name="calendar" />} onClick={() => onScheduleAppointment(selected)}>Agendar cita</Button>
        <Button icon={<NavigationIcon name="patient" />} variant="outline" onClick={() => { setEditing(selected); setShowForm(true); }}>Editar</Button>
        <Button icon={<NavigationIcon name="clinical" />} variant="outline" onClick={() => setInsurancePatient(selected)}>Seguro</Button>
        {canAccessClinical && <Button icon={<NavigationIcon name="report" />} variant="outline" onClick={() => setHistoryPatient(selected)}>Historia clínica</Button>}
      </div>
    </div>;
  }

  return <section className="patients-workspace" aria-label="Gestión de pacientes">
    <PageHeader title="Pacientes" description="Gestión y seguimiento de pacientes" actions={<Button onClick={createPatient}>+ Nuevo paciente</Button>} />
    <form className="patients-search" onSubmit={(event: FormEvent) => { event.preventDefault(); void loadPatients(query); }}>
      <FormField label="Buscar pacientes"><Input type="search" placeholder="Buscar por nombre, apellido o teléfono..." value={query} onChange={(event) => setQuery(event.target.value)} /></FormField>
      <div className="patients-search-actions"><Button type="submit">Buscar</Button><Button variant="outline" onClick={() => { setQuery(""); void loadPatients(); }}>Limpiar</Button></div>
    </form>
    <div className="patients-layout">
      <Card className="patients-master">
        <header className="patients-list-header"><div><h2 className="atlas-card-title">Listado de pacientes</h2><p className="atlas-help">{loading ? "Consultando registros" : error ? "Consulta no disponible" : `${patients.length} registros mostrados${patients.length === 100 ? " · Límite de 100" : ""}`}</p></div>
          <FormField label="Ordenar listado"><Select value={sort ? `${sort.key}:${sort.direction}` : "default"} onChange={(event) => {
            const [key, direction] = event.target.value.split(":");
            setSort(key === "default" ? null : { key: key as PatientSortKey, direction: direction as "asc" | "desc" });
          }}><option value="default">Orden del servidor</option>{[["name", "Nombre"], ["dateOfBirth", "Nacimiento"], ["phone", "Teléfono"], ["email", "Correo"]].flatMap(([key, label]) => [<option key={`${key}:asc`} value={`${key}:asc`}>{label} ↑</option>, <option key={`${key}:desc`} value={`${key}:desc`}>{label} ↓</option>])}</Select></FormField>
        </header>
        <div className="patients-list-scroll" aria-busy={loading}>
          {loading ? <LoadingState label="Cargando pacientes..." /> : error ? <div className="patients-error"><Alert tone="danger" title="No se pudo cargar el listado">{error}</Alert><Button variant="outline" onClick={() => void loadPatients(appliedQuery)}>Reintentar</Button></div> : patients.length === 0 ? <EmptyState title={appliedQuery ? "No hay resultados para esta búsqueda" : "No hay pacientes registrados"} description={appliedQuery ? "Prueba con otro nombre, apellido o teléfono." : "Registra un paciente para comenzar."} action={<Button variant="outline" onClick={appliedQuery ? () => { setQuery(""); void loadPatients(); } : createPatient}>{appliedQuery ? "Limpiar búsqueda" : "+ Nuevo paciente"}</Button>} /> : <ul className="patients-list" aria-label="Pacientes encontrados">{sortedPatients.map((patient) => <li key={patient.id}>
            <button type="button" className="patients-row" aria-pressed={selected?.id === patient.id} aria-haspopup={!desktop ? "dialog" : undefined} onClick={() => selectPatient(patient)} ref={(element) => { if (element) rowRefs.current.set(patient.id, element); else rowRefs.current.delete(patient.id); }}>
              <Avatar patient={patient} /><span className="patients-row-identity"><strong title={fullName(patient)}>{fullName(patient)}</strong><span>{ageLabel(patient)} · {birthLabel(patient.date_of_birth)}</span></span>
              <span className="patients-row-contact"><span title={patient.phone || undefined}>{patient.phone || "Sin teléfono"}</span><span title={patient.email || undefined}>{patient.email || "Sin correo"}</span></span>
              <span className="patients-row-status" aria-hidden="true">{selected?.id === patient.id ? "Seleccionado" : "Ver ficha"}</span>
            </button>
          </li>)}</ul>}
        </div>
        <footer className="patients-list-footer"><span className="atlas-help">Búsqueda en el servidor · Hasta 100 registros</span><Button variant="ghost" size="sm" onClick={onBack}>← Volver al dashboard</Button></footer>
      </Card>
      {desktop && <Card className="patients-detail" role="region" aria-label="Detalle del paciente"><header className="patients-detail-header"><h2 className="atlas-card-title">Información del paciente</h2>{selected && <Button size="sm" variant="ghost" onClick={() => { rowRefs.current.get(selected.id)?.focus(); setSelected(null); }}>Cerrar ficha</Button>}</header><div className="patients-detail-scroll">{detail()}</div></Card>}
    </div>
    {!desktop && selected && <Drawer title="Información del paciente" open={detailOpen} onClose={() => setDetailOpen(false)} closeLabel="Cerrar ficha" closeOnBackdrop>{detail()}</Drawer>}
    {showForm && <PatientForm patient={editing} user={user} onClose={() => setShowForm(false)} onSaved={handleSaved} onExistingSelected={(patient) => { setShowForm(false); onScheduleAppointment(patient); }} />}
    {insurancePatient && <PatientInsurancePanel patientId={insurancePatient.id} patientName={fullName(insurancePatient)} user={user} onClose={() => setInsurancePatient(null)} />}
    {canAccessClinical && historyPatient && <Modal title="Historia clínica" description={fullName(historyPatient)} open onClose={() => setHistoryPatient(null)} closeLabel="Cerrar historia clínica"><ClinicalHistoryPanel embedded patientId={historyPatient.id} patientName={fullName(historyPatient)} user={user} onClose={() => setHistoryPatient(null)} /></Modal>}
  </section>;
}
