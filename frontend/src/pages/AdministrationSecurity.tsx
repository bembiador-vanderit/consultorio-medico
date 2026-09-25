import { useEffect, useState } from "react";
import { api, logoutSession } from "../services/api";
import type { User } from "../types/user";
import AccessSchedules from "../components/AccessSchedules";

type Transfer = { id: number; initiator_id: number; target_id: number; initiator_name?: string; target_name?: string; replace_initiator: boolean; expires_at: string };
type Audit = { id: number; actor_id: number; action: string; outcome: string; created_at: string };
const capabilities = [{ code: "finance:read", label: "Consultar finanzas" }, { code: "finance:collect", label: "Caja y cobros" }, { code: "finance:manage", label: "Ajustes, reversos y anulaciones" }, { code: "insurance:manage", label: "Seguros y coberturas administrativas" }, { code: "patients:access", label: "Pacientes, agenda y reportes" }, { code: "clinical:access", label: "Trabajo clínico (requiere rol médico)" }];

export default function AdministrationSecurity({ user }: { user: User }) {
  const admin = user.roles.includes("admin");
  const [users, setUsers] = useState<User[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [target, setTarget] = useState("");
  const [replace, setReplace] = useState(true);
  const [restricted, setRestricted] = useState("");
  const [denied, setDenied] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  async function load() {
    const response = await api.get<Transfer[]>("/administration/transfers"); setTransfers(response.data);
    if (admin) {
      const [people, history] = await Promise.all([api.get<User[]>("/users"), api.get<Audit[]>(`/administration/audit?offset=${offset}&limit=20`)]);
      setUsers(people.data); setAudits(history.data);
    }
  }
  useEffect(() => { void load().catch(reason => setError(reason.response?.data?.detail || "No se pudo cargar la seguridad.")); }, [offset]);
  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); setMessage(success); await load(); }
    catch (reason: any) { setError(reason.response?.data?.detail || reason.message || "No se pudo completar la operación."); }
    finally { setBusy(false); }
  }
  const name = (id: number) => users.find(person => person.id === id)?.full_name || `Usuario ${id}`;
  return <section className="space-y-5">
    <h2 className="text-2xl font-bold">Seguridad y administración</h2>
    {admin && <AccessSchedules users={users} />}
    <p>El administrador gestiona todos los centros de esta instalación. El acceso clínico requiere un rol médico y una relación asistencial autorizada.</p>
    <p>La verificación en dos pasos (MFA) y la recuperación automática de cuenta todavía no están habilitadas.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}{message && <p role="status" className="text-teal-800">{message}</p>}
    {admin && <form className="space-y-3 rounded-xl border bg-white p-5" onSubmit={event => { event.preventDefault(); void run(() => api.post("/administration/transfers", { target_id: Number(target), replace_initiator: replace }), "Solicitud creada. El destinatario debe entrar a Seguridad y aceptar en 24 horas."); }}>
      <h3 className="font-bold">Cambio de administrador</h3>
      <label className="block">Destinatario<select required value={target} onChange={event => setTarget(event.target.value)} className="ml-3 rounded border p-2"><option value="">Seleccione…</option>{users.filter(person => person.is_active && !person.roles.includes("admin")).map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      <label className="block"><input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} /> Transferir mi administración y retirarme ese rol al aceptar</label>
      <p>{replace ? "Conservará sus otros roles. Si no tiene otros, quedará sin permisos operativos." : "El destinatario será un administrador adicional de toda la instalación."}</p>
      <button disabled={busy || !target} className="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50">Solicitar confirmación</button>
    </form>}
    <div className="space-y-3 rounded-xl border bg-white p-5"><h3 className="font-bold">Solicitudes pendientes</h3>{!transfers.length && <p>No hay solicitudes pendientes.</p>}
      {transfers.map(item => <div key={item.id} className="rounded border p-3"><p>{item.initiator_name || name(item.initiator_id)} → {item.target_name || name(item.target_id)} · {item.replace_initiator ? "Transferencia" : "Administrador adicional"}</p><p>Vence: {new Date(item.expires_at + "Z").toLocaleString()}</p>
        {item.target_id === user.id && <button disabled={busy} className="mr-3 rounded bg-teal-700 p-2 text-white" onClick={() => void run(async () => { await api.post(`/administration/transfers/${item.id}/accept`); await logoutSession(); window.location.reload(); }, "Solicitud aceptada. Vuelva a iniciar sesión.")}>Aceptar administración</button>}
        <button disabled={busy} className="rounded border p-2" onClick={() => void run(() => api.post(`/administration/transfers/${item.id}/cancel`), "Solicitud cancelada.")}>Cancelar solicitud</button></div>)}
    </div>
    {admin && <form className="space-y-3 rounded-xl border bg-white p-5" onSubmit={event => { event.preventDefault(); void run(() => api.put(`/users/${restricted}/permissions`, { denied_permissions: denied }), "Restricciones guardadas; las sesiones anteriores del usuario quedan invalidadas."); }}>
      <h3 className="font-bold">Restricciones individuales</h3><p>Puede retirar capacidades completas. No otorga acceso clínico ni amplía centros o médicos asignados.</p>
      <label>Usuario<select required value={restricted} className="ml-3 rounded border p-2" onChange={event => { setRestricted(event.target.value); setDenied(users.find(person => person.id === Number(event.target.value))?.denied_permissions || []); }}><option value="">Seleccione…</option>{users.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
      {capabilities.map(capability => <label key={capability.code} className="block"><input type="checkbox" checked={denied.includes(capability.code)} onChange={event => setDenied(event.target.checked ? [...denied, capability.code] : denied.filter(code => code !== capability.code))} /> Restringir {capability.label}</label>)}
      <button disabled={busy || !restricted} className="rounded border px-4 py-2">Guardar restricciones</button>
    </form>}
    {admin && <div className="rounded-xl border bg-white p-5"><h3 className="font-bold">Auditoría de seguridad</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>Momento</th><th>Actor</th><th>Operación</th><th>Resultado</th></tr></thead><tbody>{audits.map(item => <tr key={item.id}><td>{new Date(item.created_at + "Z").toLocaleString()}</td><td>{name(item.actor_id)}</td><td>{item.action}</td><td>{item.outcome}</td></tr>)}</tbody></table></div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))} className="mr-4">Anterior</button><button disabled={audits.length < 20} onClick={() => setOffset(offset + 20)}>Siguiente</button></div>}
  </section>;
}
