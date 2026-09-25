import { useEffect, useState } from 'react';
import type { User } from '../types/user';
import { api } from '../services/api';
import { financeError, kinds, methods, money, states, timestamp, type Invoice, type Method, type Movement, type Register } from '../services/finance';
import { Alert, Button, Card, FormField, Input, Select } from '../ui';
import FinanceCharge from '../components/FinanceCharge';
import './finance.css';

const tabs = ['Caja', 'Facturación', 'Movimientos del día', 'Cuentas pendientes de pacientes'];
type Summary = { collected: Record<Method, string>; reversed: Record<Method, string>; copays: string; private: string; patient_pending: string; ars_expected: string; adjustments: string };
type Action = { url: string; body: unknown; title: string };

export default function Finance({ user }: { user: User }) {
  const canRead = !!user.permissions?.includes('finance:read');
  const canCollect = !!user.permissions?.includes('finance:collect');
  const canManage = !!user.permissions?.includes('finance:manage');
  const [centers, setCenters] = useState<{ id: number; name: string }[]>([]);
  const [center, setCenter] = useState('');
  const [tab, setTab] = useState(0);
  const [day, setDay] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; });
  const [registers, setRegisters] = useState<Register[]>([]);
  const [registerId, setRegisterId] = useState('');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [opening, setOpening] = useState('0');
  const [notes, setNotes] = useState('');
  const [counted, setCounted] = useState('');
  const [reason, setReason] = useState('');
  const [adjustment, setAdjustment] = useState('');
  const [direction, setDirection] = useState('adjustment_in');
  const [charge, setCharge] = useState<Invoice | 'new' | null>(null);
  const [detail, setDetail] = useState<Invoice | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const register = registers.find(r => String(r.id) === registerId);
  const active = register?.state === 'open' && (register.opened_by === user.id || canManage) ? register : undefined;
  useEffect(() => {
    if (!canRead) return;
    const controller = new AbortController();
    api.get('/finance/centers', { signal: controller.signal }).then(r => { setCenters(r.data); setCenter(String(r.data[0]?.id || '')); }).catch(e => { if (!controller.signal.aborted) setError(financeError(e)); });
    return () => controller.abort();
  }, [canRead]);
  useEffect(() => {
    if (!center || !canRead) return;
    const controller = new AbortController(); setLoading(true); setError('');
    setRegisters([]); setSummary(null); setInvoices([]); setMovements([]);
    const params = { center_id: center, day, offset, limit: 50 };
    Promise.all([
      api.get('/finance/registers', { params: { center_id: center }, signal: controller.signal }),
      api.get('/finance/summary', { params, signal: controller.signal }),
      api.get('/finance/invoices', { params: { ...params, pending: tab === 3 }, signal: controller.signal }),
      api.get('/finance/movements', { params, signal: controller.signal }),
    ]).then(([r, s, i, m]) => { setRegisters(r.data); setSummary(s.data); setInvoices(i.data); setMovements(m.data); setRegisterId(old => r.data.some((x: Register) => String(x.id) === old) ? old : String(r.data.find((x: Register) => x.state === 'open' && x.opened_by === user.id)?.id || r.data[0]?.id || '')); })
      .catch(e => { if (!controller.signal.aborted) setError(financeError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [center, day, tab, offset, version, canRead, user.id]);
  function resetContext() { setOffset(0); setCharge(null); setDetail(null); setAction(null); setSuccess(''); setReason(''); }
  async function execute() {
    if (!action || busy) return;
    setBusy(true); setError('');
    try { await api.post(action.url, action.body); setAction(null); setSuccess('Operación registrada.'); setVersion(v => v + 1); setReason(''); setDetail(null); }
    catch (e) { setError(financeError(e)); }
    finally { setBusy(false); }
  }
  async function showInvoice(id: number) {
    setError(''); setBusy(true);
    try { const r = await api.get(`/finance/invoices/${id}`); setDetail(r.data); }
    catch (e) { setError(financeError(e)); } finally { setBusy(false); }
  }
  if (!canRead) return <Alert tone="danger" title="Sin permiso para Finanzas" />;
  return <section className="finance-workspace">
    <header><h1>Finanzas</h1><p>Caja y facturación interna · DOP</p></header>
    <div className="finance-controls">
      <FormField label="Centro"><Select value={center} disabled={busy || !!action || !!charge} onChange={e => { resetContext(); setRegisterId(''); setCenter(e.target.value); }}>{centers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></FormField>
      <FormField label="Día de movimientos"><Input type="date" required value={day} disabled={busy} onChange={e => { if (e.target.value) { resetContext(); setDay(e.target.value); } }} /></FormField>
      <Button variant="outline" disabled={loading || busy} onClick={() => setVersion(v => v + 1)}>Actualizar</Button>
      {canCollect && <Button disabled={!center || loading || busy || !!action || !!charge} onClick={() => { setDetail(null); setCharge('new'); }}>Nuevo cobro</Button>}
    </div>
    <nav aria-label="Secciones de Finanzas" className="finance-tabs">{tabs.map((t, i) => <Button key={t} variant={tab === i ? 'primary' : 'outline'} aria-current={tab === i ? 'page' : undefined} disabled={busy || !!action || !!charge} onClick={() => { resetContext(); setTab(i); }}>{t}</Button>)}</nav>
    {error && <Alert tone="danger" title={error} />}{success && <Alert tone="success" title={success} />}
    {loading && <p role="status">Cargando Finanzas…</p>}
    {action && <Card><h2>{action.title}</h2><p>Confirme para registrar esta operación en el historial.</p><Button loading={busy} onClick={() => void execute()}>Confirmar</Button><Button variant="outline" disabled={busy} onClick={() => setAction(null)}>Cancelar</Button></Card>}
    {charge && <FinanceCharge key={`${center}-${charge === 'new' ? 'new' : charge.id}`} centerId={Number(center)} register={active} invoice={charge === 'new' ? undefined : charge} onCancel={() => { setCharge(null); setVersion(v => v + 1); }} onDone={i => { setCharge(null); setDetail(null); setSuccess(`${i.number}: saldo del paciente ${money(i.balance)}.`); setVersion(v => v + 1); }} />}
    {tab === 0 && <>
      {summary && <><div className="finance-summary">
        <Card><h3>Copagos netos del día</h3><strong>{money(summary.copays)}</strong></Card><Card><h3>Particulares netos del día</h3><strong>{money(summary.private)}</strong></Card>
        <Card><h3>Pendiente de pacientes · total</h3><strong>{money(summary.patient_pending)}</strong></Card><Card><h3>ARS esperada · total</h3><strong>{money(summary.ars_expected)}</strong><p>No cobrada en Caja</p></Card>
      </div><Card><h2>Resumen del día</h2><MethodTotals collected={summary.collected} reversed={summary.reversed} /><p>Ajustes de efectivo: {money(summary.adjustments)}</p></Card></>}
      <Card><h2>Caja activa e historial reciente</h2>
        <FormField label="Caja"><Select value={registerId} onChange={e => { setRegisterId(e.target.value); setCounted(''); setNotes(''); }} disabled={busy || !!charge || !!action}><option value="">Seleccione</option>{registers.map(r => <option key={r.id} value={r.id}>#{r.id} · {r.state === 'open' ? 'Abierta' : 'Cerrada'} · Responsable #{r.opened_by} · {timestamp(r.opened_at)}</option>)}</Select></FormField>
        {register && <><p>Fondo inicial: {money(register.opening_amount)} · Efectivo esperado: <strong>{money(register.totals.expected_cash)}</strong></p><MethodTotals collected={register.totals.collected} reversed={register.totals.reversed} />
          <p>Ajustes: entradas {money(register.totals.adjustments_in)} / salidas {money(register.totals.adjustments_out)}</p>
          {register.state === 'closed' && <p>Cerrada por #{register.closed_by} · {timestamp(register.closed_at!)}<br />Efectivo contado: {money(register.counted_cash!)} · Diferencia: {money(register.difference!)}<br />{register.closing_notes}</p>}
        </>}
        {canCollect && active && <form onSubmit={e => { e.preventDefault(); setAction({ url: `/finance/registers/${active.id}/close`, body: { counted_cash: counted, notes }, title: `Cerrar caja #${active.id} · Contado ${money(counted)}` }); }}>
          <FormField label="Efectivo contado" required><Input type="number" min="0" step="0.01" value={counted} onChange={e => setCounted(e.target.value)} /></FormField>
          <p>Diferencia: {money(Number(counted || 0) - Number(active.totals.expected_cash))}</p>
          <FormField label="Observación de cierre" required={Number(counted) !== Number(active.totals.expected_cash)}><Input maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)} /></FormField>
          <Button type="submit" disabled={busy || !!action || !!charge}>Cerrar caja</Button>
        </form>}
        {canCollect && !registers.some(r => r.state === 'open' && r.opened_by === user.id) && <form onSubmit={e => { e.preventDefault(); setAction({ url: '/finance/registers', body: { center_id: Number(center), opening_amount: opening, notes }, title: `Abrir caja con ${money(opening)}` }); }}>
          <FormField label="Monto inicial" required><Input type="number" min="0" step="0.01" value={opening} onChange={e => setOpening(e.target.value)} /></FormField><FormField label="Observaciones de apertura"><Input maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)} /></FormField>
          <Button type="submit" disabled={!center || loading || busy || !!action}>Abrir caja</Button>
        </form>}
      </Card>
      {canManage && active && <Card><h2>Ajuste autorizado de efectivo</h2><form onSubmit={e => { e.preventDefault(); setAction({ url: `/finance/registers/${active.id}/adjustments`, body: { request_key: crypto.randomUUID(), kind: direction, amount: adjustment, reason }, title: `${kinds[direction]} · ${money(adjustment)}` }); }}>
        <FormField label="Tipo de ajuste"><Select value={direction} onChange={e => setDirection(e.target.value)}><option value="adjustment_in">Entrada</option><option value="adjustment_out">Salida</option></Select></FormField>
        <FormField label="Importe del ajuste" required><Input type="number" min="0.01" step="0.01" value={adjustment} onChange={e => setAdjustment(e.target.value)} /></FormField>
        <FormField label="Motivo del ajuste" required><Input maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></FormField><Button type="submit" disabled={busy || !!action}>Registrar ajuste</Button>
      </form></Card>}
    </>}
    {(tab === 1 || tab === 3) && <Card><h2>{tabs[tab]}</h2><div className="finance-table"><table><thead><tr><th>Documento / fecha</th><th>Paciente / concepto</th><th>Total</th><th>ARS esperada</th><th>Pagado por paciente</th><th>Saldo paciente</th><th>Estado</th><th>Acción</th></tr></thead><tbody>
      {invoices.map(i => <tr key={i.id}><td>{i.number}<br />{timestamp(i.created_at)}</td><td>{i.patient_name}<br />{i.concept}</td><td>{money(i.base_amount)}</td><td>{money(i.expected_ars)}</td><td>{money(i.paid_amount)}</td><td>{money(i.balance)}</td><td>{states[i.state]}</td><td><Button variant="ghost" disabled={busy} onClick={() => void showInvoice(i.id)}>Ver {i.number}</Button>{canCollect && Number(i.balance) > 0 && <Button disabled={busy || !!charge} onClick={() => { setDetail(null); setCharge(i); }}>Aplicar pago</Button>}</td></tr>)}
    </tbody></table></div>{!invoices.length && !loading && <p>No hay documentos en esta vista.</p>}<Pager offset={offset} count={invoices.length} change={setOffset} disabled={loading || busy} /></Card>}
    {(tab === 0 || tab === 2) && <Card><h2>Movimientos del día</h2><MovementList items={movements} onInvoice={id => void showInvoice(id)} />{!movements.length && !loading && <p>Sin movimientos.</p>}<Pager offset={offset} count={movements.length} change={setOffset} disabled={loading || busy} /></Card>}
    {detail && <Card><h2>{detail.number} · Documento interno</h2><p>{detail.patient_name} · {detail.concept} · {timestamp(detail.created_at)}</p><p>Total: {money(detail.base_amount)} · ARS: {money(detail.expected_ars)} · Obligación del paciente: {money(detail.patient_amount)}</p><p>Pagos netos: {money(detail.paid_amount)} · Saldo: {money(detail.balance)} · {states[detail.state]}</p><p>Sin validez fiscal DGII / e-CF.</p>
      <MovementList items={detail.movements || []} />
      {canManage && detail.state !== 'void' && <><FormField label="Motivo de reverso o anulación" required><Input maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></FormField>
        {(detail.movements || []).filter(m => m.kind === 'payment' && !detail.movements?.some(x => x.reverses_id === m.id)).map(m => <Button key={m.id} variant="outline" disabled={!active || !reason.trim() || busy || !!action} onClick={() => setAction({ url: `/finance/movements/${m.id}/reverse`, body: { register_id: active!.id, request_key: crypto.randomUUID(), reason }, title: `Revertir cobro #${m.id} · ${money(m.amount)} usando los métodos originales` })}>Revertir cobro #{m.id}</Button>)}
        {Number(detail.paid_amount) === 0 && <Button variant="danger" disabled={!reason.trim() || busy || !!action} onClick={() => setAction({ url: `/finance/invoices/${detail.id}/void`, body: { reason }, title: `Anular ${detail.number}` })}>Anular factura</Button>}
      </>}
      <Button variant="ghost" onClick={() => setDetail(null)}>Cerrar detalle</Button>
    </Card>}
  </section>;
}

function MethodTotals({ collected, reversed }: { collected: Record<Method, string>; reversed: Record<Method, string> }) {
  return <div className="finance-table"><table><thead><tr><th>Método</th><th>Cobrado</th><th>Revertido</th><th>Neto</th></tr></thead><tbody>{(Object.keys(methods) as Method[]).map(m => <tr key={m}><td>{methods[m]}</td><td>{money(collected[m])}</td><td>{money(reversed[m])}</td><td>{money(Number(collected[m]) - Number(reversed[m]))}</td></tr>)}</tbody></table></div>;
}
function MovementList({ items, onInvoice }: { items: Movement[]; onInvoice?: (id: number) => void }) {
  return <div className="finance-table"><table><thead><tr><th>Movimiento / fecha</th><th>Tipo / caja</th><th>Importe</th><th>Métodos / motivo</th><th>Documento</th></tr></thead><tbody>{items.map(m => <tr key={m.id}><td>#{m.id} · {timestamp(m.created_at)}</td><td>{kinds[m.kind]} · Caja #{m.register_id}</td><td>{money(m.amount)}</td><td>{m.parts.map(p => `${methods[p.method]} ${money(p.amount)}`).join(' + ')}<br />{m.reason}{m.reverses_id && ` · Reversa de #${m.reverses_id}`}</td><td>{m.invoice_id && (onInvoice ? <Button variant="ghost" onClick={() => onInvoice(m.invoice_id!)}>Factura #{m.invoice_id}</Button> : `#${m.invoice_id}`)}</td></tr>)}</tbody></table></div>;
}
function Pager({ offset, count, change, disabled }: { offset: number; count: number; change: (n: number) => void; disabled: boolean }) {
  return <div className="finance-controls"><Button variant="outline" disabled={disabled || offset === 0} onClick={() => change(Math.max(0, offset - 50))}>Anterior</Button><span>Página {offset / 50 + 1}</span><Button variant="outline" disabled={disabled || count < 50} onClick={() => change(offset + 50)}>Siguiente</Button></div>;
}
