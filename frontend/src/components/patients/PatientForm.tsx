import { FormEvent, useState } from "react";
import { api } from "../../services/api";
import type { Patient } from "../../types/patient";

type Props = {
  patient: Patient | null;
  onClose: () => void;
  onSaved: () => void;
};

export default function PatientForm({ patient, onClose, onSaved }: Props) {
  const [firstName, setFirstName] = useState(patient?.first_name || "");
  const [lastName, setLastName] = useState(patient?.last_name || "");
  const [dateOfBirth, setDateOfBirth] = useState(patient?.date_of_birth || "");
  const [phone, setPhone] = useState(patient?.phone || "");
  const [email, setEmail] = useState(patient?.email || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    const payload = {
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      date_of_birth: dateOfBirth,
      phone: phone.trim() || null,
      email: email.trim() || null,
    };

    try {
      if (patient) {
        await api.put(`/patients/${patient.id}`, payload);
      } else {
        await api.post("/patients", payload);
      }
      onSaved();
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((item: any) => item.msg).join(", ")
          : detail || "No fue posible guardar el paciente."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form onSubmit={save} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-xl font-bold">{patient ? "Editar paciente" : "Nuevo paciente"}</h3>
        <p className="mt-1 text-sm text-slate-500">Complete los datos del paciente.</p>

        {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">Nombre *
            <input required minLength={2} maxLength={100} value={firstName} onChange={(e) => setFirstName(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
          </label>
          <label className="text-sm font-medium">Apellido *
            <input required minLength={2} maxLength={100} value={lastName} onChange={(e) => setLastName(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
          </label>
          <label className="text-sm font-medium">Fecha de nacimiento *
            <input required type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
          </label>
          <label className="text-sm font-medium">Teléfono
            <input maxLength={30} value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
          </label>
          <label className="text-sm font-medium sm:col-span-2">Correo
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2">Cancelar</button>
          <button type="submit" disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-60">
            {saving ? "Guardando..." : patient ? "Guardar cambios" : "Guardar paciente"}
          </button>
        </div>
      </form>
    </div>
  );
}
