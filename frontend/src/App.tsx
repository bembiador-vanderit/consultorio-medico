import { useEffect, useState } from "react";
import { authenticate, type LoginCredentials } from "./services/login";
import Login, { SessionLoading } from "./pages/Login";
import { api, logoutSession, refreshAccessToken, setAccessToken } from "./services/api";
import Dashboard from "./pages/Dashboard";
import Patients from "./pages/Patients";
import Appointments from "./pages/Appointments";
import AppointmentReports from "./pages/AppointmentReports";
import CareContext from "./pages/CareContext";
import DoctorAvailability from "./pages/DoctorAvailability";
import Users from "./pages/Users";
import FollowUps from "./pages/FollowUps";
import Consultation from "./pages/Consultation";
import ClinicalCoverages from "./pages/ClinicalCoverages";
import NotificationBell from "./components/NotificationBell";
import type { Patient } from "./types/patient";
import type { Appointment } from "./types/appointment";
import type { User } from "./types/user";

type View = "dashboard" | "patients" | "appointments" | "reports" | "care-context" | "availability" | "users" | "follow-ups" | "consultation" | "clinical-coverages";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [patientsVersion, setPatientsVersion] = useState(0);
  const [selectedAppointmentPatient, setSelectedAppointmentPatient] = useState<Patient | null>(null);
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function restoreSession() {
      const token = await refreshAccessToken();
      if (!token) { if (mounted) setLoading(false); return; }
      try { const response = await api.get<User>("/auth/me"); if (mounted) setUser(response.data); }
      catch { setAccessToken(null); }
      finally { if (mounted) setLoading(false); }
    }
    void restoreSession();
    return () => { mounted = false; };
  }, []);

  async function signIn(credentials: LoginCredentials) {
    setUser(await authenticate(credentials));
  }

  async function signOut() { await logoutSession(); setUser(null); setView("dashboard"); setSelectedAppointmentPatient(null); setSelectedAppointment(null); }
  function schedulePatient(patient: Patient) { setSelectedAppointmentPatient(patient); setView("appointments"); }
  function attendAppointment(appointment: Appointment) { if (!user?.roles.some((role) => role === "doctor" || role === "admin")) return; setSelectedAppointment(appointment); setView("consultation"); }

  if (loading) return <SessionLoading />;
  if (!user) return <Login onSignIn={signIn} />;

  const isDoctor = user.roles.includes("doctor");
  const isAdmin = user.roles.includes("admin");
  const isSecretary = user.roles.includes("secretary");
  const canAccessClinical = isDoctor;

  return <main className="min-h-screen bg-slate-100 text-slate-900"><header className="border-b bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-teal-700">Consultorio Médico</p><h1 className="text-lg font-bold">Sistema de gestión</h1></div><div className="flex items-center gap-3"><NotificationBell onOpenNotifications={() => setView("dashboard")} /><div className="hidden text-right sm:block"><p className="text-sm font-semibold">{user.full_name}</p><p className="text-xs text-slate-500">{user.specialty_names?.length ? user.specialty_names.join(" · ") : user.roles.join(", ")}</p></div><button onClick={() => void signOut()} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">Cerrar sesión</button></div></div></header><div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-6 md:flex-row"><aside className="w-full rounded-xl border bg-white p-3 shadow-sm md:w-56 md:self-start"><button onClick={() => setView("dashboard")} className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "dashboard" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🏠 Dashboard</button><button onClick={() => { setSelectedAppointmentPatient(null); setView("appointments"); }} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "appointments" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>📅 Agenda</button><button onClick={() => setView("reports")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "reports" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>📊 Reportes de citas</button><button onClick={() => setView("patients")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "patients" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>👤 Pacientes</button>{isDoctor && <button onClick={() => setView("follow-ups")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "follow-ups" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🔔 Seguimientos</button>}{isDoctor && <button onClick={() => setView("availability")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "availability" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🗓️ Mi disponibilidad</button>}{(isDoctor || isSecretary) && <button onClick={() => setView("clinical-coverages")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "clinical-coverages" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🩺 Cobertura clínica</button>}{isAdmin && <><button onClick={() => setView("users")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "users" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>👥 Usuarios y roles</button><button onClick={() => setView("care-context")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "care-context" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🏥 Localidades y centros</button></>}</aside><section className="min-w-0 flex-1">{view === "patients" ? <Patients user={user} onBack={() => setView("dashboard")} onPatientChanged={() => setPatientsVersion((value) => value + 1)} onScheduleAppointment={schedulePatient} /> : view === "appointments" ? <Appointments user={user} onBack={() => setView("dashboard")} initialPatient={selectedAppointmentPatient} canAccessClinical={canAccessClinical} onAttendAppointment={attendAppointment} /> : view === "consultation" && selectedAppointment && canAccessClinical ? <Consultation appointment={selectedAppointment} onBack={() => setView("appointments")} /> : view === "clinical-coverages" && (isDoctor || isSecretary) ? <ClinicalCoverages user={user} onBack={() => setView("dashboard")} /> : view === "reports" ? <AppointmentReports onBack={() => setView("dashboard")} /> : view === "care-context" ? <CareContext onBack={() => setView("dashboard")} /> : view === "availability" ? <DoctorAvailability onBack={() => setView("dashboard")} /> : view === "users" ? <Users currentUser={user} onCurrentUserChanged={setUser} onBack={() => setView("dashboard")} /> : view === "follow-ups" && isDoctor ? <FollowUps user={user} onBack={() => setView("dashboard")} /> : <Dashboard user={user} patientsVersion={patientsVersion} />}</section></div></main>;
}

export default App;
