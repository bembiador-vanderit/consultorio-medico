import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { ClinicalHistory, ClinicalHistoryInput } from "../../types/clinicalHistory";

type Props = {
  patientId: number;
  patientName: string;
  onClose: () => void;
};

const emptyFields = {
  reason_for_visit: "",
  current_illness: "",
  personal_history: "",
  family_history: "",
  allergies: "",
  current_medications: "",
  previous_surgeries: "",
  chronic_conditions: "",
  habits: "",
  clinical_notes: "",
};

const fields: Array<[keyof typeof emptyFields, string]> = [
  ["reason_for_visit", "Motivo de consulta"],
  ["current_illness", "Enfermedad actual"],
  ["personal_history", "Antecedentes personales"],
  ["family_history", "Antecedentes familiares"],
  ["allergies", "Alergias"],
  ["current_medications", "Medicamentos habituales"],
  ["previous_surgeries", "Cirugías previas"],
  ["chronic_conditions", "Enfermedades crónicas"],
  ["habits", "Hábitos"],
  ["clinical_notes", "Observaciones clínicas"],
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function emptyHistory(): ClinicalHistoryInput {
  return { consultation_date: today(), ...emptyFields };
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function ClinicalHistoryPanel({ patientId, patientName, onClose }: Props) {
  const [records, setRecords] = useState<ClinicalHistory[]>([]);
  const [index, setIndex] = useState(0);
  const [form, setForm] = useState<ClinicalHistoryInput>(emptyHistory);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const current = records[index];
  const positionLabel = useMemo(
    () => (records.length ? `Consulta ${index + 1} de ${records.length}` : "Nueva consulta"),
    [index, records.length],
  );

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get<ClinicalHistory[]>(`/clinical-history/patients/${patientId}`);
        setRecords(data);
        if (data.length) {
          setIndex(0);
          setForm(data[0]);
          setIsNew(false);
        } else {
          setForm(emptyHistory());
          setIsNew(true);
        }
      } catch (err: any) {
        setError(err?.response?.data?.detail || "No fue posible cargar la historia clínica.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [patientId]);

  function showRecord(nextIndex: number) {
    setIndex(nextIndex);
    setForm(records[nextIndex]);
    setIsNew(false);
    setMessage("");
    setError("");
  }

  function newConsultation() {
    setForm(emptyHistory());
    setIsNew(true);
    setMessage("");
    setError("");
  }

  async function save() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      if (isNew) {
        const { data } = await api.post<ClinicalHistory>(`/clinical-history/patients/${patientId}`, form);
        const nextRecords = [data, ...records].sort((a, b) =>
          b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id,
        );
        setRecords(nextRecords);
        setIndex(nextRecords.findIndex((record) => record.id === data.id));
        setForm(data);
        setIsNew(false);
      } else if (current) {
        const { data } = await api.put<ClinicalHistory>(`/clinical-history/${current.id}`, form);
        const nextRecords = records.map((record) => (record.id === data.id ? data : record)).sort((a, b) =>
          b.consultation_date.localeCompare(a.consultation_date) || b.id - a.id,
        );
        setRecords(nextRecords);
        setIndex(nextRecords.findIndex((record) => record.id === data.id));
        setForm(data);
      }
      setMessage("Historia clínica guardada correctamente.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible guardar la historia clínica.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4">
          <div>
            <h3 className="text-xl font-bold">Historia clínica</h3>
            <p className="text-sm text-slate-500">{patientName}</p>
          </div>
          <button onClick={onClose} className="text-2xl text-slate-500 hover:text-slate-900" aria-label="Cerrar">×</button>
        </div>

        {loading ? <p className="p-6 text-slate-500">Cargando historia clínica...</p> : (
          <div className="space-y-5 p-6">
            <div className="rounded-xl border bg-slate-50 p-4">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Fecha de la consulta</label>
                  <input
                    type="date"
                    value={form.consultation_date}
                    onChange={(event) => setForm({ ...form, consultation_date: event.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
                  />
                  <p className="mt-1 text-xs text-slate-500">{positionLabel}</p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => showRecord(index + 1)}
                    disabled={isNew || index >= records.length - 1}
                    className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    ← Anterior
                  </button>
                  <button
                    type="button"
                    onClick={() => showRecord(index - 1)}
                    disabled={isNew || index <= 0}
                    className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Siguiente →
                  </button>
                  <button
                    type="button"
                    onClick={newConsultation}
                    className="rounded-lg bg-slate-700 px-4 py-2 font-medium text-white"
                  >
                    Nueva consulta
                  </button>
                </div>
              </div>
            </div>

            {fields.map(([name, label]) => (
              <label key={name} className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
                <textarea
                  value={form[name] ?? ""}
                  onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                  rows={3}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
                />
              </label>
            ))}

            {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
            {message && <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

            <div className="flex justify-end gap-3 border-t pt-5">
              <button onClick={onClose} className="rounded-lg border border-slate-300 px-5 py-2 font-medium">Cerrar</button>
              <button onClick={() => void save()} disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-50">
                {saving ? "Guardando..." : isNew ? "Guardar consulta" : "Guardar cambios"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
