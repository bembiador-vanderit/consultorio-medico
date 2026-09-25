import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { cents, financeError, methods, money, sumParts, type Invoice, type Part, type Preview, type Register } from '../services/finance';
import { Alert, Button, Card, FormField, Input, Select } from '../ui';
import FinancePaymentFields from './FinancePaymentFields';

type Confirmation = { url: string; body: unknown; label: string; base: string; ars: string; patient: string; received: number; balance: number };
export default function FinanceCharge({ centerId, register, invoice, onDone, onCancel }: { centerId: number; register?: Register; invoice?: Invoice; onDone: (invoice: Invoice) => void; onCancel: () => void }) {
  const [query, setQuery] = useState('');
  const [patients, setPatients] = useState<{ id: number; name: string }[]>([]);
  const [patient, setPatient] = useState('');
  const [appointments, setAppointments] = useState<{ id: number; date: string; status: string }[]>([]);
  const [appointment, setAppointment] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [concept, setConcept] = useState('Consulta');
  const [base, setBase] = useState('');
  const [parts, setParts] = useState<Part[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [attempted, setAttempted] = useState(false);
  const existing = invoice || preview?.invoice;
  useEffect(() => {
    if (query.trim().length < 2) { setPatients([]); return; }
    const controller = new AbortController();
    const timer = setTimeout(() => { api.get('/finance/patients', { params: { center_id: centerId, q: query.trim() }, signal: controller.signal }).then(r => setPatients(r.data)).catch(e => { if (!controller.signal.aborted) setError(financeError(e)); }); }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, centerId]);
  useEffect(() => {
    setPreview(null); setAppointments([]);
    if (!patient) return;
    const controller = new AbortController();
    api.get('/finance/appointments', { params: { center_id: centerId, patient_id: patient }, signal: controller.signal }).then(r => setAppointments(r.data)).catch(e => { if (!controller.signal.aborted) setError(financeError(e)); });
    return () => controller.abort();
  }, [patient, centerId]);
  useEffect(() => {
    setPreview(null);
    if (!patient) return;
    const controller = new AbortController(); setLoading(true);
    api.get('/finance/preview', { params: { center_id: centerId, patient_id: patient, appointment_id: appointment || undefined }, signal: controller.signal }).then(r => {
      setPreview(r.data); setConcept(r.data.coverage?.concept || 'Consulta'); setBase(r.data.coverage?.base_amount || '');
    }).catch(e => { if (!controller.signal.aborted) setError(financeError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [patient, appointment, centerId]);

  function review(e: React.FormEvent) {
    e.preventDefault(); setError('');
    const received = sumParts(parts);
    const amount = existing?.balance ?? preview?.coverage?.patient_amount ?? base;
    if ((!existing && (!preview || !patient || !concept.trim())) || !Number.isFinite(cents(amount)) || !Number.isFinite(received) || parts.some(p => !(cents(p.amount) > 0)) || received > cents(amount)) { setError('Revise los importes. El pago no puede exceder el saldo del paciente.'); return; }
    if (parts.length && !register) { setError('Abra una caja para registrar el cobro.'); return; }
    if (existing && !parts.length) { setError('Añada al menos un método de pago.'); return; }
    const payment = parts.length ? { register_id: register!.id, request_key: crypto.randomUUID(), parts } : null;
    setAttempted(false);
    setConfirm({ url: existing ? `/finance/invoices/${existing.id}/payments` : '/finance/invoices',
      body: existing ? payment : { request_key: crypto.randomUUID(), center_id: centerId, patient_id: Number(patient), appointment_id: appointment ? Number(appointment) : null, coverage_revision: preview?.coverage?.revision ?? null, concept, base_amount: base, payment },
      label: existing ? `${existing.number} · ${existing.patient_name}` : patients.find(p => p.id === Number(patient))?.name || '',
      base: existing?.base_amount ?? base, ars: existing?.ars_amount ?? preview?.coverage?.ars_amount ?? '0', patient: amount, received, balance: cents(amount) - received });
  }
  async function save() {
    if (!confirm || busy) return;
    setBusy(true); setError(''); setAttempted(true);
    try { const r = await api.post<Invoice>(confirm.url, confirm.body); onDone(r.data); }
    catch (e) { setError(financeError(e)); }
    finally { setBusy(false); }
  }
  return <Card><h2>{existing ? 'Aplicar pago al saldo' : 'Nuevo cobro'}</h2>
    {error && <Alert tone="danger" title={error} />}
    {confirm ? <div>
      <h3>Confirmar operación · {confirm.label}</h3>
      <p>Tarifa base: {money(confirm.base)} · ARS esperada: {money(confirm.ars)}</p>
      <p>Saldo del paciente antes del pago: {money(confirm.patient)}</p>
      <ul>{parts.map(p => <li key={p.method}>{methods[p.method]}: {money(p.amount)}</li>)}</ul>
      <p>Monto recibido: <strong>{money(confirm.received / 100)}</strong> · Saldo restante: <strong>{money(confirm.balance / 100)}</strong></p>
      <p>El monto ARS no ingresa a Caja. Documento interno sin comprobante fiscal.</p>
      <Button loading={busy} onClick={() => void save()}>{attempted ? 'Reintentar misma operación' : 'Confirmar operación'}</Button>
      <Button variant="outline" disabled={busy || attempted} onClick={() => setConfirm(null)}>Corregir</Button>
      {attempted && <p>Si no recibió confirmación, reintente esta misma operación. Para cambiarla, cierre y compruebe primero Facturación.</p>}
    </div> : <form onSubmit={review}>
      {!invoice && <>
        <FormField label="Buscar paciente"><Input value={query} onChange={e => { setQuery(e.target.value); setPatient(''); setAppointment(''); }} placeholder="Nombre o apellido (mínimo 2 letras)" /></FormField>
        <FormField label="Paciente" required><Select value={patient} onChange={e => { setPatient(e.target.value); setAppointment(''); }}><option value="">Seleccione</option>{patients.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></FormField>
        <FormField label="Cita / atención"><Select value={appointment} onChange={e => setAppointment(e.target.value)}><option value="">Servicio particular sin cita</option>{appointments.map(a => <option key={a.id} value={a.id}>#{a.id} · {a.date} · {a.status}</option>)}</Select></FormField>
      </>}
      {existing ? <p>{existing.number} · {existing.patient_name} · {existing.concept}<br />Saldo paciente: {money(existing.balance)} · ARS esperada: {money(existing.ars_amount)}</p> : <>
        <FormField label="Concepto" required><Input maxLength={200} value={concept} disabled={!!preview?.coverage} onChange={e => setConcept(e.target.value)} /></FormField>
        <FormField label="Tarifa base" required><Input type="number" min="0" step="0.01" max="9999999999.99" value={base} disabled={!!preview?.coverage} onChange={e => setBase(e.target.value)} /></FormField>
        {preview?.coverage && <p>Cobertura: {preview.coverage.insurance.company_name || 'Particular'} · Autorización: {preview.coverage.authorization_status}<br />Cubierto por ARS: {money(preview.coverage.ars_amount)} · Copago / obligación del paciente: {money(preview.coverage.patient_amount)}</p>}
      </>}
      <FinancePaymentFields parts={parts} onChange={setParts} />
      {!register && <p>Sin caja abierta. Puede emitir una factura pendiente; para recibir pagos debe abrir Caja.</p>}
      <Button type="submit" disabled={loading || (!invoice && !preview)}>Revisar cobro</Button>
    </form>}
    <Button variant="ghost" disabled={busy} onClick={onCancel}>Cerrar formulario</Button>
  </Card>;
}
