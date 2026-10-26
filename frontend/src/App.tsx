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
import type {ClinicalFollowUp} from "./components/FollowUpInbox";
import Consultation from "./pages/Consultation";
import ClinicalCoverages from "./pages/ClinicalCoverages";
import NotificationBell from "./components/NotificationBell";
import type { Patient } from "./types/patient";
import type { Appointment } from "./types/appointment";
import type { User } from "./types/user";
import Platform from "./pages/Platform";
import DocumentPersonalization from "./pages/DocumentPersonalization";
import AgentDevices from "./pages/AgentDevices";
import PrintManagement from "./pages/PrintManagement";
import WorkspacePersonalization from "./pages/WorkspacePersonalization";
import { getDashboardWidgets, getDefaultDashboardWidgetOrder, normalizeDashboardWidgetOrder } from "./components/dashboard/dashboardModel";
import { defaultUserPreferences, getUserPreferences, putUserPreferences, type UserPreferences } from "./services/userPreferences";

import { AtlasAppShell } from "./layouts/AtlasAppShell";
import { getDefaultFinanceSection, getDefaultGestionOrder, getFinanceNavigationGroups, getNavigationItems, normalizeGestionOrder, type AccentTheme, type AppView, type FinanceSection, type NavigationGuard, type NavigationGuardRegistrar } from "./navigation/navigation";
import "./layouts/operational-shell.css";

