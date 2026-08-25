import { FormEvent, useEffect, useState } from "react";
import { api } from "../../services/api";
import type { InsuranceCompany, PatientInsurance } from "../../types/insurance";
import type { User } from "../../types/user";

type Props = {
  patientId: number;
  patientName: string;
  user: User;
  onClose: () => void;
};

export default function PatientInsurancePanel({ patientId, patientName, user, onClose }: Props) {
  const [items, setItems] = useState<PatientInsurance[]>([]);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [memberNumber, setMemberNumber] = useState("");
  const [planName, setPlanName] = useState("");
  const [isPrimary, setIsPrimary] = useState(true);
  const [newCompany, setNewCompany] = useState("");
  const [newCode, setNewCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const canManageCompanies = user.roles.includes("admin");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [{ data: patientInsurances }, { data: insuranceCompanies }] = await Promise.all([
        api.get<PatientInsurance[]>(`/insurance/patients/${patientId}`),
        api.get<InsuranceCompany[]>("/insurance/companies"),
      ]);
      setItems(patientInsurances);
      setCompanies(insuranceCompanies);
      if (!companyId && insuranceCompanies.length > 0) setCompanyId(String(insuranceCompanies[0].id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible cargar los seguros del paciente.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [patientId]);

  async function addInsurance(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post(`/insurance/patients/${patientId}`, {
        insurance_company_id: Number(companyId),
        member_number: memberNumber.trim(),
        plan_name: planName.trim() || null,
        is_primary: isPrimary,
      });
      setMemberNumber("");
      setPlanName("");
      await load();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((item: any) => item.msg).join(", ") : detail || "No fue posible registrar el seguro.");
    } finally {
      setSaving(false);
    }
  }

  async function createCompany(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post<InsuranceCompany>("/insurance/companies", {
        name: newCompany.trim(),
        code: newCode.trim() || null,
      });
      setNewCompany("");
      setNewCode("");
      setCompanies((current) => [...current, data].sort((a, b) => a.name.localeCompare(b.name)));
      setCompanyId(String(data.id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible registrar la ARS.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/50 p-4">
      <div className="mx-auto mt-8 w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">Ficha del paciente</p>
            <h3 className="mt-1 text-2xl font-bold">Seguro médico</h3>
            <p className="mt-1 text-sm text-slate-500">{patientName}</p>
          </div>
          <button onClick={onClose} className="rounded-lg border px-3 py-2 text-sm">Cerrar</button>
        </div>

        {error && <div className="mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        <div className="mt-6 rounded-xl border bg-slate-50 p-4">
          <h4 className="font-semibold">Registrar seguro del paciente</h4>
          {companies.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No hay compañías de seguros registradas. Un administrador debe crear la primera ARS.</p>
          ) : (
            <form onSubmit={addInsurance} className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium">Compañía / ARS *
                <select required value={companyId} onChange={(e) => setCompanyId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2">
                  {companies.map((company) => <option key={company.id} value={company.id}>{company.name}{company.code ? ` (${company.code})` : ""}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Número de afiliado *
                <input required maxLength={100} value={memberNumber} onChange={(e) => setMemberNumber(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
              </label>
              <label className="text-sm font-medium">Plan
                <input maxLength={150} value={planName} onChange={(e) => setPlanName(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2" />
              </label>
              <label className="flex items-center gap-2 pt-6 text-sm font-medium">
                <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} /> Seguro principal
              </label>
              <div className="sm:col-span-2 flex justify-end">
                <button disabled={saving} className="rounded-lg bg-teal-700 px-5 py-2 font-medium text-white disabled:opacity-60">{saving ? "Guardando..." : "Agregar seguro"}</button>
              </div>
            </form>
          )}
        </div>

        {canManageCompanies && (
          <form onSubmit={createCompany} className="mt-4 rounded-xl border p-4">
            <h4 className="font-semibold">Administrar compañías de seguros</h4>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_180px_auto]">
              <input required minLength={2} maxLength={150} value={newCompany} onChange={(e) => setNewCompany(e.target.value)} placeholder="Nombre de la ARS" className="rounded-lg border border-slate-300 p-2" />
              <input maxLength={50} value={newCode} onChange={(e) => setNewCode(e.target.value)} placeholder="Código opcional" className="rounded-lg border border-slate-300 p-2" />
              <button disabled={saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Nueva ARS</button>
            </div>
          </form>
        )}

        <div className="mt-6">
          <h4 className="font-semibold">Seguros registrados</h4>
          {loading ? <p className="mt-3 text-sm text-slate-500">Cargando...</p> : items.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed p-5 text-center text-sm text-slate-500">Este paciente todavía no tiene seguros registrados.</p>
          ) : (
            <div className="mt-3 overflow-hidden rounded-xl border">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">ARS</th><th className="px-4 py-3">Afiliado</th><th className="px-4 py-3">Plan</th><th className="px-4 py-3">Estado</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((item) => <tr key={item.id}><td className="px-4 py-3 font-medium">{item.insurance_company_name}{item.is_primary && <span className="ml-2 rounded-full bg-teal-50 px-2 py-1 text-xs text-teal-700">Principal</span>}</td><td className="px-4 py-3">{item.member_number}</td><td className="px-4 py-3">{item.plan_name || "—"}</td><td className="px-4 py-3">{item.is_active ? "Activo" : "Inactivo"}</td></tr>)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
