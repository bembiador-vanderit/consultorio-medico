import { FormEvent, useState } from "react";
import { AxiosError } from "axios";
import { api, setAccessToken } from "./services/api";

type User = { full_name: string; roles: string[] };

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError("");
    try {
      const { data } = await api.post<{ access_token: string }>("/auth/login", { email, password });
      setAccessToken(data.access_token);
      const profile = await api.get<User>("/auth/me");
      setUser(profile.data);
      setPassword("");
    } catch (reason) {
      setAccessToken(null);
      setError(reason instanceof AxiosError && reason.response?.status === 401 ? "Correo o contraseña incorrectos." : "No fue posible iniciar sesión. Intente nuevamente.");
    } finally { setLoading(false); }
  }

  if (user) return <main className="min-h-screen bg-slate-50 p-6 text-slate-900"><section className="mx-auto max-w-4xl rounded-xl bg-white p-8 shadow-sm"><p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Consultorio Médico</p><h1 className="mt-3 text-3xl font-bold">Bienvenido, {user.full_name}</h1><p className="mt-3 text-slate-600">Sesión iniciada como: {user.roles.join(", ")}.</p><button className="mt-8 rounded bg-slate-900 px-4 py-2 text-white" onClick={() => { setAccessToken(null); setUser(null); }}>Cerrar sesión</button></section></main>;

  return <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-slate-900"><form onSubmit={signIn} className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm"><p className="text-sm font-semibold uppercase tracking-widest text-teal-700">Consultorio Médico</p><h1 className="mt-3 text-3xl font-bold">Iniciar sesión</h1><p className="mt-2 text-sm text-slate-600">Acceso exclusivo para personal autorizado.</p>{error && <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}<label className="mt-6 block text-sm font-medium">Correo<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded border border-slate-300 p-2" /></label><label className="mt-4 block text-sm font-medium">Contraseña<input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded border border-slate-300 p-2" /></label><button disabled={loading} className="mt-6 w-full rounded bg-teal-700 p-2 font-medium text-white disabled:opacity-60">{loading ? "Ingresando…" : "Ingresar"}</button></form></main>;
}
export default App;
