import { FormEvent, useEffect, useState } from "react";
import { api } from "../services/api";
import PatientForm from "../components/patients/PatientForm";
import PatientInsurancePanel from "../components/patients/PatientInsurancePanel";
import ClinicalHistoryPanel from "../components/patients/ClinicalHistoryPanel";
import type { Patient } from "../types/patient";
import type { User } from "../types/user";

type Props = {
  onBack: () => void;
  onPatientChanged: () => void;
  onScheduleAppointment: (patient: Patient) => void;
  user: User;
};

export default function Patients({ onBack, onPatientChanged, onScheduleAppointment, user }: Props) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Patient | null>(null);
  const [insurancePatient, setInsurancePatient] = useState<Patient | null>(null);
  const [historyPatient, setHistoryPatient] = useState<Patient | null>(null);

  async function loadPatients(search = "") {
    setLoading(true); setError("");
    try {
      const { data } = await api.get<Patient[]>("/patients", { params: { query: search.trim() || undefined, limit: 100 } });
      setPatients(data);
    } catch (err: any) {
      console.error(err); setError(err?.response?.data?.detail || "No fue posible cargar los pacientes.");
    } finally { setLoading(false); }
  }

  useEffect(() => { void loadPatients(); }, []);

  function createPatient() { setEditing(null); setShowForm(true); }
  function editPatient(patient: Patient) { setEditing(patient); setShowForm(true); }
  function handleSaved() { setShowForm(false); void loadPatients(query); onPatientChanged(); }

  return <section>
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button><h2 className="mt-2 text-2xl font-bold">Pacientes</h2><p className="mt-1 text-sm text-slate-500">Registro y administración de pacientes.</p></div><button onClick={createPatient} className="rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800">+ Nuevo paciente</button></div>
    <form onSubmit={(event: FormEvent) => { event.preventDefault(); void loadPatients(query); }} className="mt-6 flex flex-col gap-3 rounded-xl border bg-white p-4 shadow-sm sm:flex-row"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por nombre, apellido o teléfono..." className="flex-1 rounded-lg border border-slate-300 px-3 py-2" /><button type="submit" className="rounded-lg bg-slate-900 px-5 py-2 font-medium text-white">Buscar</button><button type="button" onClick={() => { setQuery(""); void loadPatients(""); }} className="rounded-lg border border-slate-300 px-5 py-2 font-medium">Limpiar</button></form>
    {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="mt-6 overflow-hidden rounded-xl border bg-white shadow-sm">{loading ? <p className="p-6 text-slate-500">Cargando pacientes...</p> : patients.length === 0 ? <div className="p-10 text-center"><p className="font-medium">No hay pacientes registrados.</p><p className="mt-1 text-sm text-slate-500">Puedes registrar el primero con "Nuevo paciente".</p></div> : <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Paciente</th><th className="px-4 py-3">Fecha nacimiento</th><th className="px-4 py-3">Teléfono</th><th className="px-4 py-3">Correo</th><th className="px-4 py-3 text-right">Acciones</th></tr></thead><tbody className="divide-y divide-slate-100">{patients.map((patient) => <tr key={patient.id} className="hover:bg-slate-50"><td className="px-4 py-3 font-medium">{patient.first_name} {patient.last_name}</td><td className="px-4 py-3">{patient.date_of_birth}</td><td className="px-4 py-3">{patient.phone || "—"}</td><td className="px-4 py-3">{patient.email || "—"}</td><td className="px-4 py-3 text-right"><div className="flex flex-wrap justify-end gap-3"><button onClick={() => onScheduleAppointment(patient)} className="font-medium text-emerald-700 hover:underline">Agendar cita</button><button onClick={() => editPatient(patient)} className="font-medium text-teal-700 hover:underline">Editar</button><button onClick={() => setHistoryPatient(patient)} className="font-medium text-indigo-700 hover:underline">Historia clínica</button><button onClick={() => setInsurancePatient(patient)} className="font-medium text-slate-700 hover:underline">Seguro</button></div></td></tr>)}</tbody></table></div>}</div>
    {showForm && <PatientForm patient={editing} onClose={() => setShowForm(false)} onSaved={handleSaved} />}
    {historyPatient && <ClinicalHistoryPanel patientId={historyPatient.id} patientName={`${historyPatient.first_name} ${historyPatient.last_name}`} onClose={() => setHistoryPatient(null)} />}
    {insurancePatient && <PatientInsurancePanel patientId={insurancePatient.id} patientName={`${insurancePatient.first_name} ${insurancePatient.last_name}`} user={user} onClose={() => setInsurancePatient(null)} />}
  </section>;
}
