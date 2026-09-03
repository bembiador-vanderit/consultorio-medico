import { FormEvent, useEffect, useState } from "react";

import { api } from "../services/api";
import type { User } from "../types/user";

type Props = {
  currentUser: User;
  onBack: () => void;
  onCurrentUserChanged: (user: User) => void;
};
type RoleCode = "admin" | "doctor" | "secretary";
type AdminUser = User & { center_ids: number[]; primary_center_id: number | null };
type Center = { id: number; name: string; city: string; is_active: boolean };
type EditForm = {
  full_name: string;
  email: string;
  roles: RoleCode[];
  center_ids: number[];
  primary_center_id: number | null;
};

const roles: { code: RoleCode; label: string; description: string }[] = [
  { code: "doctor", label: "Médico", description: "Acceso clínico y disponibilidad" },
  { code: "secretary", label: "Secretaria", description: "Gestión de pacientes y agenda" },
  { code: "admin", label: "Administrador", description: "Configuración y administración" },
];

function apiError(reason: any, fallback: string) {
  const detail = reason?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg).filter(Boolean).join(" ") || fallback;
  return fallback;
}

function userEditForm(user: AdminUser): EditForm {
  return {
    full_name: user.full_name,
    email: user.email,
    roles: user.roles.filter((role): role is RoleCode => roles.some((item) => item.code === role)),
    center_ids: user.center_ids,
    primary_center_id: user.primary_center_id,
  };
}

