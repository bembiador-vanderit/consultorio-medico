export const methods = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', check: 'Cheque', other: 'Otro' } as const;
export type Method = keyof typeof methods;
export type Part = { method: Method; amount: string };
export type Invoice = { id: number; number: string; center_id: number; patient_id: number; patient_name: string; concept: string; base_amount: string; ars_amount: string; expected_ars: string; patient_amount: string; paid_amount: string; balance: string; state: string; created_at: string; coverage_snapshot: Record<string, unknown>; movements?: Movement[] };
export type Movement = { id: number; register_id: number; invoice_id: number | null; kind: string; amount: string; parts: Part[]; reason: string | null; reverses_id: number | null; created_by: number; created_at: string };
export type Register = { id: number; opened_by: number; state: string; opening_amount: string; opened_at: string; closed_at: string | null; closed_by: number | null; counted_cash: string | null; difference: string | null; closing_notes: string | null; totals: { collected: Record<Method, string>; reversed: Record<Method, string>; adjustments_in: string; adjustments_out: string; expected_cash: string } };
export type Preview = { coverage: null | { revision: number; concept: string; base_amount: string; ars_amount: string; patient_amount: string; insurance: { company_name?: string }; authorization_status: string }; invoice: Invoice | null };
export const states: Record<string, string> = { pending: 'Pendiente', partial: 'Pago parcial', paid: 'Paciente saldado', void: 'Anulada' };
export const kinds: Record<string, string> = { payment: 'Cobro', reversal: 'Reverso / devolución', adjustment_in: 'Ajuste de entrada', adjustment_out: 'Ajuste de salida' };
export const money = (value: string | number) => new Intl.NumberFormat('es-DO', { style: 'currency', currency: 'DOP' }).format(Number(value));
export function cents(value: string) { return /^\d+(\.\d{1,2})?$/.test(value) ? Math.round(Number(value) * 100) : NaN; }
export const sumParts = (parts: Part[]) => parts.reduce((sum, p) => sum + cents(p.amount), 0);
export const financeError = (e: any): string => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : Array.isArray(e?.response?.data?.detail) ? e.response.data.detail.map((x: any) => x.msg).join('. ') : 'No se pudo confirmar la operación. Reintente con la misma confirmación para evitar duplicados.';
export const timestamp = (value: string) => new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('es-DO');
