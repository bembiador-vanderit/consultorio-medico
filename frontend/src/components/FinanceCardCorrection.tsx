import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { financeError, type CardProvider, type Movement, type ProviderSetting } from '../services/finance';
import { Alert, Button, FormField, Input, Select } from '../ui';

export default function FinanceCardCorrection({ centerId, movement, onDone }: {
  centerId: number; movement: Movement; onDone: () => void;
}) {
  const card = movement.parts.find(p => p.method === 'card');
  const [providers, setProviders] = useState<CardProvider[]>([]);
  const [provider, setProvider] = useState<CardProvider | ''>(card?.provider || '');
  const [batch, setBatch] = useState(card?.batch_number || '');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api.get<ProviderSetting[]>(`/finance/centers/${centerId}/card-providers`, { signal: controller.signal })
      .then(r => setProviders(r.data.filter(p => p.enabled).map(p => p.provider)))
      .catch(e => { if (!controller.signal.aborted) setError(financeError(e)); });
    return () => controller.abort();
  }, [centerId]);
  if (!card) return null;
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api.put(`/finance/movements/${movement.id}/card-assignment`, { provider, batch_number: batch.trim(), reason: reason.trim() });
      onDone();
    } catch (e) { setError(financeError(e)); } finally { setBusy(false); }
  }
  return <details><summary>Corregir prestadora o lote · Movimiento #{movement.id}</summary>
    <p>El importe del cobro no cambia. Si el lote de origen está cerrado, reábralo primero. La corrección queda auditada.</p>
    {error && <Alert tone="danger" title={error} />}
    <form onSubmit={e => void save(e)}>
      <FormField label={`Prestadora corregida #${movement.id}`} required><Select value={provider} onChange={e => setProvider(e.target.value as CardProvider)}>
        <option value="">Seleccione</option>{providers.map(p => <option key={p} value={p}>{p}</option>)}
      </Select></FormField>
      <FormField label={`Lote corregido #${movement.id}`} required><Input maxLength={40} value={batch} onChange={e => setBatch(e.target.value)} /></FormField>
      <FormField label={`Motivo de corrección #${movement.id}`} required><Input maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></FormField>
      <Button type="submit" disabled={busy || !provider || !batch.trim() || !reason.trim()}>Guardar corrección auditada</Button>
    </form>
  </details>;
}