export default function Users({ currentUser, onBack, onCurrentUserChanged }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [centers, setCenters] = useState<Center[]>([]);
  const [createForm, setCreateForm] = useState({ full_name: "", email: "", password: "", role: "doctor" as RoleCode });
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [modalError, setModalError] = useState("");
  const [modalMessage, setModalMessage] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [userResponse, centerResponse] = await Promise.all([
        api.get<AdminUser[]>("/users"),
        api.get<Center[]>("/centers"),
      ]);
      setUsers(userResponse.data);
      setCenters(centerResponse.data);
    } catch (reason: any) {
      setError(apiError(reason, "No fue posible cargar los usuarios."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadData(); }, []);

  function applyUpdatedUser(user: AdminUser, successMessage: string) {
    setUsers((current) => current.map((item) => item.id === user.id ? user : item));
    setEditing(user);
    setEditForm(userEditForm(user));
    setModalError("");
    setModalMessage(successMessage);
    if (user.id === currentUser.id) onCurrentUserChanged(user);
  }

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setSaving("create"); setError(""); setMessage("");
    try {
      if (!/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(createForm.password) || !/\d/.test(createForm.password)) {
        throw new Error("La contraseña debe contener al menos una letra y un número.");
      }
      await api.post<AdminUser>("/users", {
        full_name: createForm.full_name.trim(),
        email: createForm.email.trim().toLowerCase(),
        password: createForm.password,
        role_codes: [createForm.role],
      });
      setCreateForm({ full_name: "", email: "", password: "", role: "doctor" });
      setMessage("Usuario creado correctamente.");
      await loadData();
    } catch (reason: any) {
      setError(reason?.response ? apiError(reason, "No fue posible crear el usuario.") : reason.message);
    } finally {
      setSaving("");
    }
  }

  function openEdit(user: AdminUser) {
    setEditing(user);
    setEditForm(userEditForm(user));
    setNewPassword("");
    setConfirmPassword("");
    setModalError("");
    setModalMessage("");
  }

  async function saveProfile() {
    if (!editing || !editForm) return;
    setSaving("profile"); setModalError(""); setModalMessage("");
    try {
      const { data } = await api.patch<AdminUser>(`/users/${editing.id}/profile`, {
        full_name: editForm.full_name.trim(),
        email: editForm.email.trim().toLowerCase(),
      });
      applyUpdatedUser(data, "Datos generales actualizados.");
    } catch (reason: any) { setModalError(apiError(reason, "No fue posible actualizar los datos.")); }
    finally { setSaving(""); }
  }

  async function saveRoles() {
    if (!editing || !editForm) return;
    setSaving("roles"); setModalError(""); setModalMessage("");
    try {
      const { data } = await api.put<AdminUser>(`/users/${editing.id}/roles`, { role_codes: editForm.roles });
      applyUpdatedUser(data, "Roles actualizados.");
    } catch (reason: any) { setModalError(apiError(reason, "No fue posible actualizar los roles.")); }
    finally { setSaving(""); }
  }

  async function saveCenters() {
    if (!editing || !editForm) return;
    setSaving("centers"); setModalError(""); setModalMessage("");
    try {
      const { data } = await api.put<AdminUser>(`/users/${editing.id}/centers`, {
        center_ids: editForm.center_ids,
        primary_center_id: editForm.primary_center_id,
      });
      applyUpdatedUser(data, "Centros actualizados.");
    } catch (reason: any) { setModalError(apiError(reason, "No fue posible actualizar los centros.")); }
    finally { setSaving(""); }
  }

  async function changeStatus() {
    if (!editing) return;
    setSaving("status"); setModalError(""); setModalMessage("");
    try {
      const { data } = await api.put<AdminUser>(`/users/${editing.id}/status`, { is_active: !editing.is_active });
      applyUpdatedUser(data, data.is_active ? "Usuario reactivado." : "Usuario desactivado.");
    } catch (reason: any) { setModalError(apiError(reason, "No fue posible cambiar el estado.")); }
    finally { setSaving(""); }
  }

  async function changePassword() {
    if (!editing) return;
    setModalError(""); setModalMessage("");
    if (newPassword !== confirmPassword) { setModalError("Las contraseñas no coinciden."); return; }
    if (newPassword.length < 12 || !/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(newPassword) || !/\d/.test(newPassword)) {
      setModalError("La contraseña debe tener al menos 12 caracteres, una letra y un número."); return;
    }
    setSaving("password");
    try {
      const { data } = await api.put<AdminUser>(`/users/${editing.id}/password`, { new_password: newPassword });
      applyUpdatedUser(data, "Contraseña cambiada correctamente.");
      setNewPassword(""); setConfirmPassword("");
    } catch (reason: any) { setModalError(apiError(reason, "No fue posible cambiar la contraseña.")); }
    finally { setSaving(""); }
  }

  function toggleRole(role: RoleCode) {
    if (!editForm) return;
    setEditForm({ ...editForm, roles: editForm.roles.includes(role) ? editForm.roles.filter((item) => item !== role) : [...editForm.roles, role] });
  }

  function toggleCenter(centerId: number) {
    if (!editForm) return;
    const assigned = editForm.center_ids.includes(centerId);
    setEditForm({
      ...editForm,
      center_ids: assigned ? editForm.center_ids.filter((id) => id !== centerId) : [...editForm.center_ids, centerId],
      primary_center_id: assigned && editForm.primary_center_id === centerId ? null : editForm.primary_center_id,
    });
  }

  return <section>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button><h2 className="mt-2 text-2xl font-bold">Usuarios y roles</h2><p className="mt-1 text-sm text-slate-500">Administre las cuentas, roles, centros y estado del personal.</p></div></div>
    {error && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {message && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
      <form onSubmit={createUser} className="rounded-xl border bg-white p-5 shadow-sm"><h3 className="font-semibold">Crear usuario</h3><label className="mt-4 block text-sm font-medium">Nombre completo<input required minLength={2} value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} className="mt-1 w-full rounded-lg border p-2.5" /></label><label className="mt-3 block text-sm font-medium">Correo electrónico<input required type="email" value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} className="mt-1 w-full rounded-lg border p-2.5" /></label><label className="mt-3 block text-sm font-medium">Contraseña inicial<input required minLength={12} type="password" value={createForm.password} onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })} className="mt-1 w-full rounded-lg border p-2.5" /><span className="mt-1 block text-xs text-slate-500">Mínimo 12 caracteres, una letra y un número.</span></label><label className="mt-3 block text-sm font-medium">Rol<select value={createForm.role} onChange={(event) => setCreateForm({ ...createForm, role: event.target.value as RoleCode })} className="mt-1 w-full rounded-lg border p-2.5">{roles.map((role) => <option key={role.code} value={role.code}>{role.label}</option>)}</select></label><button disabled={saving === "create"} className="mt-5 w-full rounded-lg bg-teal-700 px-4 py-2.5 font-medium text-white disabled:opacity-50">{saving === "create" ? "Creando..." : "Crear usuario"}</button></form>

      <div className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><div><h3 className="font-semibold">Usuarios registrados</h3><p className="text-xs text-slate-500">La contraseña nunca se muestra ni se devuelve.</p></div><button onClick={() => void loadData()} className="rounded-lg border px-3 py-2 text-sm">Actualizar</button></div><div className="mt-4 overflow-x-auto">{loading ? <p className="py-6 text-slate-500">Cargando usuarios...</p> : users.length === 0 ? <p className="py-6 text-slate-500">No hay usuarios registrados.</p> : <table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-3 py-3">Usuario</th><th className="px-3 py-3">Rol</th><th className="px-3 py-3">Estado</th><th className="px-3 py-3 text-right">Acción</th></tr></thead><tbody className="divide-y">{users.map((user) => <tr key={user.id}><td className="px-3 py-3"><div className="font-medium">{user.full_name}</div><div className="text-xs text-slate-500">{user.email}</div></td><td className="px-3 py-3"><div className="flex flex-wrap gap-1">{user.roles.map((code) => <span key={code} className="rounded-full bg-slate-100 px-2 py-1 text-xs">{roles.find((role) => role.code === code)?.label ?? code}</span>)}</div></td><td className="px-3 py-3">{user.is_active ? <span className="text-emerald-700">Activo</span> : <span className="text-red-700">Inactivo</span>}</td><td className="px-3 py-3 text-right"><button onClick={() => openEdit(user)} className="font-medium text-teal-700">Editar</button></td></tr>)}</tbody></table>}</div></div>
    </div>

    {editing && editForm && <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/50 p-4"><div className="mx-auto my-6 w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl"><div className="flex items-start justify-between gap-4"><div><h3 className="text-xl font-bold">Editar usuario</h3><p className="text-sm text-slate-500">{editing.full_name}</p></div><button onClick={() => setEditing(null)} className="rounded-lg border px-3 py-1.5 text-sm">Cerrar</button></div>{modalError && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{modalError}</div>}{modalMessage && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{modalMessage}</div>}

      <div className="mt-5 rounded-xl border p-4"><h4 className="font-semibold">Datos generales</h4><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-sm font-medium">Nombre completo<input value={editForm.full_name} onChange={(event) => setEditForm({ ...editForm, full_name: event.target.value })} className="mt-1 w-full rounded-lg border p-2.5" /></label><label className="text-sm font-medium">Correo electrónico<input type="email" disabled={editing.id === currentUser.id} value={editForm.email} onChange={(event) => setEditForm({ ...editForm, email: event.target.value })} className="mt-1 w-full rounded-lg border p-2.5 disabled:bg-slate-100" /></label></div>{editing.id === currentUser.id && <p className="mt-2 text-xs text-slate-500">Por seguridad, otro administrador debe cambiar su correo.</p>}<button disabled={Boolean(saving)} onClick={() => void saveProfile()} className="mt-3 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving === "profile" ? "Guardando..." : "Guardar datos"}</button></div>

      <div className="mt-4 rounded-xl border p-4"><h4 className="font-semibold">Roles</h4><div className="mt-3 grid gap-2 sm:grid-cols-3">{roles.map((role) => <label key={role.code} className="flex gap-2 rounded-lg border p-3 text-sm"><input type="checkbox" checked={editForm.roles.includes(role.code)} disabled={editing.id === currentUser.id && role.code === "admin"} onChange={() => toggleRole(role.code)} /><span><span className="font-medium">{role.label}</span><span className="block text-xs text-slate-500">{role.description}</span></span></label>)}</div><button disabled={Boolean(saving)} onClick={() => void saveRoles()} className="mt-3 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving === "roles" ? "Guardando..." : "Guardar roles"}</button></div>

      <div className="mt-4 rounded-xl border p-4"><h4 className="font-semibold">Centros</h4><div className="mt-3 grid gap-2 sm:grid-cols-2">{centers.filter((center) => center.is_active || editForm.center_ids.includes(center.id)).map((center) => <label key={center.id} className="flex items-center gap-2 rounded-lg border p-3 text-sm"><input type="checkbox" checked={editForm.center_ids.includes(center.id)} disabled={!editing.is_active && !editForm.center_ids.includes(center.id)} onChange={() => toggleCenter(center.id)} /><span>{center.name} — {center.city}{!center.is_active && <span className="text-red-600"> (inactivo)</span>}</span></label>)}</div><label className="mt-3 block text-sm font-medium">Centro principal<select value={editForm.primary_center_id ?? ""} onChange={(event) => setEditForm({ ...editForm, primary_center_id: Number(event.target.value) || null })} className="mt-1 w-full rounded-lg border p-2.5"><option value="">Sin centro principal</option>{centers.filter((center) => editForm.center_ids.includes(center.id)).map((center) => <option key={center.id} value={center.id}>{center.name} — {center.city}</option>)}</select></label>{!editing.is_active && <p className="mt-2 text-xs text-slate-500">Reactive el usuario antes de asignarle centros nuevos.</p>}<button disabled={Boolean(saving)} onClick={() => void saveCenters()} className="mt-3 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving === "centers" ? "Guardando..." : "Guardar centros"}</button></div>

      <div className="mt-4 rounded-xl border p-4"><h4 className="font-semibold">Estado</h4><p className="mt-2 text-sm">Estado actual: <span className={editing.is_active ? "font-semibold text-emerald-700" : "font-semibold text-red-700"}>{editing.is_active ? "Activo" : "Inactivo"}</span></p><button disabled={Boolean(saving) || editing.id === currentUser.id} onClick={() => void changeStatus()} className={`mt-3 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${editing.is_active ? "bg-red-700" : "bg-emerald-700"}`}>{saving === "status" ? "Actualizando..." : editing.is_active ? "Desactivar usuario" : "Reactivar usuario"}</button>{editing.id === currentUser.id && <p className="mt-2 text-xs text-slate-500">No puede desactivar su propia cuenta.</p>}</div>

      <div className="mt-4 rounded-xl border p-4"><h4 className="font-semibold">Cambiar contraseña</h4><p className="mt-1 text-xs text-slate-500">No es necesario conocer la contraseña anterior.</p><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-sm font-medium">Nueva contraseña<input type="password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className="mt-1 w-full rounded-lg border p-2.5" /></label><label className="text-sm font-medium">Confirmar contraseña<input type="password" minLength={12} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="mt-1 w-full rounded-lg border p-2.5" /></label></div><p className="mt-2 text-xs text-slate-500">Mínimo 12 caracteres, una letra y un número.</p><button disabled={Boolean(saving) || !newPassword || !confirmPassword} onClick={() => void changePassword()} className="mt-3 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving === "password" ? "Cambiando..." : "Cambiar contraseña"}</button></div>
    </div></div>}
  </section>;
}
