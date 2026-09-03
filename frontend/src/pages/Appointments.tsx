import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import type { Appointment, AppointmentInput } from "../types/appointment";
import type { Patient } from "../types/patient";
import type { User } from "../types/user";
import { sortAppointments, type AppointmentSortKey, type SortDirection } from "../utils/appointmentSort";

type Center = { id: number; name: string; city: string; center_type: string; is_active: boolean };
type Doctor = { id: number; full_name: string };
type Props = { user: User; onBack: () => void; initialPatient?: Patient | null; canAccessClinical: boolean; onAttendAppointment: (appointment: Appointment) => void };

const empty: AppointmentInput = { patient_id: 0, doctor_id: null, center_id: null, appointment_date: new Date().toISOString().slice(0, 10), appointment_time: "08:00", reason: "", status: "scheduled", notes: "" };
const labels: Record<string, string> = { scheduled: "Programada", confirmed: "Confirmada", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió" };

function errorMessage(reason: any, fallback: string) {
  const detail = reason?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg).filter(Boolean).join(" ") || fallback;
  return reason?.message || fallback;
}

export default function Appointments({ user, onBack, initialPatient, canAccessClinical, onAttendAppointment }: Props) {
  const [items, setItems] = useState<Appointment[]>([]);
  const [centers, setCenters] = useState<Center[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [patientResults, setPatientResults] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [form, setForm] = useState<AppointmentInput>({ ...empty });
  const [editing, setEditing] = useState<Appointment | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchingPatients, setSearchingPatients] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [loadingDoctors, setLoadingDoctors] = useState(false);
  const [savingAppointment, setSavingAppointment] = useState(false);
  const [sort, setSort] = useState<{ key: AppointmentSortKey; direction: SortDirection }>({ key: "dateTime", direction: "asc" });
  const doctorRequest = useRef(0);
  const initialPatientHandled = useRef(false);

  async function load() { setLoading(true); try { const [a, c] = await Promise.all([api.get<Appointment[]>("/appointments"), api.get<Center[]>("/centers/mine")]); setItems(a.data); setCenters(c.data); } catch (e: any) { setError(e?.response?.data?.detail || "No fue posible cargar la agenda."); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  useEffect(() => { if (loading || !initialPatient || initialPatientHandled.current) return; initialPatientHandled.current = true; openNew(initialPatient); }, [loading, initialPatient, centers]);
  useEffect(() => { if (!showForm || selectedPatient || patientQuery.trim().length < 2) { setPatientResults([]); return; } const timer = window.setTimeout(async () => { setSearchingPatients(true); try { const { data } = await api.get<Patient[]>("/patients", { params: { query: patientQuery.trim(), limit: 10 } }); setPatientResults(data); } catch (e: any) { setPatientResults([]); setFormError(errorMessage(e, "No fue posible buscar pacientes.")); } finally { setSearchingPatients(false); } }, 250); return () => window.clearTimeout(timer); }, [patientQuery, selectedPatient, showForm]);

  async function loadDoctors(centerId: number | null, date: string, preferredDoctorId?: number | null) {
    const request = ++doctorRequest.current;
    if (!centerId || !date) { setDoctors([]); setLoadingDoctors(false); return; }
    setLoadingDoctors(true);
    try {
      const { data } = await api.get<Doctor[]>("/appointments/doctors", { params: { center_id: centerId, appointment_date: date } });
      if (request !== doctorRequest.current) return;
      setDoctors(data);
      setForm((current) => {
        if (current.center_id !== centerId || current.appointment_date !== date) return current;
        const preferred = preferredDoctorId === undefined ? current.doctor_id : preferredDoctorId;
        const validPreferred = preferred && data.some((doctor) => doctor.id === preferred) ? preferred : null;
        const currentDoctor = user.roles.includes("doctor") && data.some((doctor) => doctor.id === user.id) ? user.id : null;
        return { ...current, doctor_id: validPreferred || currentDoctor };
      });
    } catch (e: any) {
      if (request !== doctorRequest.current) return;
      setDoctors([]);
      setForm((current) => current.center_id === centerId && current.appointment_date === date ? { ...current, doctor_id: null } : current);
      setFormError(errorMessage(e, "No fue posible consultar los médicos disponibles."));
    } finally {
      if (request === doctorRequest.current) setLoadingDoctors(false);
    }
  }
  function openNew(patient?: Patient | null) {
    doctorRequest.current += 1;
    setDoctors([]);
    setFormError("");
    setEditing(null);
    setSelectedPatient(patient ?? null);
    setPatientQuery(patient ? `${patient.first_name} ${patient.last_name}` : "");
    const center = centers.length === 1 ? centers[0].id : null;
    setForm({ ...empty, patient_id: patient?.id ?? 0, center_id: center });
    setShowForm(true);
    if (center) void loadDoctors(center, empty.appointment_date, null);
  }
  async function edit(a: Appointment) { setFormError(""); setEditing(a); try { const { data } = await api.get<Patient>(`/patients/${a.patient_id}`); setSelectedPatient(data); setPatientQuery(`${data.first_name} ${data.last_name}`); } catch { setSelectedPatient(null); setPatientQuery(a.patient_name); } setForm({ patient_id: a.patient_id, doctor_id: a.doctor_id, center_id: a.center_id, appointment_date: a.appointment_date, appointment_time: a.appointment_time.slice(0, 5), reason: a.reason || "", status: a.status, notes: a.notes || "" }); setShowForm(true); if (a.center_id) void loadDoctors(a.center_id, a.appointment_date, a.doctor_id); }
  function selectPatient(patient: Patient) { setSelectedPatient(patient); setPatientQuery(`${patient.first_name} ${patient.last_name}`); setPatientResults([]); setForm((f) => ({ ...f, patient_id: patient.id })); }
  function clearPatient() { setSelectedPatient(null); setPatientQuery(""); setPatientResults([]); setForm((f) => ({ ...f, patient_id: 0 })); }
  async function save() { if (savingAppointment) return; setFormError(""); setSavingAppointment(true); try { if (!form.patient_id) throw new Error("Seleccione un paciente."); if (!form.center_id) throw new Error("Seleccione el centro donde se realizará la cita."); if (!form.doctor_id) throw new Error("Seleccione el médico que atenderá la cita."); if (editing) await api.put(`/appointments/${editing.id}`, form); else await api.post("/appointments", form); setShowForm(false); setSelectedPatient(null); await load(); } catch (e: any) { setFormError(errorMessage(e, "No fue posible guardar la cita.")); } finally { setSavingAppointment(false); } }
  async function remove(id: number) { if (!confirm("¿Eliminar esta cita?")) return; try { await api.delete(`/appointments/${id}`); await load(); } catch (e: any) { setError(e?.response?.data?.detail || "No fue posible eliminar la cita."); } }

  const sortedItems = useMemo(
    () => sortAppointments(items, sort.key, sort.direction, labels),
    [items, sort],
  );

  function toggleSort(key: AppointmentSortKey) {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
      : { key, direction: "asc" });
  }

  function sortableHeader(label: string, key: AppointmentSortKey, colSpan?: number) {
    const active = sort.key === key;
    return <th colSpan={colSpan} aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} className="px-4 py-3"><button type="button" onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 font-semibold hover:text-teal-700">{label}<span aria-hidden="true">{active ? (sort.direction === "asc" ? "↑" : "↓") : ""}</span></button></th>;
  }

  return <section>
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button><h2 className="mt-2 text-2xl font-bold">Agenda de citas</h2><p className="mt-1 text-sm text-slate-500">Programa y administra las citas de los pacientes.</p></div><button onClick={() => openNew()} className="rounded-lg bg-teal-700 px-4 py-2 font-medium text-white">+ Nueva cita</button></div>
    {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="mt-6 overflow-hidden rounded-xl border bg-white shadow-sm">{loading ? <p className="p-6 text-slate-500">Cargando agenda...</p> : items.length === 0 ? <p className="p-10 text-center text-slate-500">No hay citas registradas.</p> : <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{sortableHeader("Fecha / Hora", "dateTime", 2)}{sortableHeader("Paciente", "patient")}{sortableHeader("Médico", "doctor")}{sortableHeader("Centro", "center")}{sortableHeader("Estado", "status")}<th className="px-4 py-3">Motivo</th><th className="px-4 py-3 text-right">Acciones</th></tr></thead><tbody className="divide-y divide-slate-100">{sortedItems.map((a) => <tr key={a.id}><td className="px-4 py-3">{a.appointment_date}</td><td className="px-4 py-3 font-medium">{a.appointment_time.slice(0, 5)}</td><td className="px-4 py-3 font-medium">{a.patient_name}</td><td className="px-4 py-3">{a.doctor_name}</td><td className="px-4 py-3">{a.center_name ? `${a.center_name} (${a.center_city})` : "—"}</td><td className="px-4 py-3">{labels[a.status]}</td><td className="px-4 py-3">{a.reason || "—"}</td><td className="px-4 py-3 text-right">{canAccessClinical && <button onClick={() => onAttendAppointment(a)} className="mr-3 rounded-md bg-teal-700 px-3 py-1.5 font-medium text-white">Atender</button>}<button onClick={() => void edit(a)} className="mr-3 font-medium text-teal-700">Editar</button><button onClick={() => void remove(a.id)} className="font-medium text-red-700">Eliminar</button></td></tr>)}</tbody></table></div>}</div>
    {showForm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"><h3 className="text-xl font-bold">{editing ? "Editar cita" : "Nueva cita"}</h3>
      <div className="relative mt-4"><label className="block text-sm font-medium">Paciente</label>{selectedPatient ? <div className="mt-1 flex items-center justify-between rounded-lg border bg-slate-50 p-2.5"><span className="font-medium">{selectedPatient.first_name} {selectedPatient.last_name}</span><button type="button" onClick={clearPatient} className="text-sm font-medium text-red-700">Cambiar</button></div> : <><input value={patientQuery} onChange={(e) => setPatientQuery(e.target.value)} placeholder="Escriba nombre o apellido..." className="mt-1 w-full rounded-lg border p-2.5" autoComplete="off" />{patientQuery.trim().length >= 2 && <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-auto rounded-lg border bg-white shadow-lg">{searchingPatients ? <p className="p-3 text-sm text-slate-500">Buscando...</p> : patientResults.length ? patientResults.map((p) => <button type="button" key={p.id} onClick={() => selectPatient(p)} className="block w-full border-b px-3 py-2 text-left hover:bg-slate-50"><span className="font-medium">{p.first_name} {p.last_name}</span>{p.phone && <span className="ml-2 text-xs text-slate-500">{p.phone}</span>}</button>) : <p className="p-3 text-sm text-slate-500">No se encontraron pacientes.</p>}</div>}</>}</div>
      <label className="mt-4 block text-sm font-medium">Centro de atención<select value={form.center_id || ""} onChange={(e) => { const id = Number(e.target.value) || null; setFormError(""); setForm((current) => ({ ...current, center_id: id, doctor_id: null })); void loadDoctors(id, form.appointment_date, null); }} className="mt-1 w-full rounded-lg border p-2.5" required><option value="">Seleccione...</option>{centers.map((c) => <option key={c.id} value={c.id}>{c.name} — {c.city}</option>)}</select></label>
      <div className="mt-4 grid grid-cols-2 gap-3"><label className="text-sm font-medium">Fecha<input type="date" value={form.appointment_date} onChange={(e) => { const date = e.target.value; setFormError(""); setForm((current) => ({ ...current, appointment_date: date })); void loadDoctors(form.center_id, date, form.doctor_id); }} className="mt-1 w-full rounded-lg border p-2.5" required /></label><label className="text-sm font-medium">Hora<input type="time" value={form.appointment_time} onChange={(e) => setForm({ ...form, appointment_time: e.target.value })} className="mt-1 w-full rounded-lg border p-2.5" required /></label></div>
      <label className="mt-4 block text-sm font-medium">Médico<select value={form.doctor_id || ""} onChange={(e) => setForm({ ...form, doctor_id: Number(e.target.value) || null })} className="mt-1 w-full rounded-lg border p-2.5" required disabled={!form.center_id || loadingDoctors}><option value="">{loadingDoctors ? "Consultando disponibilidad..." : "Seleccione..."}</option>{doctors.map((d) => <option key={d.id} value={d.id}>{d.full_name}</option>)}</select></label>
      <label className="mt-4 block text-sm font-medium">Estado<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as AppointmentInput["status"] })} className="mt-1 w-full rounded-lg border p-2.5">{Object.entries(labels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label><label className="mt-4 block text-sm font-medium">Motivo<input value={form.reason || ""} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="mt-1 w-full rounded-lg border p-2.5" /></label><label className="mt-4 block text-sm font-medium">Notas<textarea value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} className="mt-1 w-full rounded-lg border p-2.5" /></label>{formError && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{formError}</div>}<div className="mt-6 flex justify-end gap-3"><button onClick={() => setShowForm(false)} disabled={savingAppointment} className="rounded-lg border px-5 py-2 disabled:opacity-60">Cancelar</button><button onClick={() => void save()} disabled={savingAppointment} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-60">{savingAppointment ? "Guardando..." : "Guardar"}</button></div></div></div>}
  </section>;
}
