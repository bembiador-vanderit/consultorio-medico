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

import { AtlasAppShell } from "./layouts/AtlasAppShell";
import type { AppView } from "./navigation/navigation";
import "./layouts/operational-shell.css";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<AppView>("dashboard");
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

  function navigate(nextView: AppView) {
    // Agenda from navigation starts without the patient preselected by Patients.
    if (nextView === "appointments") setSelectedAppointmentPatient(null);
    setView(nextView);
  }

  return <AtlasAppShell user={user} pageTitle="Espacio de trabajo"
    activeView={view === "consultation" ? "appointments" : view}
    onNavigate={navigate} onSignOut={() => void signOut()}
    notifications={<NotificationBell onOpenNotifications={() => setView("dashboard")} />}>
    <div className="atlas-operational-workspace">
      {view === "patients" ? <Patients user={user} onBack={() => setView("dashboard")} onPatientChanged={() => setPatientsVersion((value) => value + 1)} onScheduleAppointment={schedulePatient} /> : view === "appointments" ? <Appointments user={user} onBack={() => setView("dashboard")} initialPatient={selectedAppointmentPatient} canAccessClinical={canAccessClinical} onAttendAppointment={attendAppointment} /> : view === "consultation" && selectedAppointment && canAccessClinical ? <Consultation appointment={selectedAppointment} onBack={() => setView("appointments")} /> : view === "clinical-coverages" && (isDoctor || isSecretary) ? <ClinicalCoverages user={user} onBack={() => setView("dashboard")} /> : view === "reports" ? <AppointmentReports onBack={() => setView("dashboard")} /> : view === "care-context" ? <CareContext onBack={() => setView("dashboard")} /> : view === "availability" ? <DoctorAvailability onBack={() => setView("dashboard")} /> : view === "users" ? <Users currentUser={user} onCurrentUserChanged={setUser} onBack={() => setView("dashboard")} /> : view === "follow-ups" && isDoctor ? <FollowUps user={user} onBack={() => setView("dashboard")} /> : <Dashboard user={user} patientsVersion={patientsVersion} onNavigate={navigate} />}
    </div>
  </AtlasAppShell>;
}

export default App;