const Finance = lazy(() => import("./pages/Finance"));

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionMessage, setSessionMessage] = useState("");
  const [view, setView] = useState<AppView>("dashboard");
  const [financeSection, setFinanceSection] = useState<FinanceSection>(0);
  const [preferenceDraft, setPreferenceDraft] = useState<UserPreferences | null>(null);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [preferencesError, setPreferencesError] = useState("");
  const [preferencesSaved, setPreferencesSaved] = useState(false);
  const preferenceEpochRef = useRef(0);
  const [patientsVersion, setPatientsVersion] = useState(0);
  const [selectedAppointmentPatient, setSelectedAppointmentPatient] = useState<Patient | null>(null);
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);
  const [createAppointment, setCreateAppointment] = useState(false);
  const [selectedFollowUp,setSelectedFollowUp]=useState<ClinicalFollowUp|null>(null);
  async function scheduleFollowUp(task:ClinicalFollowUp){
    try{const {data}=await api.get<Patient>(`/patients/${task.patient_id}`);setSelectedAppointmentPatient(data);setSelectedFollowUp(task);setCreateAppointment(true);setView("appointments");}
    catch{window.alert("No fue posible preparar la cita de retorno. Verifique su alcance de paciente y agenda.");}
  }
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
    const expired = (event: Event) => { preferenceEpochRef.current += 1; setSessionMessage((event as CustomEvent<string>).detail || "Su sesión terminó. Vuelva a iniciar sesión."); setAccessToken(null); setUser(null); setPreferenceDraft(null); setPreferencesSaving(false); setView("dashboard"); setSelectedAppointment(null); setSelectedAppointmentPatient(null); navigationGuardRef.current = null; };
    window.addEventListener("atlas-session-expired", expired);
    return () => window.removeEventListener("atlas-session-expired", expired);
  }, []);

  useEffect(() => {
    preferenceEpochRef.current += 1;
    if (!user || user.access_scope === "platform") { setPreferenceDraft(null); setPreferencesLoading(false); return; }
    let active = true;
    setPreferenceDraft(null);
    setPreferencesLoading(true);
    setPreferencesSaving(false);
    setPreferencesError("");
    setPreferencesSaved(false);
    void getUserPreferences().then(data => { if (active) setPreferenceDraft(data); })
      .catch(() => { if (active) setPreferencesError("No fue posible cargar las preferencias de tu cuenta. El orden actual no está sincronizado."); })
      .finally(() => { if (active) setPreferencesLoading(false); });
    return () => { active = false; };
  }, [user?.id, user?.access_scope]);

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
    const authenticated = await authenticate(credentials);
    preferenceEpochRef.current += 1;
    setPreferenceDraft(null);
    setPreferencesSaving(false);
    setUser(authenticated);
    setSessionMessage("");
  }

  async function completeSignOut() { preferenceEpochRef.current += 1; await logoutSession(); setUser(null); setPreferenceDraft(null); setPreferencesSaving(false); setView("dashboard"); setSelectedAppointmentPatient(null); setSelectedAppointment(null); }
  function signOut() { requestNavigation(() => { void completeSignOut(); }); }
  function schedulePatient(patient: Patient) { setSelectedFollowUp(null);setSelectedAppointmentPatient(patient); setView("appointments"); }
  function attendAppointment(appointment: Appointment) { if (!user?.roles.some((role) => role === "doctor")) return; setSelectedAppointment(appointment); setView("consultation"); }

  if (loading) return <SessionLoading />;
  if (!user) return <Login onSignIn={signIn} sessionMessage={sessionMessage} />;
  if (user.access_scope === "platform") return <Platform user={user} onSignOut={signOut} />;

  const currentUser = user;
  const isDoctor = currentUser.roles.includes("doctor");
  const isAdmin = currentUser.roles.includes("admin");
  const isSecretary = currentUser.roles.includes("secretary");
  const canAccessClinical = isDoctor && (!currentUser.permissions || currentUser.permissions.includes("clinical:access"));
  const visibleNavigationItems = getNavigationItems(currentUser);
  const currentPersonalization = preferenceDraft ?? defaultUserPreferences();
  const gestionOrder = normalizeGestionOrder(visibleNavigationItems, currentPersonalization.gestion_menu_order);
  const dashboardWidgets = getDashboardWidgets(currentUser);
  const dashboardOrder = normalizeDashboardWidgetOrder(dashboardWidgets.map(widget => widget.id), currentPersonalization.dashboard_widget_order);

  function updatePreferenceDraft(update: Partial<UserPreferences>) {
    setPreferenceDraft(current => ({ ...(current ?? defaultUserPreferences()), ...update }));
    setPreferencesSaved(false);
  }

  async function savePreferences() {
    if (preferencesLoading || preferencesSaving) return;
    const epoch = preferenceEpochRef.current;
    const payload: UserPreferences = {
      gestion_menu_order: gestionOrder,
      dashboard_widget_order: dashboardOrder,
      accent_theme: currentPersonalization.accent_theme,
    };
    setPreferencesSaving(true);
    setPreferencesError("");
    setPreferencesSaved(false);
    try { const saved = await putUserPreferences(payload); if (epoch === preferenceEpochRef.current) { setPreferenceDraft(saved); setPreferencesSaved(true); } }
    catch { if (epoch === preferenceEpochRef.current) setPreferencesError("No fue posible guardar las preferencias. Tus cambios aún no están sincronizados."); }
    finally { if (epoch === preferenceEpochRef.current) setPreferencesSaving(false); }
  }

  function navigate(nextView: AppView) {
    requestNavigation(() => {
      setCreateAppointment(false);
      setSelectedFollowUp(null);
      if (nextView === "finance" && user) setFinanceSection(getDefaultFinanceSection(user));
      // Agenda from navigation starts without the patient preselected by Patients.
      if (nextView === "appointments") setSelectedAppointmentPatient(null);
      setView(nextView);
    });
  }

  function navigateFinanceSection(section: FinanceSection) {
    if (!user || !getFinanceNavigationGroups(user).some(group => group.sections.some(option => option.index === section))) return;
    requestNavigation(() => {
      setCreateAppointment(false);
      setSelectedFollowUp(null);
      setFinanceSection(section);
      setView("finance");
    });
  }

  const titles: Record<AppView, string> = { finance: "Finanzas", insurance: "Aseguradoras / ARS", security: "Seguridad", dashboard: "Inicio", patients: "Pacientes", appointments: "Agenda", reports: "Reportes de citas", "care-context": "Localidades y centros", availability: "Mi disponibilidad", users: "Usuarios y roles", "follow-ups": "Seguimientos", consultation: "Consulta", "clinical-coverages": "Cobertura clínica", documents: "Documentos", personalization: "Mi espacio de trabajo", "agent-devices": "Agentes y dispositivos", "print-management": "Gestión de impresión" };
  return <AtlasAppShell user={user} pageTitle={view === "agent-devices" ? "Agentes y dispositivos" : titles[view]}
    activeView={view === "consultation" ? "appointments" : view}
    activeFinanceSection={financeSection} gestionOrder={gestionOrder} accentTheme={currentPersonalization.accent_theme} onNavigate={navigate} onNavigateFinanceSection={navigateFinanceSection} onSignOut={signOut}
    notifications={<NotificationBell onOpenNotifications={() => navigate("dashboard")} />}>
    <ReauthenticationDialog />
    {view === "agent-devices" && user.permissions?.includes("local_agents:view") ? <AgentDevices user={user} /> : null}
    {view === "print-management" && user.permissions?.includes("local_agents:view") ? <PrintManagement user={user} /> : null}
    {view !== "agent-devices" && view !== "print-management" && <div className={`atlas-operational-workspace${view === "appointments" ? " atlas-operational-workspace--agenda" : view === "patients" ? " atlas-operational-workspace--patients" : view === "dashboard" ? " atlas-operational-workspace--dashboard" : ""}`}>
      {view === "finance" ? <Suspense fallback={<p role="status">Cargando Finanzas…</p>}><Finance user={user} section={financeSection} onSectionChange={navigateFinanceSection} /></Suspense> : view === "insurance" && user.permissions?.includes("users:manage") ? <InsuranceCatalog /> : view === "security" ? <AdministrationSecurity user={user} /> : view === "personalization" ? <WorkspacePersonalization modules={visibleNavigationItems} gestionOrder={gestionOrder} onGestionOrderChange={order => updatePreferenceDraft({ gestion_menu_order: order })} onResetGestionOrder={() => updatePreferenceDraft({ gestion_menu_order: getDefaultGestionOrder() })} dashboardWidgets={dashboardWidgets} dashboardOrder={dashboardOrder} onDashboardOrderChange={order => updatePreferenceDraft({ dashboard_widget_order: order })} onResetDashboard={() => updatePreferenceDraft({ dashboard_widget_order: getDefaultDashboardWidgetOrder() })} accentTheme={currentPersonalization.accent_theme} onAccentThemeChange={(accent_theme: AccentTheme) => updatePreferenceDraft({ accent_theme })} onResetAll={() => { setPreferenceDraft(defaultUserPreferences()); setPreferencesSaved(false); }} onSave={() => void savePreferences()} loading={preferencesLoading} saving={preferencesSaving} error={preferencesError} saved={preferencesSaved} /> : view === "documents" && (user.permissions?.includes("documents:manage") || user.permissions?.includes("users:manage")) ? <DocumentPersonalization user={user} /> : view === "patients" ? <Patients user={user} onBack={() => setView("dashboard")} onPatientChanged={() => setPatientsVersion((value) => value + 1)} onScheduleAppointment={schedulePatient} /> : view === "appointments" ? <Appointments user={user} onBack={() => setView("dashboard")} initialPatient={selectedAppointmentPatient} initialCreate={createAppointment} initialFollowUp={selectedFollowUp} canAccessClinical={canAccessClinical} onAttendAppointment={attendAppointment} /> : view === "consultation" && selectedAppointment && canAccessClinical ? <Consultation appointment={selectedAppointment} onBack={() => setView("appointments")} registerNavigationGuard={registerNavigationGuard} /> : view === "clinical-coverages" && (isDoctor || isSecretary) ? <ClinicalCoverages user={user} onBack={() => setView("dashboard")} /> : view === "reports" ? <AppointmentReports onBack={() => setView("dashboard")} /> : view === "care-context" ? <CareContext onBack={() => setView("dashboard")} /> : view === "availability" ? <DoctorAvailability onBack={() => setView("dashboard")} /> : view === "users" ? <Users currentUser={user} onCurrentUserChanged={setUser} onBack={() => setView("dashboard")} /> : view === "follow-ups" && (isDoctor || isSecretary) ? <FollowUps user={user} onBack={() => setView("dashboard")} onSchedule={scheduleFollowUp} /> : <Dashboard user={user} patientsVersion={patientsVersion} widgetOrder={dashboardOrder} onNavigate={navigate} onNewAppointment={() => { setSelectedAppointmentPatient(null); setCreateAppointment(true); setView("appointments"); }} />}
    </div>}
  </AtlasAppShell>;
}

export default App;
