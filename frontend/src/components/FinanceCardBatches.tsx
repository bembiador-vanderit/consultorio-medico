import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { financeError, money, timestamp, type CardBatch, type CardBatchEvent, type ProviderSetting, type Register } from '../services/finance';
import { Alert, Button, Card, FormField, Input } from '../ui';

export default function FinanceCardBatches({ centerId, register, canManage, canCollect, onChanged }: {
  centerId: number; register: Register; canManage: boolean; canCollect: boolean; onChanged: () => void;
}) {
  const [providers, setProviders] = useState<ProviderSetting[]>([]);
  const [batches, setBatches] = useState<CardBatch[]>([]);
  const [history, setHistory] = useState<CardBatchEvent[]>([]);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.get<ProviderSetting[]>(`/finance/centers/${centerId}/card-providers`, { signal: controller.signal }),
      api.get<CardBatch[]>(`/finance/registers/${register.id}/card-batches`, { signal: controller.signal }),
      api.get<CardBatchEvent[]>(`/finance/registers/${register.id}/card-batch-history`, { signal: controller.signal }),
    ]).then(([p, b, h]) => { setProviders(p.data); setBatches(b.data); setHistory(h.data); })
      .catch(e => { if (!controller.signal.aborted) setError(financeError(e)); });
    return () => controller.abort();
  }, [centerId, register.id, version]);
  async function updateProvider(provider: ProviderSetting) {
    setBusy(true); setError('');
    try {
      await api.put(`/finance/centers/${centerId}/card-providers/${provider.provider}`, { enabled: !provider.enabled });
      setMessage(`${provider.provider}: ${provider.enabled ? 'desactivada' : 'activada'} para este centro.`);
      setVersion(v => v + 1); onChanged();
    } catch (e) { setError(financeError(e)); } finally { setBusy(false); }
  }
  async function submit(url: string, body: unknown) {
    setBusy(true); setError('');
    try {
      await api.post(url, body);
      setMessage('Cambio registrado en el historial de lotes.'); setVersion(v => v + 1); onChanged();
    } catch (e) { setError(financeError(e)); } finally { setBusy(false); }
  }
  return <Card><h2>Lotes de tarjeta · Caja #{register.id}</h2>
    <p>Cada prestadora y número de lote se cuadra solo con los cobros de esta caja. El cierre no equivale a conciliación bancaria.</p>
    {error && <Alert tone="danger" title={error} />}{message && <Alert tone="success" title={message} />}
    {canManage && <div><h3>Prestadoras disponibles en este centro</h3>
      {providers.map(p => <label key={p.provider} style={{ marginRight: 16 }}><input type="checkbox" checked={p.enabled} disabled={busy}
        onChange={() => void updateProvider(p)} /> {p.provider}</label>)}
    </div>}
    {!batches.length && <p>Esta caja no tiene cobros con tarjeta ni lotes registrados.</p>}
    {batches.map(batch => <BatchControl key={`${batch.provider}-${batch.batch_number}`} batch={batch} busy={busy}
      canClose={(register.state === 'open' && canCollect) || canManage} canReopen={canManage}
      onClose={body => submit(`/finance/registers/${register.id}/card-batches`, body)}
      onReopen={reason => submit(`/finance/card-batches/${batch.id}/reopen`, { reason })} />)}
    {history.length > 0 && <details><summary>Historial auditable de lotes ({history.length})</summary><ol>
      {history.map(event => <li key={event.id}>{timestamp(event.created_at)} · Usuario #{event.actor_id} · {
        { provider_config: 'Configuración de prestadora', close: 'Cierre', reopen: 'Reapertura', assignment_correction: 'Corrección de cobro' }[event.action] || event.action}
        {event.movement_id ? ` · Movimiento #${event.movement_id}` : ''}
        {event.reason ? ` · Motivo: ${event.reason}` : ''}
        <br /><small>Antes: {JSON.stringify(event.before)} · Después: {JSON.stringify(event.after)}</small></li>)}
    </ol></details>}
  </Card>;
}

function BatchControl({ batch, busy, canClose, canReopen, onClose, onReopen }: {
  batch: CardBatch; busy: boolean; canClose: boolean; canReopen: boolean;
  onClose: (body: unknown) => Promise<void>; onReopen: (reason: string) => Promise<void>;
}) {
  const [count, setCount] = useState(String(batch.atlas_count));
  const [amount, setAmount] = useState(batch.atlas_amount);
  const [notes, setNotes] = useState('');
  const difference = Number(count) !== batch.atlas_count || Number(amount) !== Number(batch.atlas_amount);
  return <section className="atlas-form-section"><h3>{batch.provider || 'Prestadora pendiente'} · Lote {batch.batch_number || 'sin identificar'}</h3>
    <p>Atlas: {batch.atlas_count} transacciones netas · {money(batch.atlas_amount)} · {batch.state === 'closed' ? 'Cerrado' : 'Pendiente de cierre'}</p>
    {batch.state === 'closed' && <p>Voucher POS: {batch.declared_count} · {money(batch.declared_amount || 0)}<br />
      Diferencia: {batch.count_difference} transacciones · {money(batch.amount_difference || 0)}<br />
      Cerrado por usuario #{batch.closed_by} · {batch.closed_at && timestamp(batch.closed_at)}</p>}
    {batch.state === 'open' && canClose && batch.provider && batch.batch_number && <form onSubmit={e => { e.preventDefault(); void onClose({
      provider: batch.provider, batch_number: batch.batch_number, declared_count: Number(count), declared_amount: amount, notes }); }}>
      <FormField label={`Cantidad del voucher ${batch.provider} ${batch.batch_number}`} required><Input type="number" min="0" step="1" value={count} onChange={e => setCount(e.target.value)} /></FormField>
      <FormField label={`Monto del voucher ${batch.provider} ${batch.batch_number}`} required><Input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></FormField>
      <FormField label="Motivo de diferencia" required={difference}><Input maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)} /></FormField>
      <Button type="submit" disabled={busy || !count || !amount || (difference && !notes.trim())}>Cerrar lote</Button>
    </form>}
    {batch.state === 'closed' && canReopen && <form onSubmit={e => { e.preventDefault(); void onReopen(notes); }}>
      <FormField label={`Motivo para reabrir lote ${batch.provider} ${batch.batch_number}`} required><Input maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)} /></FormField>
      <Button type="submit" variant="outline" disabled={busy || !notes.trim()}>Reabrir para corrección</Button>
    </form>}
  </section>;
}
