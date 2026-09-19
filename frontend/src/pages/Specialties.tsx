import { FormEvent, useEffect, useState } from "react";

import { api } from "../services/api";

type Props = { onBack: () => void };
type Specialty = { id: number; name: string; is_active: boolean };

function apiError(reason: any, fallback: string) {
  const detail = reason?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return (
      detail
        .map((item) => item?.msg)
        .filter(Boolean)
        .join(" ") || fallback
    );
  return fallback;
}

export default function Specialties({ onBack }: Props) {
  const [items, setItems] = useState<Specialty[]>([]);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<Specialty | null>(null);
  const [editName, setEditName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setItems(
        (await api.get<Specialty[]>("/clinical-catalog/specialties/admin"))
          .data,
      );
    } catch (reason: any) {
      setError(apiError(reason, "No fue posible cargar las especialidades."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setSaving("create");
    setError("");
    setMessage("");
    try {
      await api.post("/clinical-catalog/specialties", { name: name.trim() });
      setName("");
      setMessage("Especialidad creada y disponible para nuevos médicos.");
      await load();
    } catch (reason: any) {
      setError(apiError(reason, "No fue posible crear la especialidad."));
    } finally {
      setSaving("");
    }
  }

  async function saveName(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setSaving(`edit-${editing.id}`);
    setError("");
    setMessage("");
    try {
      await api.patch(`/clinical-catalog/specialties/${editing.id}`, {
        name: editName.trim(),
      });
      setEditing(null);
      setMessage("Nombre actualizado.");
      await load();
    } catch (reason: any) {
      setError(apiError(reason, "No fue posible editar la especialidad."));
    } finally {
      setSaving("");
    }
  }

  async function changeStatus(item: Specialty) {
    setSaving(`status-${item.id}`);
    setError("");
    setMessage("");
    try {
      await api.put(`/clinical-catalog/specialties/${item.id}/status`, {
        is_active: !item.is_active,
      });
      setMessage(
        item.is_active
          ? "Especialidad desactivada; sus referencias históricas se conservaron."
          : "Especialidad reactivada.",
      );
      await load();
    } catch (reason: any) {
      setError(apiError(reason, "No fue posible cambiar el estado."));
    } finally {
      setSaving("");
    }
  }

  return (
    <section>
      <button
        onClick={onBack}
        className="text-sm font-medium text-teal-700 hover:underline"
      >
        ← Volver al dashboard
      </button>
      <h2 className="mt-2 text-2xl font-bold">Especialidades</h2>
      <p className="mt-1 text-sm text-slate-500">
        Administre el catálogo disponible para médicos y citas nuevas. Las
        referencias clínicas nunca se eliminan.
      </p>
      {error && (
        <div
          role="alert"
          className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}
      {message && (
        <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
          {message}
        </div>
      )}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <form
          onSubmit={create}
          className="rounded-xl border bg-white p-5 shadow-sm"
        >
          <h3 className="font-semibold">Nueva especialidad</h3>
          <label className="mt-4 block text-sm font-medium">
            Nombre
            <input
              required
              minLength={2}
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full rounded-lg border p-2.5"
            />
          </label>
          <button
            disabled={Boolean(saving) || name.trim().length < 2}
            className="mt-4 w-full rounded-lg bg-teal-700 px-4 py-2.5 font-medium text-white disabled:opacity-50"
          >
            {saving === "create" ? "Creando..." : "Crear especialidad"}
          </button>
        </form>
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">Catálogo</h3>
              <p className="text-xs text-slate-500">
                Desactive en lugar de borrar para conservar el historial.
              </p>
            </div>
            <button
              onClick={() => void load()}
              className="rounded-lg border px-3 py-2 text-sm"
            >
              Actualizar
            </button>
          </div>
          {loading ? (
            <p className="py-6 text-slate-500">Cargando...</p>
          ) : (
            <div className="mt-4 divide-y rounded-lg border">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-medium">{item.name}</p>
                    <p
                      className={`text-xs font-medium ${item.is_active ? "text-emerald-700" : "text-red-700"}`}
                    >
                      {item.is_active ? "Activa" : "Inactiva"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditing(item);
                        setEditName(item.name);
                        setError("");
                      }}
                      className="rounded-lg border px-3 py-2 text-sm font-medium"
                    >
                      Editar
                    </button>
                    <button
                      disabled={Boolean(saving)}
                      onClick={() => void changeStatus(item)}
                      className={`rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-50 ${item.is_active ? "bg-red-700" : "bg-emerald-700"}`}
                    >
                      {saving === `status-${item.id}`
                        ? "Actualizando..."
                        : item.is_active
                          ? "Desactivar"
                          : "Activar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <form
            onSubmit={saveName}
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
          >
            <h3 className="text-lg font-bold">Editar especialidad</h3>
            <p className="mt-1 text-xs text-slate-500">
              El nombre solo puede cambiar si aún no tiene citas ni consultas
              asociadas.
            </p>
            <label className="mt-4 block text-sm font-medium">
              Nombre
              <input
                required
                minLength={2}
                maxLength={120}
                autoFocus
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                className="mt-1 w-full rounded-lg border p-2.5"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="rounded-lg border px-4 py-2 text-sm"
              >
                Cancelar
              </button>
              <button
                disabled={Boolean(saving) || editName.trim().length < 2}
                className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {saving === `edit-${editing.id}` ? "Guardando..." : "Guardar"}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
