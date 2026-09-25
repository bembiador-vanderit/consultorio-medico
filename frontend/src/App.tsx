import InsuranceCatalog from "./pages/InsuranceCatalog";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { authenticate, type LoginCredentials } from "./services/login";
import Login, { SessionLoading } from "./pages/Login";
import { api, logoutSession, refreshAccessToken, setAccessToken } from "./services/api";
import Dashboard from "./pages/Dashboard";
import Patients from "./pages/Patients";
import Appointments from "./pages/Appointments";
import AppointmentReports from "./pages/AppointmentReports";
import CareContext from "./pages/CareContext";
import DoctorAvailability from "./pages/DoctorAvailability";
import ReauthenticationDialog from "./components/ReauthenticationDialog";
import AdministrationSecurity from "./pages/AdministrationSecurity";
import Users from "./pages/Users";
import FollowUps from "./pages/FollowUps";
import Consultation from "./pages/Consultation";
import ClinicalCoverages from "./pages/ClinicalCoverages";
import NotificationBell from "./components/NotificationBell";
import type { Patient } from "./types/patient";
import type { Appointment } from "./types/appointment";
import type { User } from "./types/user";
import Platform from "./pages/Platform";

import { AtlasAppShell } from "./layouts/AtlasAppShell";
import type { AppView, NavigationGuard, NavigationGuardRegistrar } from "./navigation/navigation";
import "./layouts/operational-shell.css";

const Finance = lazy(() => import("./pages/Finance"));

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionMessage, setSessionMessage] = useState("");
  const [view, setView] = useState<AppView>("dashboard");
  const [patientsVersion, setPatientsVersion] = useState(0);
  const [selectedAppointmentPatient, setSelectedAppointmentPatient] = useState<Patient | null>(null);
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);
  const [createAppointment, setCreateAppointment] = useState(false);
  const [loading, setLoading] = useState(true);
  const navigationGuardRef = useRef<NavigationGuard | null>(null);

  const registerNavigationGuard: NavigationGuardRegistrar = useCallback((guard) => {
    navigationGuardRef.current = guard;
  }, []);

  function requestNavigation(proceed: () => void) {
    const guard = navigationGuardRef.current;
    if (guard) guard(proceed);
    else proceed();
  }

  useEffect(() => {
    const expired = (event: Event) => { setSessionMessage((event as CustomEvent<string>).detail || "Su sesión terminó. Vuelva a iniciar sesión."); setAccessToken(null); setUser(null); setView("dashboard"); setSelectedAppointment(null); setSelectedAppointmentPatient(null); navigationGuardRef.current = null; };
    window.addEventListener("atlas-session-expired", expired);
    return () => window.removeEventListener("atlas-session-expired", expired);
  }, []);

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
    setSessionMessage("");
  }

  async function completeSignOut() { await logoutSession(); setUser(null); setView("dashboard"); setSelectedAppointmentPatient(null); setSelectedAppointment(null); }
  function signOut() { requestNavigation(() => { void completeSignOut(); }); }
  function schedulePatient(patient: Patient) { setSelectedAppointmentPatient(patient); setView("appointments"); }
  function attendAppointment(appointment: Appointment) { if (!user?.roles.some((role) => role === "doctor")) return; setSelectedAppointment(appointment); setView("consultation"); }

  if (loading) return <SessionLoading />;
  if (!user) return <Login onSignIn={signIn} sessionMessage={sessionMessage} />;
  if (user.access_scope === "platform") return <Platform user={user} onSignOut={signOut} />;

  const isDoctor = user.roles.includes("doctor");
  const isAdmin = user.roles.includes("admin");
  const isSecretary = user.roles.includes("secretary");
  const canAccessClinical = isDoctor && (!user.permissions || user.permissions.includes("clinical:access"));

  function navigate(nextView: AppView) {
    requestNavigation(() => {
      setCreateAppointment(false);
      // Agenda from navigation starts without the patient preselected by Patients.
      if (nextView === "appointments") setSelectedAppointmentPatient(null);
      setView(nextView);
    });
  }

  const titles: Record<AppView, string> = { finance: "Finanzas", insurance: "Aseguradoras / ARS", security: "Seguridad", dashboard: "Inicio", patients: "Pacientes", appointments: "Agenda", reports: "Reportes de citas", "care-context": "Localidades y centros", availability: "Mi disponibilidad", users: "Usuarios y roles", "follow-ups": "Seguimientos", consultation: "Consulta", "clinical-coverages": "Cobertura clínica" };
  return <AtlasAppShell user={user} pageTitle={titles[view]}
    activeView={view === "consultation" ? "appointments" : view}
    onNavigate={navigate} onSignOut={signOut}
    notifications={<NotificationBell onOpenNotifications={() => navigate("dashboard")} />}>
    <ReauthenticationDialog />
    <div className={`atlas-operational-workspace${view === "appointments" ? " atlas-operational-workspace--agenda" : view === "patients" ? " atlas-operational-workspace--patients" : view === "dashboard" ? " atlas-operational-workspace--dashboard" : ""}`}>
      {view === "finance" ? <Suspense fallback={<p role="status">Cargando Finanzas…</p>}><Finance user={user} /></Suspense> : view === "insurance" && user.permissions?.includes("users:manage") ? <InsuranceCatalog /> : view === "security" ? <AdministrationSecurity user={user} /> : view === "patients" ? <Patients user={user} onBack={() => setView("dashboard")} onPatientChanged={() => setPatientsVersion((value) => value + 1)} onScheduleAppointment={schedulePatient} /> : view === "appointments" ? <Appointments user={user} onBack={() => setView("dashboard")} initialPatient={selectedAppointmentPatient} initialCreate={createAppointment} canAccessClinical={canAccessClinical} onAttendAppointment={attendAppointment} /> : view === "consultation" && selectedAppointment && canAccessClinical ? <Consultation appointment={selectedAppointment} onBack={() => setView("appointments")} registerNavigationGuard={registerNavigationGuard} /> : view === "clinical-coverages" && (isDoctor || isSecretary) ? <ClinicalCoverages user={user} onBack={() => setView("dashboard")} /> : view === "reports" ? <AppointmentReports onBack={() => setView("dashboard")} /> : view === "care-context" ? <CareContext onBack={() => setView("dashboard")} /> : view === "availability" ? <DoctorAvailability onBack={() => setView("dashboard")} /> : view === "users" ? <Users currentUser={user} onCurrentUserChanged={setUser} onBack={() => setView("dashboard")} /> : view === "follow-ups" && isDoctor ? <FollowUps user={user} onBack={() => setView("dashboard")} /> : <Dashboard user={user} patientsVersion={patientsVersion} onNavigate={navigate} onNewAppointment={() => { setSelectedAppointmentPatient(null); setCreateAppointment(true); setView("appointments"); }} />}
    </div>
  </AtlasAppShell>;
}

export default App;
