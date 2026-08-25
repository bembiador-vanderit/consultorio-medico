import { FormEvent, useEffect, useState } from "react";
import { api } from "../../services/api";
import type { InsuranceCompany, PatientInsurance } from "../../types/insurance";
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
  const [hasInsurance, setHasInsurance] = useState(false);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [memberNumber, setMemberNumber] = useState("");
  const [planName, setPlanName] = useState("");
  const [currentInsurance, setCurrentInsurance] = useState<PatientInsurance | null>(null);
  const [loadingInsurance, setLoadingInsurance] = useState(Boolean(patient));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadInsurance() {
      setLoadingInsurance(Boolean(patient));
      try {
        const { data: insuranceCompanies } = await api.get<InsuranceCompany[]>("/insurance/companies");
        if (cancelled) return;
        setCompanies(insuranceCompanies);
        if (insuranceCompanies.length > 0 && !companyId) {
          setCompanyId(String(insuranceCompanies[0].id));
        }

        if (!patient) return;
        const { data: patientInsurances } = await api.get<PatientInsurance[]>(`/insurance/patients/${patient.id}`);
        if (cancelled) return;
        const active = patientInsurances.find((item) => item.is_active && item.is_primary) ?? patientInsurances.find((item) => item.is_active) ?? null;
        setCurrentInsurance(active);
        if (active) {
          setHasInsurance(true);
          setCompanyId(String(active.insurance_company_id));
          setMemberNumber(active.member_number);
          setPlanName(active.plan_name || "");
        }
      } catch (err: any) {
        if (!cancelled) setError(err?.response?.data?.detail || "No fue posible cargar las compañías de seguros.");
      } finally {
        if (!cancelled) setLoadingInsurance(false);
      }
    }

    void loadInsurance();
    return () => { cancelled = true; };
  }, [patient?.id]);

  function selectInsurance(value: boolean) {
    setHasInsurance(value);
    if (!value) {
      setMemberNumber("");
      setPlanName("");
      setCurrentInsurance(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    if (hasInsurance && (!companyId || !memberNumber.trim())) {
      setError("Para registrar un seguro debe seleccionar la ARS e indicar el número de afiliado.");
      setSaving(false);
      return;
    }

    const insuranceChanged = hasInsurance && (
      !currentInsurance ||
      currentInsurance.insurance_company_id !== Number(companyId) ||
      currentInsurance.member_number !== memberNumber.trim() ||
      (currentInsurance.plan_name || "") !== planName.trim()
    );

    const payload = {
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      date_of_birth: dateOfBirth,
      phone: phone.trim() || null,
      email: email.trim() || null,
      has_insurance: hasInsurance,
      insurance: insuranceChanged ? {
        insurance_company_id: Number(companyId),
        member_number: memberNumber.trim(),
        plan_name: planName.trim() || null,
        is_primary: true,
      } : null,
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
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/50 p-4">
      <form onSubmit={save} className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-xl font-bold">{patient ? "Editar paciente" : "Nuevo paciente"}</h3>
        <p className="mt-1 text-sm text-slate-500">Complete los datos del paciente y su cobertura médica.</p>

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

        <div className="mt-6 rounded-xl border bg-slate-50 p-4">
          <h4 className="font-semibold">Seguro</h4>
          <p className="mt-1 text-sm text-slate-500">Indique si el paciente tiene seguro médico.</p>
          <div className="mt-3 flex gap-6">
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={hasInsurance} onChange={() => selectInsurance(true)} className="h-4 w-4" />
              Sí
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={!hasInsurance} onChange={() => selectInsurance(false)} className="h-4 w-4" />
              No
            </label>
          </div>

          <div className={`mt-4 grid gap-4 sm:grid-cols-2 ${!hasInsurance ? "opacity-50" : ""}`}>
            <label className="text-sm font-medium">ARS *
              <select required={hasInsurance} disabled={!hasInsurance || loadingInsurance} value={companyId} onChange={(e) => setCompanyId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 disabled:cursor-not-allowed disabled:bg-slate-100">
                <option value="">{loadingInsurance ? "Cargando ARS..." : "Seleccione una ARS"}</option>
                {companies.map((company) => <option key={company.id} value={company.id}>{company.name}{company.code ? ` (${company.code})` : ""}</option>)}
              </select>
            </label>
            <label className="text-sm font-medium">Número de afiliado *
              <input required={hasInsurance} disabled={!hasInsurance} maxLength={100} value={memberNumber} onChange={(e) => setMemberNumber(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2 disabled:cursor-not-allowed disabled:bg-slate-100" />
            </label>
            <label className="text-sm font-medium sm:col-span-2">Plan
              <input disabled={!hasInsurance} maxLength={150} value={planName} onChange={(e) => setPlanName(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2 disabled:cursor-not-allowed disabled:bg-slate-100" />
            </label>
          </div>
          {!hasInsurance && <p className="mt-3 text-sm font-medium text-slate-600">Paciente sin Seguro</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2">Cancelar</button>
          <button type="submit" disabled={saving || loadingInsurance} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-60">
            {saving ? "Guardando..." : patient ? "Guardar cambios" : "Guardar paciente"}
          </button>
        </div>
      </form>
    </div>
  );
}
