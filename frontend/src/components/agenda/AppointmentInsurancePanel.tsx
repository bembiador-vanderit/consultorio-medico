import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, Card, FormField, Input, LoadingState, RequiredFieldsLegend, Select } from "../../ui";
import { api } from "../../services/api";
import { insuranceError } from "../../services/insurance";
import type { Appointment } from "../../types/appointment";
import type { User } from "../../types/user";
import type { AppointmentInsuranceCoverage, InsuranceCompany, InsurancePlan, PatientInsurance } from "../../types/insurance";
import PatientInsurancePanel from "../patients/PatientInsurancePanel";
const blank = { patient_insurance_id: '', service: '', currency: 'DOP', base_amount: '0.00', covered_amount: '0.00', patient_copay: '0.00', authorization_status: 'pending', authorization_number: '', authorized_at: '', authorized_amount: '', authorization_notes: '', notes: '', revision: 0 };
function eligibleAffiliations(items: PatientInsurance[], companies: InsuranceCompany[], plans: InsurancePlan[], date: string) {
  return items.filter(item => item.is_active && companies.some(company => company.id === item.insurance_company_id && company.is_active)
    && (!item.plan_id || plans.some(plan => plan.id === item.plan_id && plan.insurance_company_id === item.insurance_company_id && plan.is_active))
    && (!date || ((!item.valid_from || item.valid_from <= date) && (!item.valid_until || item.valid_until >= date))));
}
function preferredAffiliation(items: PatientInsurance[]) {
  return items.find(item => item.is_primary) || items[0];
}
export default function AppointmentInsurancePanel({ appointment, user }: { appointment: Appointment; user: User }) {
  const [saved, setSaved] = useState<AppointmentInsuranceCoverage | null>(null), [insurances, setInsurances] = useState<PatientInsurance[]>([]);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]), [plans, setPlans] = useState<InsurancePlan[]>([]);
  const [coverageType, setCoverageType] = useState<'particular' | 'insured'>('particular');
  const [companyId, setCompanyId] = useState(''), [planId, setPlanId] = useState('');
  const [editingAffiliation, setEditingAffiliation] = useState(false);
  const [form, setForm] = useState(blank), [states, setStates] = useState<{ code: string; label: string }[]>([]);
  const [blocked, setBlocked] = useState(false);
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [attempted, setAttempted] = useState(false);
  const canWrite = !!user.permissions?.includes('insurance:manage') && !!user.permissions?.includes('patients:access');
  const closed = ['completed', 'cancelled', 'no_show'].includes(appointment.status);
  const path = `/insurance/appointments/${appointment.id}/coverage`;
  function apply(data: AppointmentInsuranceCoverage | null, items: PatientInsurance[], catalog: InsuranceCompany[], planCatalog: InsurancePlan[]) {
    setAttempted(false);
    setSaved(data);
    const preferred = !data ? preferredAffiliation(eligibleAffiliations(items, catalog, planCatalog, appointment.appointment_date)) : undefined;
    const selected = items.find(item => item.id === (data?.patient_insurance_id || preferred?.id));
    setCoverageType(data ? (data.patient_insurance_id ? 'insured' : 'particular') : preferred ? 'insured' : 'particular');
    setCompanyId(selected ? String(selected.insurance_company_id) : '');
    setPlanId(selected?.plan_id ? String(selected.plan_id) : '');
    setForm(data ? { patient_insurance_id: data.patient_insurance_id ? String(data.patient_insurance_id) : '', service: data.service, currency: data.currency,
      base_amount: data.base_amount, covered_amount: data.covered_amount, patient_copay: data.patient_copay, authorization_status: data.authorization_status,
      authorization_number: data.authorization_number || '', authorized_at: data.authorized_at || '', authorized_amount: data.authorized_amount || '',
      authorization_notes: data.authorization_notes || '', notes: data.notes || '', revision: data.revision } : { ...blank, patient_insurance_id: preferred ? String(preferred.id) : '' });
  }
  useEffect(() => {
    let active = true; setLoading(true); setBlocked(false); setError(''); setNotice('');
    Promise.all([api.get(path), api.get(`/insurance/patients/${appointment.patient_id}`), api.get('/insurance/authorization-states'), api.get('/insurance/companies'), api.get('/insurance/plans')])
      .then(([c, i, s, companiesResponse, plansResponse]) => { if (active) { setInsurances(i.data); setStates(s.data); setCompanies(companiesResponse.data); setPlans(plansResponse.data); apply(c.data, i.data, companiesResponse.data, plansResponse.data); } })
      .catch(e => { if (active) { setError(insuranceError(e)); setBlocked(true); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [appointment.id, appointment.patient_id]);
  const eligible = eligibleAffiliations(insurances, companies, plans, appointment.appointment_date);
  const selectedAffiliation = insurances.find(item => String(item.id) === form.patient_insurance_id);
  const historicalSelection = !!saved?.patient_insurance_id && saved.patient_insurance_id === selectedAffiliation?.id;
  const companyOptions = companies.filter(company => company.is_active || (historicalSelection && company.id === selectedAffiliation?.insurance_company_id));
  const planOptions = plans.filter(plan => plan.insurance_company_id === Number(companyId) && (plan.is_active || (historicalSelection && plan.id === selectedAffiliation?.plan_id)));
  const matchingAffiliations = eligible.filter(item => String(item.insurance_company_id) === companyId && String(item.plan_id || '') === planId);
  const affiliationOptions = historicalSelection && selectedAffiliation && !matchingAffiliations.some(item => item.id === selectedAffiliation.id)
    ? [selectedAffiliation, ...matchingAffiliations] : matchingAffiliations;
  function selectCompany(value: string) {
    const match = preferredAffiliation(eligible.filter(item => String(item.insurance_company_id) === value));
    setCompanyId(value); setPlanId(match?.plan_id ? String(match.plan_id) : '');
    setForm(current => ({ ...current, patient_insurance_id: match ? String(match.id) : '' }));
  }
  function selectPlan(value: string) {
    const match = preferredAffiliation(eligible.filter(item => String(item.insurance_company_id) === companyId && String(item.plan_id || '') === value));
    setPlanId(value); setForm(current => ({ ...current, patient_insurance_id: match ? String(match.id) : '' }));
  }
  async function save(e: FormEvent) {
    e.preventDefault(); setAttempted(true);
    if (!form.service.trim() || !form.currency.trim() || !form.base_amount.trim() || (coverageType === 'insured' && (!companyId || !form.patient_insurance_id || !form.covered_amount.trim() || !form.patient_copay.trim() || (form.authorization_status === 'authorized' && !form.authorization_number.trim())))) return;
    setSaving(true); setError(''); setNotice('');
    try { const { data } = await api.put(path, { ...form, patient_insurance_id: coverageType === 'insured' ? Number(form.patient_insurance_id) : null,
      covered_amount: coverageType === 'insured' ? form.covered_amount : '0.00', patient_copay: coverageType === 'insured' ? form.patient_copay : form.base_amount,
      authorization_status: coverageType === 'insured' ? form.authorization_status : 'not_required',
      authorization_number: coverageType === 'insured' ? form.authorization_number || null : null,
      authorized_at: coverageType === 'insured' ? form.authorized_at || null : null,
      authorized_amount: coverageType === 'insured' ? form.authorized_amount || null : null,
      authorization_notes: coverageType === 'insured' ? form.authorization_notes || null : null, notes: form.notes || null });
      apply(data, insurances, companies, plans); setNotice('Cobertura guardada. No se registró un cobro en Caja.');
    } catch (e: any) { setError(insuranceError(e)); setBlocked(e?.response?.status === 409); } finally { setSaving(false); }
  }
  async function reload() {
    setLoading(true);
    try {
      const [c, i, s, companiesResponse, plansResponse] = await Promise.all([api.get(path), api.get(`/insurance/patients/${appointment.patient_id}`), api.get('/insurance/authorization-states'), api.get('/insurance/companies'), api.get('/insurance/plans')]);
      setInsurances(i.data); setStates(s.data); setCompanies(companiesResponse.data); setPlans(plansResponse.data);
      apply(c.data, i.data, companiesResponse.data, plansResponse.data); setError(''); setBlocked(false);
    } catch(e) { setError(insuranceError(e)); setBlocked(true); } finally { setLoading(false); }
  }
  async function refreshAffiliations() {
    try {
      const { data } = await api.get(`/insurance/patients/${appointment.patient_id}`);
      setInsurances(data);
      if (coverageType === 'insured' && !form.patient_insurance_id) {
        const match = preferredAffiliation(eligibleAffiliations(data, companies, plans, appointment.appointment_date).filter(item => !companyId || String(item.insurance_company_id) === companyId));
        if (match) { setCompanyId(String(match.insurance_company_id)); setPlanId(match.plan_id ? String(match.plan_id) : ''); setForm(current => ({ ...current, patient_insurance_id: String(match.id) })); }
      }
    } catch(e) { setError(insuranceError(e)); }
  }
  return <Card compact><h3>Cobertura / Autorización</h3>
    <p className="atlas-help">Guardar la cobertura define importes y autorización de esta cita; no crea factura ni movimiento. Para registrar el pago del paciente, vaya a Finanzas → Nuevo cobro y confirme la operación.</p>
    {error && <Alert tone="danger" title="No se pudo completar la operación">{error}<Button variant="outline" onClick={() => void reload()}>Recargar cobertura</Button></Alert>}
    {notice && <Alert title={notice} />}
    {loading ? <LoadingState label="Cargando cobertura..." /> : <>
      {saved ? <><p>{saved.insurance_snapshot.company_name || 'Particular'}{saved.patient_insurance_id ? ` · ${saved.insurance_snapshot.plan_name || 'Sin plan'} · ${saved.insurance_snapshot.member_number || ''}` : ''}</p>
        <p>{saved.service} · Tarifa: {saved.base_amount} {saved.currency}</p><p>Paciente: {saved.patient_copay} {saved.currency} · Esperado de ARS: {saved.expected_insurer_balance} {saved.currency}</p><p>Autorización: {states.find(s => s.code === saved.authorization_status)?.label || saved.authorization_status} {saved.authorization_number}</p><p>{saved.authorized_amount && `Monto autorizado: ${saved.authorized_amount} ${saved.currency}`}</p>{saved.authorization_notes && <p>{saved.authorization_notes}</p>}{saved.notes && <p>{saved.notes}</p>}</> : <p>Sin cobertura registrada.</p>}
      {canWrite && (!closed || saved) && <form className="patient-form" onSubmit={save} onInvalid={() => setAttempted(true)}>
        <RequiredFieldsLegend />
        <fieldset className="agenda-appointment-mode"><legend>Tipo de cobertura <span aria-hidden="true" className="atlas-required-mark">*</span></legend>
          <div className="agenda-appointment-mode-options">
            <label className={coverageType === 'particular' ? 'is-selected' : ''}><input type="radio" name={`coverage-type-${appointment.id}`} value="particular" checked={coverageType === 'particular'} disabled={closed} required aria-required="true" onChange={() => setCoverageType('particular')} />Particular</label>
            <label className={coverageType === 'insured' ? 'is-selected' : ''}><input type="radio" name={`coverage-type-${appointment.id}`} value="insured" checked={coverageType === 'insured'} disabled={closed} required aria-required="true" onChange={() => { setCoverageType('insured'); if (form.authorization_status === 'not_required') setForm(current => ({ ...current, authorization_status: 'pending' })); }} />Con seguro</label>
          </div>
        </fieldset>
        {coverageType === 'insured' && <>
          <FormField label="Seguro / ARS" required error={attempted && !companyId ? 'Este campo es obligatorio.' : undefined}><Select value={companyId} disabled={closed} onChange={e => selectCompany(e.target.value)}><option value="">Seleccione...</option>{companyOptions.map(company => <option key={company.id} value={company.id}>{company.name}{!company.is_active ? ' (histórica)' : ''}</option>)}</Select></FormField>
          <FormField label="Plan" description="Opcional: el catálogo permite afiliaciones sin plan."><Select value={planId} disabled={closed || !companyId} onChange={e => selectPlan(e.target.value)}><option value="">Sin plan de catálogo</option>{planOptions.map(plan => <option key={plan.id} value={plan.id}>{plan.name}{!plan.is_active ? ' (histórico)' : ''}</option>)}</Select></FormField>
          {selectedAffiliation && !selectedAffiliation.plan_id && selectedAffiliation.plan_name && <p className="atlas-help">Plan registrado en la afiliación: {selectedAffiliation.plan_name}</p>}
          <FormField label="Afiliación del paciente" required error={attempted && !form.patient_insurance_id ? 'Registre o seleccione una afiliación válida del paciente.' : undefined}><Select value={form.patient_insurance_id} disabled={closed || !companyId} onChange={e => setForm({ ...form, patient_insurance_id: e.target.value })}><option value="">Seleccione...</option>{affiliationOptions.map(item => <option key={item.id} value={item.id}>{item.is_primary ? 'Principal' : 'Adicional'} · {item.plan_name || 'Sin plan'} · póliza terminada en {item.member_number.slice(-4)}{!item.is_active ? ' (histórica)' : ''}</option>)}</Select></FormField>
          {!closed && (!eligible.length || (companyId && !matchingAffiliations.length)) && <Alert tone="warning" title="Afiliación necesaria">Para guardar Con seguro, primero registre una afiliación vigente de este paciente con la ARS y el plan seleccionados.</Alert>}
          {!closed && <Button variant="outline" onClick={() => setEditingAffiliation(true)}>Registrar o editar seguro del paciente</Button>}
        </>}
        <FormField label="Servicio / procedimiento" required error={attempted && !form.service.trim() ? "Este campo es obligatorio." : undefined}><Input maxLength={200} value={form.service} onChange={e => setForm({ ...form, service: e.target.value })} /></FormField>
        <FormField label="Moneda" required error={attempted && !form.currency.trim() ? "Este campo es obligatorio." : undefined}><Input maxLength={3} pattern="[A-Z]{3}" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></FormField>
        <FormField label="Tarifa base" required error={attempted && !form.base_amount.trim() ? "Este campo es obligatorio." : undefined}><Input type="number" min="0" step="0.01" value={form.base_amount} onChange={e => setForm({ ...form, base_amount: e.target.value })} /></FormField>
        {coverageType === 'insured' && <>
          {([['covered_amount', 'Monto cubierto por ARS'], ['patient_copay', 'Copago del paciente'], ['authorized_amount', 'Monto autorizado']] as const).map(([key, label]) => <FormField key={key} label={label} required={key !== 'authorized_amount'} error={attempted && key !== 'authorized_amount' && !form[key].trim() ? "Este campo es obligatorio." : undefined}><Input type="number" min="0" step="0.01" value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></FormField>)}
          <p className="atlas-help">Tarifa base = monto ARS + copago. El monto esperado de ARS no representa un cobro ni garantiza aprobación.</p>
          <FormField label="Estado de autorización"><Select value={form.authorization_status} onChange={e => setForm({ ...form, authorization_status: e.target.value })}>{states.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}</Select></FormField>
          <FormField label="Número de autorización" required={form.authorization_status === 'authorized'} error={attempted && form.authorization_status === 'authorized' && !form.authorization_number.trim() ? "Este campo es obligatorio." : undefined}><Input maxLength={100} value={form.authorization_number} onChange={e => setForm({ ...form, authorization_number: e.target.value })} /></FormField>
          <FormField label="Fecha y hora de autorización"><Input type="datetime-local" value={form.authorized_at ? new Date(new Date(form.authorized_at).getTime() - new Date(form.authorized_at).getTimezoneOffset() * 60000).toISOString().slice(0,16) : ''} onChange={e => setForm({ ...form, authorized_at: e.target.value ? new Date(e.target.value).toISOString() : '' })} /></FormField>
          <p className="atlas-help">Hora local de este dispositivo.</p>
          <FormField label="Observaciones de autorización"><Input maxLength={1000} value={form.authorization_notes} onChange={e => setForm({ ...form, authorization_notes: e.target.value })} /></FormField>
        </>}
        <FormField label="Notas de cobertura"><Input maxLength={1000} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></FormField>
        <Button type="submit" loading={saving} disabled={blocked}>Guardar cobertura</Button>
      </form>}
      {editingAffiliation && <PatientInsurancePanel patientId={appointment.patient_id} patientName={appointment.patient_name || 'Paciente'} user={user} onClose={() => { setEditingAffiliation(false); void refreshAffiliations(); }} />}
    </>}
  </Card>;
}
