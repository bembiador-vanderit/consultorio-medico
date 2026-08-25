import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { ClinicalHistoryInput } from "../../types/clinicalHistory";

type Props = {
  patientId: number;
  patientName: string;
  onClose: () => void;
};

const emptyHistory: ClinicalHistoryInput = {
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

const fields: Array<[keyof ClinicalHistoryInput, string]> = [
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

export default function ClinicalHistoryPanel({ patientId, patientName, onClose }: Props) {
  const [form, setForm] = useState<ClinicalHistoryInput>(emptyHistory);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get(`/clinical-history/patients/${patientId}`);
        if (data) setForm(data);
      } catch (err: any) {
        setError(err?.response?.data?.detail || "No fue posible cargar la historia clínica.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [patientId]);

  async function save() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      await api.put(`/clinical-history/patients/${patientId}`, form);
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
        <div className="sticky top-0 flex items-center justify-between border-b bg-white px-6 py-4">
          <div>
            <h3 className="text-xl font-bold">Historia clínica</h3>
            <p className="text-sm text-slate-500">{patientName}</p>
          </div>
          <button onClick={onClose} className="text-2xl text-slate-500 hover:text-slate-900" aria-label="Cerrar">×</button>
        </div>

        {loading ? <p className="p-6 text-slate-500">Cargando historia clínica...</p> : (
          <div className="space-y-5 p-6">
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
                {saving ? "Guardando..." : "Guardar historia clínica"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
