import { Button, FormField, Input, Select } from '../ui';
import { methods, money, sumParts, type CardProvider, type Method, type Part } from '../services/finance';

export default function FinancePaymentFields({ parts, providers, onChange }: { parts: Part[]; providers: CardProvider[]; onChange: (parts: Part[]) => void }) {
  const addable = (Object.keys(methods) as Method[]).filter(m => (m !== 'card' || providers.length > 0) && !parts.some(p => p.method === m));
  return <fieldset className="atlas-form-section"><legend>Métodos de pago</legend>
    {parts.map((part, index) => <div className="finance-payment-row" key={index}>
      <FormField label={`Método ${index + 1}`}><Select value={part.method} onChange={e => onChange(parts.map((p, i) => i === index ? { method: e.target.value as Method, amount: p.amount, ...(e.target.value === 'card' ? { batch_number: '', provider: providers[0] } : {}) } : p))}>
        {Object.entries(methods).map(([key, label]) => <option key={key} value={key} disabled={(key === 'card' && !providers.length) || parts.some((p, i) => i !== index && p.method === key)}>{label}</option>)}
      </Select></FormField>
      <FormField label={`Importe ${index + 1}`} required><Input type="number" min="0.01" step="0.01" max="9999999999.99" value={part.amount} onChange={e => onChange(parts.map((p, i) => i === index ? { ...p, amount: e.target.value } : p))} /></FormField>
      {part.method === 'card' && <FormField label={`Prestadora de tarjeta ${index + 1}`} required><Select value={part.provider || ''} onChange={e => onChange(parts.map((p, i) => i === index ? { ...p, provider: e.target.value as CardProvider } : p))}><option value="">Seleccione</option>{providers.map(provider => <option key={provider} value={provider}>{provider}</option>)}</Select></FormField>}
      {part.method === 'card' && <FormField label={`Número de lote del voucher ${index + 1}`} required><Input maxLength={40} value={part.batch_number || ''} onChange={e => onChange(parts.map((p, i) => i === index ? { ...p, batch_number: e.target.value } : p))} /></FormField>}
      <Button variant="ghost" onClick={() => onChange(parts.filter((_, i) => i !== index))}>Quitar método {index + 1}</Button>
    </div>)}
    <Button variant="outline" disabled={!addable.length} onClick={() => onChange([...parts, { method: addable[0], amount: '', ...(addable[0] === 'card' ? { provider: providers[0], batch_number: '' } : {}) }])}>Añadir método</Button>
    <p>Monto recibido: <strong>{money(Number.isFinite(sumParts(parts)) ? sumParts(parts) / 100 : 0)}</strong></p>
    {parts.some(part => part.method === 'card') && <p className="atlas-help">Registre el lote del voucher del terminal. No introduzca el número de tarjeta.</p>}
    {!providers.length && <p className="atlas-help">Tarjeta no disponible: un administrador debe habilitar la prestadora de este centro.</p>}
    {!parts.length && <p>Sin pago ahora: se registrará el saldo pendiente del paciente.</p>}
  </fieldset>;
}
