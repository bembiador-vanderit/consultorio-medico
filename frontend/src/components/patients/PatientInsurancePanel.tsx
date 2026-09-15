import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, EmptyState, FormField, FormSection, Input, LoadingState, Modal, Select, StatusBadge } from "../../ui";
import "../../pages/patients.css";
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

  async function deactivateInsurance(item: PatientInsurance) {
    if (!window.confirm(`¿Desea desactivar el seguro ${item.insurance_company_name} del paciente? El registro se conservará en el historial.`)) return;
    setSaving(true);
    setError("");
    try {
      await api.delete(`/insurance/patients/${patientId}/${item.id}`);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No fue posible desactivar el seguro.");
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

  const activeItems = items.filter((item) => item.is_active);

  return <Modal title="Seguro médico" description={patientName} open onClose={() => { if (!saving) onClose(); }} closeLabel="Cerrar seguro médico">
    <div className="patient-form">
      {error && <Alert tone="danger" title="No se pudo completar la operación">{error}</Alert>}
      {loading ? <LoadingState label="Cargando seguros..." /> : <>
        <section aria-label="Seguros registrados">
          <h2 className="atlas-card-title">Seguros registrados</h2>
          {items.length === 0 ? <EmptyState title="Paciente sin Seguro" description="No hay afiliaciones registradas." /> : <ul className="patient-insurance-list">{items.map((item) => <li key={item.id}><Card compact>
            <header><h3 className="atlas-card-title">{item.insurance_company_name}</h3><StatusBadge tone={item.is_active ? "success" : "neutral"}>{item.is_active ? item.is_primary ? "Activo · Principal" : "Activo" : "Inactivo"}</StatusBadge></header>
            <dl className="patients-facts"><div><dt>Número de afiliado</dt><dd>{item.member_number}</dd></div><div><dt>Plan</dt><dd>{item.plan_name || "Sin plan registrado"}</dd></div></dl>
            {item.is_active ? <Button variant="outline" disabled={saving} onClick={() => void deactivateInsurance(item)}>Desactivar</Button> : <p className="atlas-help">Registro conservado en el historial</p>}
          </Card></li>)}</ul>}
          {items.length > 0 && activeItems.length === 0 && <p className="atlas-help">Paciente sin Seguro activo.</p>}
        </section>
        {companies.length === 0 ? <Alert title="No hay compañías de seguros registradas">Un administrador debe crear la primera ARS.</Alert> : <form onSubmit={addInsurance} className="patient-form">
          <FormSection title="Registrar seguro del paciente">
            <FormField label="Compañía / ARS" required><Select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}{company.code ? ` (${company.code})` : ""}</option>)}</Select></FormField>
            <FormField label="Número de afiliado" required><Input maxLength={100} value={memberNumber} onChange={(e) => setMemberNumber(e.target.value)} /></FormField>
            <FormField label="Plan"><Input maxLength={150} value={planName} onChange={(e) => setPlanName(e.target.value)} /></FormField>
            <Checkbox label="Seguro principal" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
          </FormSection><Button type="submit" loading={saving} loadingLabel="Guardando...">Agregar seguro</Button>
        </form>}
        {canManageCompanies && <form onSubmit={createCompany} className="patient-form">
          <FormSection title="Administrar compañías de seguros">
            <FormField label="Nombre de la ARS" required><Input minLength={2} maxLength={150} value={newCompany} onChange={(e) => setNewCompany(e.target.value)} /></FormField>
            <FormField label="Código opcional"><Input maxLength={50} value={newCode} onChange={(e) => setNewCode(e.target.value)} /></FormField>
          </FormSection><Button type="submit" variant="outline" disabled={saving}>Nueva ARS</Button>
        </form>}
      </>}
    </div>
  </Modal>;
}
