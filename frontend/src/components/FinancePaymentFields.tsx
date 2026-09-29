import { Button, FormField, Input, Select } from '../ui';
import { methods, money, sumParts, type Method, type Part } from '../services/finance';

export default function FinancePaymentFields({ parts, onChange }: { parts: Part[]; onChange: (parts: Part[]) => void }) {
  return <fieldset className="atlas-form-section"><legend>Métodos de pago</legend>
    {parts.map((part, index) => <div className="finance-payment-row" key={index}>
      <FormField label={`Método ${index + 1}`}><Select value={part.method} onChange={e => onChange(parts.map((p, i) => i === index ? { ...p, method: e.target.value as Method } : p))}>
        {Object.entries(methods).map(([key, label]) => <option key={key} value={key} disabled={parts.some((p, i) => i !== index && p.method === key)}>{label}</option>)}
      </Select></FormField>
      <FormField label={`Importe ${index + 1}`} required><Input type="number" min="0.01" step="0.01" max="9999999999.99" value={part.amount} onChange={e => onChange(parts.map((p, i) => i === index ? { ...p, amount: e.target.value } : p))} /></FormField>
      <Button variant="ghost" onClick={() => onChange(parts.filter((_, i) => i !== index))}>Quitar método {index + 1}</Button>
    </div>)}
    <Button variant="outline" disabled={parts.length === 5} onClick={() => onChange([...parts, { method: (Object.keys(methods) as Method[]).find(m => !parts.some(p => p.method === m))!, amount: '' }])}>Añadir método</Button>
    <p>Monto recibido: <strong>{money(Number.isFinite(sumParts(parts)) ? sumParts(parts) / 100 : 0)}</strong></p>
    {!parts.length && <p>Sin pago ahora: se registrará el saldo pendiente del paciente.</p>}
  </fieldset>;
}
