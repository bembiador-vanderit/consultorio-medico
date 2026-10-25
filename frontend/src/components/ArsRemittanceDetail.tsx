import { useId } from 'react';
import { money } from '../services/finance';
import { Button, Card, FormField, Input, StatusBadge } from '../ui';

export type RemittanceApplication = {
  id: number;
  claim_id: number;
  amount: string;
  reversed_at: string | null;
  reversal_reason: string | null;
};

export type Remittance = {
  id: number;
  center_id: number | null;
  insurance_company_id: number;
  company_name: string;
  received_on: string;
  reference: string;
  amount: string;
  applied_amount: string;
  unapplied: string;
  applications?: RemittanceApplication[];
};

type AllocationClaim = {
  id: number;
  patient_name: string;
  insurance_company_id: number;
  balance: string;
  state: string;
};

type Props = {
  remittance: Remittance;
  claims: AllocationClaim[];
  allocation: Record<number, string>;
  canPayment: boolean;
  busy: boolean;
  pendingApply: boolean;
  onAllocationChange: (claimId: number, value: string) => void;
  onApply: () => void;
  onReverse: (applicationId: number) => void;
  onClose: () => void;
};

/** Presentation only: financial requests and immutable retry intent stay in ArsFinance. */
export default function ArsRemittanceDetail({
  remittance, claims, allocation, canPayment, busy, pendingApply,
  onAllocationChange, onApply, onReverse, onClose,
}: Props) {
  const titleId = useId();
  const applicationsId = useId();
  const distributionId = useId();
  const applications = remittance.applications || [];
  const candidates = claims.filter(c => c.insurance_company_id === remittance.insurance_company_id
    && Number(c.balance) > 0 && ['sent', 'received', 'resent', 'glosed', 'rejected'].includes(c.state));
  const showDistribution = canPayment && (pendingApply || Number(remittance.unapplied) > 0);
  const distributed = Object.values(allocation).reduce((sum, value) => sum + (Number(value) || 0), 0);

  return <Card className="ars-remittance-detail">
    <section aria-labelledby={titleId}>
      <header className="ars-remittance-detail-header">
        <div>
          <p className="ars-remittance-eyebrow">Detalle de remesa</p>
          <h2 id={titleId}>{remittance.reference}</h2>
          <p className="ars-remittance-meta">{remittance.company_name} <span aria-hidden="true">·</span> Recibida el {remittance.received_on}</p>
        </div>
        <Button variant="outline" disabled={pendingApply} aria-label="Cerrar detalle de remesa" onClick={onClose}>Cerrar</Button>
      </header>

      <dl className="ars-remittance-totals">
        <div><dt>Total recibido</dt><dd>{money(remittance.amount)}</dd></div>
        <div><dt>Aplicado neto</dt><dd>{money(remittance.applied_amount)}</dd></div>
        <div className="ars-remittance-available"><dt>Disponible para aplicar</dt><dd>{money(remittance.unapplied)}</dd></div>
      </dl>

      <div className={`ars-remittance-detail-grid${showDistribution ? '' : ' ars-remittance-detail-grid--read-only'}`}>
        <section className="ars-remittance-history" aria-labelledby={applicationsId}>
          <div className="ars-remittance-section-heading">
            <h3 id={applicationsId}>Aplicaciones <span className="ars-remittance-count">{applications.length}</span></h3>
            <p>Los reversos se conservan en el historial.</p>
          </div>
          {applications.length ? <div className="ars-applications-scroll" tabIndex={0} role="region" aria-label="Historial de aplicaciones">
            <table className="ars-applications-table">
              <thead><tr><th scope="col">Reclamación</th><th scope="col">Importe</th><th scope="col">Estado</th><th scope="col"><span className="ars-remittance-sr-only">Acción</span></th></tr></thead>
              <tbody>{applications.map(a => {
                const patient = claims.find(c => c.id === a.claim_id)?.patient_name;
                return <tr key={a.id} className={a.reversed_at ? 'ars-application-reversed' : undefined}>
                  <td><strong>Reclamación #{a.claim_id}</strong><span className="ars-application-secondary">{patient && `${patient} · `}Aplicación #{a.id}</span></td>
                  <td className="ars-remittance-money">{money(a.amount)}</td>
                  <td><StatusBadge tone={a.reversed_at ? 'neutral' : 'success'}>{a.reversed_at ? 'Revertida' : 'Aplicada'}</StatusBadge></td>
                  <td className="ars-application-action">{!a.reversed_at && canPayment && <Button variant="outline" size="sm" className="ars-remittance-reverse" aria-label={`Revertir aplicación #${a.id}`} onClick={() => onReverse(a.id)}>Revertir</Button>}</td>
                </tr>;
              })}</tbody>
            </table>
          </div> : <p className="ars-remittance-empty">Esta remesa todavía no tiene aplicaciones.</p>}
        </section>

        {showDistribution && <section className="ars-remittance-distribution" aria-labelledby={distributionId}>
          <div className="ars-remittance-section-heading">
            <h3 id={distributionId}>Distribuir entre reclamaciones</h3>
            <p>Indique cuánto aplicar a cada saldo pendiente.</p>
          </div>
          {candidates.length ? <div className="ars-allocation-list">{candidates.map(c => <div className="ars-allocation-row" key={c.id}>
            <div className="ars-allocation-patient"><strong>{c.patient_name}</strong><span>Reclamación #{c.id}</span><span>Saldo: <b>{money(c.balance)}</b></span></div>
            <FormField className="ars-allocation-field" label={`#${c.id} · ${c.patient_name} · saldo ${money(c.balance)}`}>
              <span className="ars-allocation-currency" aria-hidden="true">Importe DOP</span>
              <Input disabled={pendingApply} type="number" inputMode="decimal" min="0" max={c.balance} step="0.01" placeholder="0.00" value={allocation[c.id] || ''} onChange={e => onAllocationChange(c.id, e.target.value)} />
            </FormField>
          </div>)}</div> : <p className="ars-remittance-empty">No hay reclamaciones compatibles con saldo pendiente.</p>}
          <div className="ars-distribution-footer">
            <p className="ars-distribution-total"><span>Distribuido</span><strong>{money(String(distributed))}</strong></p>
            {pendingApply && <p className="ars-remittance-pending" role="status">La operación conserva los mismos importes para un reintento seguro.</p>}
            <Button disabled={busy || (!pendingApply && Object.values(allocation).every(v => !Number(v)))} onClick={onApply}>{pendingApply ? 'Reintentar aplicación' : 'Aplicar importes'}</Button>
            <p className="ars-remittance-footnote">Solo se aplicarán los importes indicados.</p>
          </div>
        </section>}
      </div>
    </section>
  </Card>;
}
