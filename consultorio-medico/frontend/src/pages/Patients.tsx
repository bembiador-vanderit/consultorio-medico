import { FormEvent, useEffect, useState } from "react";
import { api } from "../services/api";

type Patient = {
  id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone: string | null;
  email: string | null;
  created_at: string;
};

type Props = {
  onBack: () => void;
  onPatientChanged: () => void;
};

export default function Patients({
  onBack,
  onPatientChanged,
}: Props) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Patient | null>(null);

  async function loadPatients(search = "") {
    setLoading(true);
    setError("");

    try {
      const { data } = await api.get<Patient[]>("/patients", {
        params: {
          query: search.trim() || undefined,
          limit: 100,
        },
      });

      setPatients(data);
    } catch (err: any) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          "No fue posible cargar los pacientes."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPatients();
  }, []);

  function createPatient() {
    setEditing(null);
    setShowForm(true);
  }

  function editPatient(patient: Patient) {
    setEditing(patient);
    setShowForm(true);
  }

  return (
    <section>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            onClick={onBack}
            className="text-sm font-medium text-teal-700 hover:underline"
          >
            ← Volver al dashboard
          </button>

          <h2 className="mt-2 text-2xl font-bold">
            Pacientes
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Registro y administración de pacientes.
          </p>
        </div>

        <button
          onClick={createPatient}
          className="rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800"
        >
          + Nuevo paciente
        </button>
      </div>

      <form
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          loadPatients(query);
        }}
        className="mt-6 flex flex-col gap-3 rounded-xl border bg-white p-4 shadow-sm sm:flex-row"
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar por nombre, apellido o teléfono..."
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2"
        />

        <button
          type="submit"
          className="rounded-lg bg-slate-900 px-5 py-2 font-medium text-white"
        >
          Buscar
        </button>

        <button
          type="button"
          onClick={() => {
            setQuery("");
            loadPatients("");
          }}
          className="rounded-lg border border-slate-300 px-5 py-2 font-medium"
        >
          Limpiar
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-xl border bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-slate-500">
            Cargando pacientes...
          </p>
        ) : patients.length === 0 ? (
          <div className="p-10 text-center">
            <p className="font-medium">
              No hay pacientes registrados.
            </p>

            <p className="mt-1 text-sm text-slate-500">
              Puedes registrar el primero con "Nuevo paciente".
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">
                    Paciente
                  </th>

                  <th className="px-4 py-3">
                    Fecha nacimiento
                  </th>

                  <th className="px-4 py-3">
                    Teléfono
                  </th>

                  <th className="px-4 py-3">
                    Correo
                  </th>

                  <th className="px-4 py-3 text-right">
                    Acción
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
                {patients.map((patient) => (
                  <tr
                    key={patient.id}
                    className="hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-medium">
                      {patient.first_name}{" "}
                      {patient.last_name}
                    </td>

                    <td className="px-4 py-3">
                      {patient.date_of_birth}
                    </td>

                    <td className="px-4 py-3">
                      {patient.phone || "—"}
                    </td>

                    <td className="px-4 py-3">
                      {patient.email || "—"}
                    </td>

                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => editPatient(patient)}
                        className="font-medium text-teal-700 hover:underline"
                      >
                        Editar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <PatientForm
  patient={editing}
  onClose={() => setShowForm(false)}
  onSaved={() => {
    console.log("PACIENTE GUARDADO - ACTUALIZANDO DASHBOARD");
    
    setShowForm(false);
    loadPatients(query);
    onPatientChanged();
  }}
/>
      )}
    </section>
  );
}

function PatientForm({
  patient,
  onClose,
  onSaved,
}: {
  patient: Patient | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [firstName, setFirstName] = useState(
    patient?.first_name || ""
  );

  const [lastName, setLastName] = useState(
    patient?.last_name || ""
  );

  const [dateOfBirth, setDateOfBirth] = useState(
    patient?.date_of_birth || ""
  );

  const [phone, setPhone] = useState(
    patient?.phone || ""
  );

  const [email, setEmail] = useState(
    patient?.email || ""
  );

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
        await api.put(
          `/patients/${patient.id}`,
          payload
        );
      } else {
        await api.post(
          "/patients",
          payload
        );
      }

      onSaved();
    } catch (err: any) {
      console.error(err);

      const detail = err?.response?.data?.detail;

      if (Array.isArray(detail)) {
        setError(
          detail
            .map((item: any) => item.msg)
            .join(", ")
        );
      } else {
        setError(
          detail ||
            "No fue posible guardar el paciente."
        );
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form
        onSubmit={save}
        className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"
      >
        <h3 className="text-xl font-bold">
          {patient
            ? "Editar paciente"
            : "Nuevo paciente"}
        </h3>

        <p className="mt-1 text-sm text-slate-500">
          Complete los datos del paciente.
        </p>

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Nombre *

            <input
              required
              minLength={2}
              maxLength={100}
              value={firstName}
              onChange={(e) =>
                setFirstName(e.target.value)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 p-2"
            />
          </label>

          <label className="text-sm font-medium">
            Apellido *

            <input
              required
              minLength={2}
              maxLength={100}
              value={lastName}
              onChange={(e) =>
                setLastName(e.target.value)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 p-2"
            />
          </label>

          <label className="text-sm font-medium">
            Fecha de nacimiento *

            <input
              required
              type="date"
              value={dateOfBirth}
              onChange={(e) =>
                setDateOfBirth(e.target.value)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 p-2"
            />
          </label>

          <label className="text-sm font-medium">
            Teléfono

            <input
              maxLength={30}
              value={phone}
              onChange={(e) =>
                setPhone(e.target.value)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 p-2"
            />
          </label>

          <label className="text-sm font-medium sm:col-span-2">
            Correo

            <input
              type="email"
              value={email}
              onChange={(e) =>
                setEmail(e.target.value)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 p-2"
            />
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2"
          >
            Cancelar
          </button>

          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-60"
          >
            {saving
              ? "Guardando..."
              : patient
              ? "Guardar cambios"
              : "Guardar paciente"}
          </button>
        </div>
      </form>
    </div>
  );
}
