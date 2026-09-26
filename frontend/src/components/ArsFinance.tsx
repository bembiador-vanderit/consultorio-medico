import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { financeError, money } from '../services/finance';
import type { User } from '../types/user';
import { Alert, Button, Card, FormField, Input, Select } from '../ui';

type Company = { id: number; name: string };
type Claim = { id: number; center_id: number; patient_id: number; appointment_id: number; patient_name: string; insurance_company_id: number; service_date: string; state: string; display_state: string; claimed_amount: string; approved_amount: string | null; disputed_amount: string; paid_amount: string; balance: string; snapshot: { insurance?: { company_name?: string; plan_name?: string }; authorization_number?: string; authorization_status?: string; service?: string }; events?: Array<{ id: number; kind: string; note: string | null; code: string | null; amount: string | null; created_at: string }>; applications?: Application[]; aging_bucket?: string; days_open?: number };
type Remittance = { id: number; center_id: number | null; insurance_company_id: number; company_name: string; received_on: string; reference: string; amount: string; applied_amount: string; unapplied: string; applications?: Application[] };
type Application = { id: number; claim_id: number; amount: string; reversed_at: string | null; reversal_reason: string | null };
type Summary = { insurance_company_id: number; company_name: string; claims: number; claimed: string; approved: string; collectible: string; disputed: string; paid: string; pending: string; aging: Record<string, string> };
const states: Record<string, string> = { draft: 'Borrador', pending: 'Pendiente de enviar', sent: 'Enviada', received: 'Recibida / en revisión', glosed: 'Glosada', rejected: 'Rechazada', corrected: 'Corregida', resent: 'Reenviada', partial: 'Pago parcial', paid: 'Pagada', cancelled: 'Cancelada' };
const moves: Record<string, string[]> = { draft: ['pending', 'cancelled'], pending: ['sent', 'cancelled'], sent: ['received', 'cancelled'], received: ['cancelled'], glosed: ['corrected', 'cancelled'], rejected: ['corrected', 'cancelled'], corrected: ['resent', 'cancelled'], resent: ['received', 'cancelled'] };
const today = () => new Date().toISOString().slice(0, 10);

