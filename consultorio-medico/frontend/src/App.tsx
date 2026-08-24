import { FormEvent, useEffect, useState } from "react";
import { AxiosError } from "axios";
import { api, logoutSession, refreshAccessToken, setAccessToken } from "./services/api";
import Dashboard from "./pages/Dashboard";
import Patients from "./pages/Patients";
import type { User } from "./types/user";

type View = "dashboard" | "patients";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [patientsVersion, setPatientsVersion] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function restoreSession() {
      const token = await refreshAccessToken();
      if (!token) {
        if (mounted) setLoading(false);
        return;
      }

      try {
        const { data } = await api.get<User>("/auth/me");
        if (mounted) setUser(data);
      } catch {
        setAccessToken(null);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    void restoreSession();
    return () => { mounted = false; };
  }, []);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post<{ access_token: string }>("/auth/login", { email, password });
      setAccessToken(data.access_token);
      const profile = await api.get<User>("/auth/me");
      setUser(profile.data);
      setPassword("");
    } catch (reason) {
      console.error(reason);
      setAccessToken(null);
      setError(reason instanceof AxiosError && reason.response?.status === 401
        ? "Correo o contraseña incorrectos."
        : "No fue posible iniciar sesión. Intente nuevamente.");
    } finally {
      setLoading(false);
    }
  }

  async function signOut() {
    await logoutSession();
    setUser(null);
    setView("dashboard");
  }

  if (loading) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-100 text-slate-600"><p>Comprobando sesión...</p></main>;
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6 text-slate-900">
        <form onSubmit={signIn} className="w-full max-w-md rounded-2xl bg-white p-8 shadow-lg">
          <p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Consultorio Médico</p>
          <h1 className="mt-3 text-3xl font-bold">Iniciar sesión</h1>
          <p className="mt-2 text-sm text-slate-600">Acceso exclusivo para personal autorizado.</p>
          {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <label className="mt-6 block text-sm font-medium">Correo
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2.5" />
          </label>
          <label className="mt-4 block text-sm font-medium">Contraseña
            <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2.5" />
          </label>
          <button type="submit" disabled={loading} className="mt-6 w-full rounded-lg bg-teal-700 p-2.5 font-medium text-white hover:bg-teal-800 disabled:opacity-60">
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">Consultorio Médico</p>
            <h1 className="text-lg font-bold">Sistema de gestión</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold">{user.full_name}</p>
              <p className="text-xs text-slate-500">{user.roles.join(", ")}</p>
            </div>
            <button onClick={() => void signOut()} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">Cerrar sesión</button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-6 md:flex-row">
        <aside className="w-full rounded-xl border bg-white p-3 shadow-sm md:w-56 md:self-start">
          <button onClick={() => setView("dashboard")} className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "dashboard" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>🏠 Dashboard</button>
          <button onClick={() => setView("patients")} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${view === "patients" ? "bg-teal-50 text-teal-800" : "hover:bg-slate-50"}`}>👤 Pacientes</button>
          {user.roles.includes("admin") && <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">Administración</div>}
        </aside>

        <section className="min-w-0 flex-1">
          {view === "patients"
            ? <Patients onBack={() => setView("dashboard")} onPatientChanged={() => setPatientsVersion((value) => value + 1)} />
            : <Dashboard user={user} patientsVersion={patientsVersion} />}
        </section>
      </div>
    </main>
  );
}

export default App;
