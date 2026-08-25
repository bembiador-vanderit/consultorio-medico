import { FormEvent, useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";

type Props = { onBack: () => void };
type RoleCode = "admin" | "doctor" | "secretary";

const roles: { code: RoleCode; label: string; description: string }[] = [
  { code: "doctor", label: "Médico", description: "Acceso clínico y disponibilidad" },
  { code: "secretary", label: "Secretaria", description: "Gestión de pacientes y agenda" },
  { code: "admin", label: "Administrador", description: "Configuración y administración" },
];

export default function Users({ onBack }: Props) {
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "doctor" as RoleCode });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadUsers() {
    setLoading(true); setError("");
    try { const { data } = await api.get<User[]>("/users"); setUsers(data); }
    catch (err: any) { setError(err?.response?.data?.detail || "No fue posible cargar los usuarios."); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadUsers(); }, []);

  async function createUser(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setMessage("");
    try {
      await api.post<User>("/users", {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        role_codes: [form.role],
      });
      setForm({ full_name: "", email: "", password: "", role: "doctor" });
      setMessage("Usuario creado correctamente.");
      await loadUsers();
    } catch (err: any) { setError(err?.response?.data?.detail || "No fue posible crear el usuario."); }
    finally { setSaving(false); }
  }

  return <section>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button><h2 className="mt-2 text-2xl font-bold">Usuarios y roles</h2><p className="mt-1 text-sm text-slate-500">Cree las cuentas del personal y determine su rol inicial.</p></div>
    </div>
    {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {message && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
      <form onSubmit={createUser} className="rounded-xl border bg-white p-5 shadow-sm">
        <h3 className="font-semibold">Crear usuario</h3>
        <label className="mt-4 block text-sm font-medium">Nombre completo<input required minLength={2} value={form.full_name} onChange={e=>setForm({...form,full_name:e.target.value})} className="mt-1 w-full rounded-lg border p-2.5" /></label>
        <label className="mt-3 block text-sm font-medium">Correo electrónico<input required type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} className="mt-1 w-full rounded-lg border p-2.5" /></label>
        <label className="mt-3 block text-sm font-medium">Contraseña inicial<input required minLength={12} type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} className="mt-1 w-full rounded-lg border p-2.5" /><span className="mt-1 block text-xs text-slate-500">Mínimo 12 caracteres.</span></label>
        <label className="mt-3 block text-sm font-medium">Rol<select value={form.role} onChange={e=>setForm({...form,role:e.target.value as RoleCode})} className="mt-1 w-full rounded-lg border p-2.5">{roles.map(role=><option key={role.code} value={role.code}>{role.label}</option>)}</select></label>
        <button disabled={saving} className="mt-5 w-full rounded-lg bg-teal-700 px-4 py-2.5 font-medium text-white disabled:opacity-50">{saving ? "Creando..." : "Crear usuario"}</button>
      </form>

      <div className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><div><h3 className="font-semibold">Usuarios registrados</h3><p className="text-xs text-slate-500">Las cuentas creadas aquí podrán utilizarse en Agenda y asignarse a centros.</p></div><button onClick={()=>void loadUsers()} className="rounded-lg border px-3 py-2 text-sm">Actualizar</button></div>
        <div className="mt-4 overflow-x-auto">{loading ? <p className="py-6 text-slate-500">Cargando usuarios...</p> : users.length === 0 ? <p className="py-6 text-slate-500">No hay usuarios registrados.</p> : <table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-3 py-3">Usuario</th><th className="px-3 py-3">Rol</th><th className="px-3 py-3">Estado</th></tr></thead><tbody className="divide-y">{users.map(user=><tr key={user.id}><td className="px-3 py-3"><div className="font-medium">{user.full_name}</div><div className="text-xs text-slate-500">{user.email}</div></td><td className="px-3 py-3"><div className="flex flex-wrap gap-1">{user.roles.map(code=><span key={code} className="rounded-full bg-slate-100 px-2 py-1 text-xs">{roles.find(role=>role.code===code)?.label ?? code}</span>)}</div></td><td className="px-3 py-3">{user.is_active ? <span className="text-emerald-700">Activo</span> : <span className="text-red-700">Inactivo</span>}</td></tr>)}</tbody></table>}</div>
      </div>
    </div>
  </section>;
}