export default function ArsFinance({ section, centerId, user }: { section: number; centerId: number; user: User }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [company, setCompany] = useState('');
  const [state, setState] = useState('');
  const [fromDate, setFromDate] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [toDate, setToDate] = useState(today);
  const [patientSearch, setPatientSearch] = useState('');
  const [appointments, setAppointments] = useState<{ id: number; date: string; patient_name: string; coverage_revision: number; ars_amount: string }[]>([]);
  const [appointmentId, setAppointmentId] = useState('');
  const coverageRevision = appointments.find(a => String(a.id) === appointmentId)?.coverage_revision || null;
  const [claims, setClaims] = useState<Claim[]>([]);
  const [remittances, setRemittances] = useState<Remittance[]>([]);
  const [receivables, setReceivables] = useState<Claim[]>([]);
  const [summary, setSummary] = useState<Summary[]>([]);
  const [detail, setDetail] = useState<Claim | null>(null);
  const [remittance, setRemittance] = useState<Remittance | null>(null);
  const [reference, setReference] = useState('');
  const [receivedOn, setReceivedOn] = useState(today);
  const [remittanceAmount, setRemittanceAmount] = useState('');
  const [allocation, setAllocation] = useState<Record<number, string>>({});
  const [reason, setReason] = useState('');
  const [glosaAmount, setGlosaAmount] = useState('');
  const [glosaCode, setGlosaCode] = useState('');
  const [glosaKind, setGlosaKind] = useState<'glosed' | 'rejected'>('glosed');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const [offset, setOffset] = useState(0);
  const canClaim = user.permissions?.includes('ars:claim');
  const canSend = user.permissions?.includes('ars:send');
  const canGlosa = user.permissions?.includes('ars:glosa');
  const canPayment = user.permissions?.includes('ars:payment');
  useEffect(() => { if (user.permissions?.includes('ars:read')) void api.get<Company[]>('/ars/companies').then(r => setCompanies(r.data)).catch(e => setError(financeError(e))); }, [user.permissions]);
  useEffect(() => {
    if (!centerId || !user.permissions?.includes('ars:read')) return;
    const controller = new AbortController();
    const params = { center_id: centerId, insurance_company_id: company || undefined,
      state: section === 0 ? state || undefined : undefined,
      from_date: section === 0 ? fromDate : undefined, to_date: section === 0 ? toDate : undefined,
      patient_name: section === 0 ? patientSearch || undefined : undefined,
      offset: section === 0 ? offset : 0, limit: section === 1 ? 100 : 50 };
    void Promise.all([
      api.get<Claim[]>('/ars/claims', { params, signal: controller.signal }),
      api.get<Remittance[]>('/ars/remittances', { params: { center_id: centerId, insurance_company_id: company || undefined, offset: section === 1 ? offset : 0 }, signal: controller.signal }),
      user.permissions?.includes('ars:report') ? api.get<Claim[]>('/ars/receivables', { params: { center_id: centerId, insurance_company_id: company || undefined, state: section === 2 ? state || undefined : undefined, patient_name: section === 2 ? patientSearch || undefined : undefined, offset: section === 2 ? offset : 0 }, signal: controller.signal }) : Promise.resolve({ data: [] as Claim[] }),
      user.permissions?.includes('ars:reconcile') ? api.get<Summary[]>('/ars/reconciliation', { params: { center_id: centerId, from_date: fromDate, to_date: toDate }, signal: controller.signal }) : Promise.resolve({ data: [] as Summary[] }),
    ]).then(([c, r, x, s]) => { if (!controller.signal.aborted) { setClaims(c.data); setRemittances(r.data); setReceivables(x.data); setSummary(s.data); } }).catch(e => { if (!controller.signal.aborted) setError(financeError(e)); });
    return () => controller.abort();
  }, [centerId, company, state, fromDate, toDate, version, user.permissions, section, patientSearch, offset]);
  useEffect(() => { setOffset(0); }, [centerId, section]);
  useEffect(() => {
    if (!centerId || patientSearch.trim().length < 2 || !canClaim) { setAppointments([]); return; }
    const handle = setTimeout(() => { void api.get('/ars/eligible-appointments', { params: { center_id: centerId, q: patientSearch } }).then(r => setAppointments(r.data)).catch(e => setError(financeError(e))); }, 250);
    return () => clearTimeout(handle);
  }, [centerId, patientSearch, canClaim]);
  async function run(url: string, body: unknown, after?: () => void) {
    setBusy(true); setError('');
    try { await api.post(url, body); setVersion(v => v + 1); setReason(''); after?.(); }
    catch (e) { setError(financeError(e)); }
    finally { setBusy(false); }
  }
  async function showClaim(id: number) { try { setDetail((await api.get<Claim>(`/ars/claims/${id}`)).data); } catch (e) { setError(financeError(e)); } }
  async function showRemittance(id: number) { try { setRemittance((await api.get<Remittance>(`/ars/remittances/${id}`)).data); } catch (e) { setError(financeError(e)); } }
  if (!user.permissions?.includes('ars:read')) return <Alert tone="danger" title="Sin permiso para Reclamaciones ARS" />;
  return <div className="ars-workspace">
    {error && <Alert tone="danger" title={error} />}
    <div className="finance-controls">
      <FormField label="Aseguradora"><Select value={company} onChange={e => { setOffset(0); setCompany(e.target.value); }}><option value="">Todas</option>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></FormField>
      {(section === 0 || section === 2) && <FormField label="Estado"><Select value={state} onChange={e => { setOffset(0); setState(e.target.value); }}><option value="">Todos</option>{Object.entries(states).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></FormField>}
      {(section === 0 || section === 3) && <><FormField label="Desde"><Input type="date" value={fromDate} onChange={e => { setOffset(0); setFromDate(e.target.value); }} /></FormField><FormField label="Hasta"><Input type="date" value={toDate} onChange={e => { setOffset(0); setToDate(e.target.value); }} /></FormField></>}
      <Button variant="outline" onClick={() => setVersion(v => v + 1)}>Actualizar</Button>
    </div>
    {section === 0 && <>
      {canClaim && <Card><h2>Nueva reclamación desde cobertura</h2><div className="finance-controls"><FormField label="Buscar paciente"><Input value={patientSearch} onChange={e => { setOffset(0); setPatientSearch(e.target.value); }} placeholder="Nombre o apellido" /></FormField><FormField label="Cita asegurada"><Select value={appointmentId} onChange={e => setAppointmentId(e.target.value)}><option value="">Seleccione</option>{appointments.map(a => <option key={a.id} value={a.id}>{a.date} · {a.patient_name} · #{a.id} · ARS {money(a.ars_amount)}</option>)}</Select></FormField><Button disabled={!coverageRevision || busy} onClick={() => void run('/ars/claims', { appointment_id: Number(appointmentId), coverage_revision: coverageRevision }, () => { setAppointmentId(''); setPatientSearch(''); })}>Crear reclamación</Button></div>{appointmentId && !coverageRevision && <p>La cita no tiene cobertura ARS disponible.</p>}</Card>}
      <Card><h2>Reclamaciones ARS</h2><div className="ars-table-wrap"><table><thead><tr><th>Fecha</th><th>Paciente</th><th>ARS</th><th>Reclamado</th><th>Pagado</th><th>Pendiente</th><th>Estado</th><th></th></tr></thead><tbody>{claims.map(c => <tr key={c.id}><td>{c.service_date}</td><td>{c.patient_name}</td><td>{c.snapshot.insurance?.company_name}</td><td>{money(c.claimed_amount)}</td><td>{money(c.paid_amount)}</td><td>{money(c.balance)}</td><td>{states[c.display_state] || c.display_state}</td><td><Button variant="outline" onClick={() => void showClaim(c.id)}>Detalle</Button></td></tr>)}</tbody></table></div></Card>
      {detail && <Card><h2>Reclamación #{detail.id}</h2><p>{detail.patient_name} · {detail.snapshot.service} · {detail.snapshot.insurance?.company_name} / {detail.snapshot.insurance?.plan_name || 'Sin plan'}</p><p>Cobertura original: {money(detail.claimed_amount)} · Autorización: {detail.snapshot.authorization_status || '—'} {detail.snapshot.authorization_number || ''}</p><p>Aprobado: {detail.approved_amount === null ? 'Pendiente' : money(detail.approved_amount)} · Glosado: {money(detail.disputed_amount)} · Pagado: {money(detail.paid_amount)} · Saldo: {money(detail.balance)}</p><h3>Historial</h3><ul>{detail.events?.map(e => <li key={e.id}>{e.created_at} · {states[e.kind] || e.kind} {e.code || ''} {e.note || ''} {e.amount ? money(e.amount) : ''}</li>)}</ul><h3>Pagos aplicados</h3><ul>{detail.applications?.map(a => <li key={a.id}>#{a.id} · {money(a.amount)} {a.reversed_at ? `· Revertido: ${a.reversal_reason}` : ''}</li>)}</ul>
        {canSend && (moves[detail.state] || []).filter(next => next !== 'corrected').map(next => <Button key={next} variant="outline" disabled={busy} onClick={() => { const note = next === 'cancelled' ? prompt('Motivo de cancelación') : null; if (next !== 'cancelled' || note) void run(`/ars/claims/${detail.id}/transition`, { state: next, note }, () => void showClaim(detail.id)); }}>{states[next]}</Button>)}
        {canClaim && ['glosed', 'rejected'].includes(detail.state) && <div className="finance-controls"><FormField label="Nuevo monto aprobado"><Input type="number" min="0" max={detail.claimed_amount} step="0.01" value={glosaAmount} onChange={e => setGlosaAmount(e.target.value)} /></FormField><FormField label="Motivo de corrección"><Input value={reason} onChange={e => setReason(e.target.value)} /></FormField><Button disabled={busy || !reason || !glosaAmount} onClick={() => void run(`/ars/claims/${detail.id}/correction`, { approved_amount: glosaAmount, note: reason }, () => void showClaim(detail.id))}>Corregir y preparar reenvío</Button></div>}
        {canGlosa && ['sent', 'received', 'resent'].includes(detail.state) && <div className="finance-controls"><FormField label="Resultado"><Select value={glosaKind} onChange={e => setGlosaKind(e.target.value as 'glosed' | 'rejected')}><option value="glosed">Glosa</option><option value="rejected">Rechazo</option></Select></FormField><FormField label="Monto glosado"><Input type="number" min="0.01" step="0.01" value={glosaAmount} onChange={e => setGlosaAmount(e.target.value)} /></FormField><FormField label="Código"><Input value={glosaCode} onChange={e => setGlosaCode(e.target.value)} /></FormField><FormField label="Motivo"><Input value={reason} onChange={e => setReason(e.target.value)} /></FormField><Button disabled={busy || !reason || !glosaAmount} onClick={() => void run(`/ars/claims/${detail.id}/glosa`, { kind: glosaKind, amount: glosaAmount, code: glosaCode || null, note: reason }, () => void showClaim(detail.id))}>Registrar glosa</Button></div>}
        <Button variant="outline" onClick={() => setDetail(null)}>Cerrar</Button></Card>}
    </>}
    {section === 1 && <>
      {canPayment && <Card><h2>Registrar pago ARS / remesa</h2><div className="finance-controls"><FormField label="Aseguradora"><Select value={company} onChange={e => setCompany(e.target.value)}><option value="">Seleccione</option>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></FormField><FormField label="Fecha de recepción"><Input type="date" value={receivedOn} onChange={e => setReceivedOn(e.target.value)} /></FormField><FormField label="Referencia"><Input value={reference} onChange={e => setReference(e.target.value)} /></FormField><FormField label="Monto DOP"><Input type="number" min="0.01" step="0.01" value={remittanceAmount} onChange={e => setRemittanceAmount(e.target.value)} /></FormField><Button disabled={busy || !company || !reference || !remittanceAmount} onClick={() => void run('/ars/remittances', { center_id: centerId, insurance_company_id: Number(company), received_on: receivedOn, reference, amount: remittanceAmount }, () => { setReference(''); setRemittanceAmount(''); })}>Registrar remesa</Button></div></Card>}
      <Card><h2>Remesas</h2><div className="ars-table-wrap"><table><thead><tr><th>Fecha</th><th>ARS</th><th>Referencia</th><th>Total</th><th>Aplicado</th><th>Sin aplicar</th><th></th></tr></thead><tbody>{remittances.map(r => <tr key={r.id}><td>{r.received_on}</td><td>{r.company_name}</td><td>{r.reference}</td><td>{money(r.amount)}</td><td>{money(r.applied_amount)}</td><td>{money(r.unapplied)}</td><td><Button variant="outline" onClick={() => void showRemittance(r.id)}>Detalle</Button></td></tr>)}</tbody></table></div></Card>
      {remittance && <Card><h2>Remesa {remittance.reference}</h2><p>Disponible para aplicar: {money(remittance.unapplied)}</p><h3>Aplicaciones</h3><ul>{remittance.applications?.map(a => <li key={a.id}>Reclamación #{a.claim_id}: {money(a.amount)} {a.reversed_at ? '· Revertida' : canPayment && <Button variant="outline" onClick={() => { const note = prompt('Motivo del reverso'); if (note) void run(`/ars/applications/${a.id}/reverse`, { reason: note }, () => void showRemittance(remittance.id)); }}>Revertir</Button>}</li>)}</ul>
        {canPayment && Number(remittance.unapplied) > 0 && <><h3>Distribuir entre reclamaciones</h3>{claims.filter(c => c.insurance_company_id === remittance.insurance_company_id && Number(c.balance) > 0 && ['sent', 'received', 'resent', 'glosed', 'rejected'].includes(c.state)).map(c => <FormField key={c.id} label={`#${c.id} · ${c.patient_name} · saldo ${money(c.balance)}`}><Input type="number" min="0" max={c.balance} step="0.01" value={allocation[c.id] || ''} onChange={e => setAllocation(old => ({ ...old, [c.id]: e.target.value }))} /></FormField>)}<p>Distribuido: {money(String(Object.values(allocation).reduce((sum, value) => sum + (Number(value) || 0), 0)))}</p><Button disabled={busy || Object.values(allocation).every(v => !Number(v))} onClick={() => void run(`/ars/remittances/${remittance.id}/apply`, { allocations: Object.entries(allocation).filter(([, amount]) => Number(amount) > 0).map(([claim_id, amount]) => ({ claim_id: Number(claim_id), amount })) }, () => { setAllocation({}); void showRemittance(remittance.id); })}>Aplicar importes</Button></>}
        <Button variant="outline" onClick={() => { setRemittance(null); setAllocation({}); }}>Cerrar</Button></Card>}
    </>}
    {section === 2 && <Card><h2>Cuentas por cobrar ARS</h2><FormField label="Paciente"><Input value={patientSearch} onChange={e => { setOffset(0); setPatientSearch(e.target.value); }} placeholder="Filtrar por nombre" /></FormField><div className="ars-table-wrap"><table><thead><tr><th>Paciente</th><th>Fecha</th><th>ARS</th><th>Estado</th><th>Reclamado</th><th>Pagado</th><th>Pendiente</th><th>Antigüedad</th></tr></thead><tbody>{receivables.map(c => <tr key={c.id}><td>{c.patient_name}</td><td>{c.service_date}</td><td>{c.snapshot.insurance?.company_name}</td><td>{states[c.display_state] || c.display_state}</td><td>{money(c.claimed_amount)}</td><td>{money(c.paid_amount)}</td><td>{money(c.balance)}</td><td>{c.aging_bucket} ({c.days_open} días)</td></tr>)}</tbody></table></div></Card>}
    {section === 3 && <Card><h2>Conciliación por ARS y período</h2><div className="ars-table-wrap"><table><thead><tr><th>ARS</th><th>Reclamaciones</th><th>Reclamado</th><th>Aprobado</th><th>Cobrable</th><th>Glosado</th><th>Pagado</th><th>Pendiente</th><th>Aging</th></tr></thead><tbody>{summary.map(s => <tr key={s.insurance_company_id}><td>{s.company_name}</td><td>{s.claims}</td><td>{money(s.claimed)}</td><td>{money(s.approved)}</td><td>{money(s.collectible)}</td><td>{money(s.disputed)}</td><td>{money(s.paid)}</td><td>{money(s.pending)}</td><td>{Object.entries(s.aging).map(([key, value]) => `${key}: ${money(value)}`).join(' · ')}</td></tr>)}</tbody></table></div></Card>}
    {section !== 3 && <div className="finance-controls"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Anterior</Button><span>Página {Math.floor(offset / 50) + 1}</span><Button variant="outline" disabled={(section === 0 ? claims : section === 1 ? remittances : receivables).length < 50} onClick={() => setOffset(n => n + 50)}>Siguiente</Button></div>}
  </div>;
}
