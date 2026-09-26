import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, FormField, Input, Select, LoadingState } from "../ui";
import { api } from "../services/api";
import { insuranceError } from "../services/insurance";
import type { InsuranceCompany, InsurancePlan } from "../types/insurance";
const blankCompany = { name: "", code: "", is_active: true };
const blankPlan = { name: "", code: "", description: "", is_active: true };
export default function InsuranceCatalog() {
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]), [plans, setPlans] = useState<InsurancePlan[]>([]);
  const [company, setCompany] = useState(blankCompany), [plan, setPlan] = useState(blankPlan);
  const [companyId, setCompanyId] = useState<number | null>(null), [planId, setPlanId] = useState<number | null>(null), [selected, setSelected] = useState("");
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false);
  async function load() { const [c, p] = await Promise.all([api.get('/insurance/companies?include_inactive=true'), api.get('/insurance/plans?include_inactive=true')]); setCompanies(c.data); setPlans(p.data); }
  useEffect(() => { load().catch(e => setError(insuranceError(e))).finally(() => setLoading(false)); }, []);
  async function save(e: FormEvent, kind: 'companies' | 'plans') {
    e.preventDefault(); setSaving(true); setError('');
    const id = kind === 'companies' ? companyId : planId;
    const data = kind === 'companies' ? { ...company, code: company.code || null } : { ...plan, code: plan.code || null, description: plan.description || null, insurance_company_id: Number(selected) };
    try { if (id) await api.put(`/insurance/${kind}/${id}`, data); else await api.post(`/insurance/${kind}`, data);
      if (kind === 'companies') { setCompany(blankCompany); setCompanyId(null); } else { setPlan(blankPlan); setPlanId(null); }
      await load();
    } catch (e) { setError(insuranceError(e)); } finally { setSaving(false); }
  }
  return <section className="patient-form"><h2>Aseguradoras / ARS y planes</h2><p>Catálogo exclusivo de esta organización. Desactivar conserva los registros históricos.</p>
    {error && <Alert tone="danger" title="No se pudo guardar">{error}</Alert>}
    {loading ? <LoadingState label="Cargando catálogo..." /> : <>
      <Card><h3>Aseguradoras / ARS</h3>{companies.length === 0 && <p>No hay aseguradoras registradas.</p>}
        {companies.map(c => <p key={c.id}>{c.name} · {c.is_active ? 'Activa' : 'Inactiva'} <Button variant="outline" disabled={saving} onClick={() => { setCompanyId(c.id); setCompany({ name: c.name, code: c.code || '', is_active: c.is_active }); }}>Editar {c.name}</Button></p>)}
        <form onSubmit={e => void save(e, 'companies')} className="patient-form"><h3>{companyId ? 'Editar aseguradora' : 'Nueva aseguradora'}</h3>
          <FormField label="Nombre de la ARS" required><Input minLength={2} maxLength={150} value={company.name} onChange={e => setCompany({ ...company, name: e.target.value })} /></FormField>
          <FormField label="Código"><Input maxLength={50} value={company.code} onChange={e => setCompany({ ...company, code: e.target.value })} /></FormField>
          <Checkbox label="Aseguradora activa" checked={company.is_active} onChange={e => setCompany({ ...company, is_active: e.target.checked })} />
          <Button type="submit" loading={saving}>Guardar aseguradora</Button>{companyId && <Button variant="outline" onClick={() => { setCompanyId(null); setCompany(blankCompany); }}>Cancelar edición</Button>}
        </form>
      </Card>
      <Card><h3>Planes</h3><FormField label="Aseguradora de los planes"><Select value={selected} disabled={planId !== null} onChange={e => setSelected(e.target.value)}><option value="">Seleccione</option>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></FormField>
        {plans.filter(p => p.insurance_company_id === Number(selected)).map(p => <p key={p.id}>{p.name} · {p.is_active ? 'Activo' : 'Inactivo'} <Button variant="outline" disabled={saving} onClick={() => { setPlanId(p.id); setPlan({ name: p.name, code: p.code || '', description: p.description || '', is_active: p.is_active }); }}>Editar {p.name}</Button></p>)}
        {selected && <form onSubmit={e => void save(e, 'plans')} className="patient-form"><h3>{planId ? 'Editar plan' : 'Nuevo plan'}</h3>
          <FormField label="Nombre del plan" required><Input minLength={2} maxLength={150} value={plan.name} onChange={e => setPlan({ ...plan, name: e.target.value })} /></FormField>
          <FormField label="Código del plan"><Input maxLength={50} value={plan.code} onChange={e => setPlan({ ...plan, code: e.target.value })} /></FormField>
          <FormField label="Descripción del plan"><Input maxLength={1000} value={plan.description} onChange={e => setPlan({ ...plan, description: e.target.value })} /></FormField>
          <Checkbox label="Plan activo" checked={plan.is_active} onChange={e => setPlan({ ...plan, is_active: e.target.checked })} />
          <Button type="submit" loading={saving}>Guardar plan</Button>{planId && <Button variant="outline" onClick={() => { setPlanId(null); setPlan(blankPlan); }}>Cancelar edición de plan</Button>}
        </form>}
      </Card>
    </>}
  </section>;
}
