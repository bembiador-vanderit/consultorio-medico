import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, Card, FormField, Input, LoadingState, Select } from "../../ui";
import { api } from "../../services/api";
import { insuranceError } from "../../services/insurance";
import type { Appointment } from "../../types/appointment";
import type { User } from "../../types/user";
import type { AppointmentInsuranceCoverage, PatientInsurance } from "../../types/insurance";
const blank = { patient_insurance_id: '', service: '', currency: 'DOP', base_amount: '0.00', covered_amount: '0.00', patient_copay: '0.00', authorization_status: 'pending', authorization_number: '', authorized_at: '', authorized_amount: '', authorization_notes: '', notes: '', revision: 0 };
export default function AppointmentInsurancePanel({ appointment, user }: { appointment: Appointment; user: User }) {
  const [saved, setSaved] = useState<AppointmentInsuranceCoverage | null>(null), [insurances, setInsurances] = useState<PatientInsurance[]>([]);
  const [form, setForm] = useState(blank), [states, setStates] = useState<{ code: string; label: string }[]>([]);
  const [blocked, setBlocked] = useState(false);
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const canWrite = !!user.permissions?.includes('insurance:manage') && !!user.permissions?.includes('patients:access');
  const closed = ['completed', 'cancelled', 'no_show'].includes(appointment.status);
  const path = `/insurance/appointments/${appointment.id}/coverage`;
  function apply(data: AppointmentInsuranceCoverage | null) {
    setSaved(data);
    setForm(data ? { patient_insurance_id: data.patient_insurance_id ? String(data.patient_insurance_id) : '', service: data.service, currency: data.currency,
      base_amount: data.base_amount, covered_amount: data.covered_amount, patient_copay: data.patient_copay, authorization_status: data.authorization_status,
      authorization_number: data.authorization_number || '', authorized_at: data.authorized_at || '', authorized_amount: data.authorized_amount || '',
      authorization_notes: data.authorization_notes || '', notes: data.notes || '', revision: data.revision } : blank);
  }
  useEffect(() => {
    let active = true; setLoading(true); setBlocked(false); setError(''); setNotice('');
    Promise.all([api.get(path), api.get(`/insurance/patients/${appointment.patient_id}`), api.get('/insurance/authorization-states')])
      .then(([c, i, s]) => { if (active) { apply(c.data); setInsurances(i.data); setStates(s.data); } })
      .catch(e => { if (active) { setError(insuranceError(e)); setBlocked(true); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [appointment.id, appointment.patient_id]);
  async function save(e: FormEvent) {
    e.preventDefault(); setSaving(true); setError(''); setNotice('');
    try { const { data } = await api.put(path, { ...form, patient_insurance_id: form.patient_insurance_id ? Number(form.patient_insurance_id) : null,
      authorization_number: form.authorization_number || null, authorized_at: form.authorized_at || null, authorized_amount: form.authorized_amount || null,
      authorization_notes: form.authorization_notes || null, notes: form.notes || null }); apply(data); setNotice('Cobertura guardada.');
    } catch (e: any) { setError(insuranceError(e)); setBlocked(e?.response?.status === 409); } finally { setSaving(false); }
  }
  async function reload() {
    setLoading(true);
    try {
      const [c, i, s] = await Promise.all([api.get(path), api.get(`/insurance/patients/${appointment.patient_id}`), api.get('/insurance/authorization-states')]);
      apply(c.data); setInsurances(i.data); setStates(s.data); setError(''); setBlocked(false);
    } catch(e) { setError(insuranceError(e)); setBlocked(true); } finally { setLoading(false); }
  }
  return <Card compact><h3>Cobertura / Autorización</h3>
    {error && <Alert tone="danger" title="No se pudo completar la operación">{error}<Button variant="outline" onClick={() => void reload()}>Recargar cobertura</Button></Alert>}
    {notice && <Alert title={notice} />}
    {loading ? <LoadingState label="Cargando cobertura..." /> : <>
      {saved ? <><p>{saved.insurance_snapshot.company_name || 'Particular'} · {saved.insurance_snapshot.plan_name || 'Sin plan'} · {saved.insurance_snapshot.member_number || ''}</p>
        <p>{saved.service} · Tarifa: {saved.base_amount} {saved.currency}</p><p>Paciente: {saved.patient_copay} {saved.currency} · Esperado de ARS: {saved.expected_insurer_balance} {saved.currency}</p><p>Autorización: {states.find(s => s.code === saved.authorization_status)?.label || saved.authorization_status} {saved.authorization_number}</p><p>{saved.authorized_amount && `Monto autorizado: ${saved.authorized_amount} ${saved.currency}`}</p>{saved.authorization_notes && <p>{saved.authorization_notes}</p>}{saved.notes && <p>{saved.notes}</p>}</> : <p>Sin cobertura registrada.</p>}
      {canWrite && (!closed || saved) && <form className="patient-form" onSubmit={save}>
        <FormField label="Seguro para esta cita"><Select value={form.patient_insurance_id} disabled={closed} onChange={e => setForm({ ...form, patient_insurance_id: e.target.value })}><option value="">Particular / sin seguro</option>
          {insurances.filter(i => i.is_active || i.id === saved?.patient_insurance_id).map(i => <option key={i.id} value={i.id}>{i.insurance_company_name} · {i.plan_name || 'Sin plan'} · {i.member_number}{i.is_primary ? ' · Principal' : ''}{!i.is_active ? ' · Inactivo (histórico)' : ''}</option>)}
        </Select></FormField>
        <FormField label="Servicio / procedimiento" required><Input maxLength={200} value={form.service} onChange={e => setForm({ ...form, service: e.target.value })} /></FormField>
        <FormField label="Moneda" required><Input maxLength={3} pattern="[A-Z]{3}" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></FormField>
        {([['base_amount', 'Tarifa base'], ['covered_amount', 'Monto cubierto por ARS'], ['patient_copay', 'Copago del paciente'], ['authorized_amount', 'Monto autorizado (opcional)']] as const).map(([key, label]) => <FormField key={key} label={label} required={key !== 'authorized_amount'}><Input type="number" min="0" step="0.01" value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></FormField>)}
        <p className="atlas-help">Tarifa base = monto ARS + copago. El monto esperado de ARS no representa un cobro ni garantiza aprobación.</p>
        <FormField label="Estado de autorización"><Select value={form.authorization_status} onChange={e => setForm({ ...form, authorization_status: e.target.value })}>{states.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}</Select></FormField>
        <FormField label="Número de autorización" required={form.authorization_status === 'authorized'}><Input maxLength={100} value={form.authorization_number} onChange={e => setForm({ ...form, authorization_number: e.target.value })} /></FormField>
        <FormField label="Fecha y hora de autorización"><Input type="datetime-local" value={form.authorized_at ? new Date(new Date(form.authorized_at).getTime() - new Date(form.authorized_at).getTimezoneOffset() * 60000).toISOString().slice(0,16) : ''} onChange={e => setForm({ ...form, authorized_at: e.target.value ? new Date(e.target.value).toISOString() : '' })} /></FormField>
        <p className="atlas-help">Hora local de este dispositivo.</p>
        <FormField label="Observaciones de autorización"><Input maxLength={1000} value={form.authorization_notes} onChange={e => setForm({ ...form, authorization_notes: e.target.value })} /></FormField>
        <FormField label="Notas de cobertura"><Input maxLength={1000} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></FormField>
        <Button type="submit" loading={saving} disabled={blocked}>Guardar cobertura</Button>
      </form>}
    </>}
  </Card>;
}
