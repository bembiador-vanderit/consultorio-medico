import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, EmptyState, FormField, Input, LoadingState, Modal, Select, StatusBadge } from "../../ui";
import "../../pages/patients.css";
import { api } from "../../services/api";
import type { InsuranceCompany, InsurancePlan, PatientInsurance } from "../../types/insurance";
import type { User } from "../../types/user";
import { insuranceError } from "../../services/insurance";

type Props = { patientId: number; patientName: string; user: User; onClose: () => void };
const empty = { insurance_company_id: "", plan_id: "", plan_name: "", member_number: "", policy_holder: "", relationship_to_holder: "", valid_from: "", valid_until: "", administrative_notes: "", is_primary: true, is_active: true };
export default function PatientInsurancePanel({ patientId, patientName, user, onClose }: Props) {
  const [items, setItems] = useState<PatientInsurance[]>([]);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [plans, setPlans] = useState<InsurancePlan[]>([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<number | null>(null);
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState("");
  const canWrite = !!user.permissions?.includes("insurance:manage") && !!user.permissions?.includes("patients:access");
  async function load() {
    const [i, c, p] = await Promise.all([api.get(`/insurance/patients/${patientId}`), api.get("/insurance/companies?include_inactive=true"), api.get("/insurance/plans?include_inactive=true")]);
    setItems(i.data); setCompanies(c.data); setPlans(p.data);
  }
  useEffect(() => { setLoading(true); setForm(empty); setEditing(null); load().catch(e => setError(insuranceError(e))).finally(() => setLoading(false)); }, [patientId]);
  async function save(e: FormEvent) {
    e.preventDefault(); setSaving(true); setError("");
    const payload = { ...form, insurance_company_id: Number(form.insurance_company_id), plan_id: form.plan_id ? Number(form.plan_id) : null,
      plan_name: form.plan_name || null, policy_holder: form.policy_holder || null, relationship_to_holder: form.relationship_to_holder || null,
      valid_from: form.valid_from || null, valid_until: form.valid_until || null, administrative_notes: form.administrative_notes || null };
    try {
      if (editing) await api.put(`/insurance/patients/${patientId}/${editing}`, payload);
      else await api.post(`/insurance/patients/${patientId}`, payload);
      setForm(empty); setEditing(null); await load();
    } catch (e) { setError(insuranceError(e)); } finally { setSaving(false); }
  }
  function edit(i: PatientInsurance) {
    setEditing(i.id); setForm({ insurance_company_id: String(i.insurance_company_id), plan_id: i.plan_id ? String(i.plan_id) : "", plan_name: i.plan_name || "",
      member_number: i.member_number, policy_holder: i.policy_holder || "", relationship_to_holder: i.relationship_to_holder || "", valid_from: i.valid_from || "",
      valid_until: i.valid_until || "", administrative_notes: i.administrative_notes || "", is_primary: i.is_primary, is_active: i.is_active });
  }
  async function deactivate(i: PatientInsurance) {
    setSaving(true); setError("");
    try { await api.delete(`/insurance/patients/${patientId}/${i.id}`); await load(); } catch (e) { setError(insuranceError(e)); } finally { setSaving(false); }
  }
  return <Modal title="Seguros" description={patientName} open onClose={() => { if (!saving) onClose(); }} closeLabel="Cerrar seguros">
    <div className="patient-form">
      {error && <Alert tone="danger" title="No se pudo guardar">{error}</Alert>}
      {loading ? <LoadingState label="Cargando seguros..." /> : <>
        <p className="atlas-help">Las coberturas ya registradas en citas conservan sus datos aunque cambie esta afiliación.</p>
        {!items.length && <EmptyState title="Sin seguros registrados" description="Puede registrar una afiliación cuando disponga de los datos." />}
        {items.map(i => <Card key={i.id} compact><h3>{i.insurance_company_name}</h3><StatusBadge tone={i.is_active ? "success" : "neutral"}>{i.is_active ? i.is_primary ? "Activo · Principal" : "Activo" : "Inactivo"}</StatusBadge>
          <p>{i.plan_name || "Sin plan"} · Afiliado / póliza: {i.member_number}</p>
          <p>Titular: {i.policy_holder || "No registrado"} · Relación: {i.relationship_to_holder || "No registrada"}</p>
          <p>Vigencia: {i.valid_from || "Sin fecha inicial"} — {i.valid_until || "Sin fecha final"}</p>
          {i.administrative_notes && <p>{i.administrative_notes}</p>}
          {canWrite && <><Button variant="outline" disabled={saving} onClick={() => edit(i)}>Editar seguro</Button>{i.is_active && <Button variant="outline" disabled={saving} onClick={() => void deactivate(i)}>Desactivar</Button>}</>}
        </Card>)}
        {canWrite && <form className="patient-form" onSubmit={save}>
          <h3>{editing ? "Editar afiliación" : "Registrar seguro"}</h3>
          <FormField label="Aseguradora / ARS" required><Select value={form.insurance_company_id} onChange={e => setForm({ ...form, insurance_company_id: e.target.value, plan_id: "", plan_name: "" })}><option value="">Seleccione</option>{companies.filter(c => c.is_active || String(c.id) === form.insurance_company_id).map(c => <option key={c.id} value={c.id}>{c.name}{!c.is_active && " (inactiva)"}</option>)}</Select></FormField>
          <FormField label="Plan"><Select value={form.plan_id} onChange={e => setForm({ ...form, plan_id: e.target.value, plan_name: "" })}><option value="">Sin plan de catálogo</option>{plans.filter(p => p.insurance_company_id === Number(form.insurance_company_id) && (p.is_active || String(p.id) === form.plan_id)).map(p => <option key={p.id} value={p.id}>{p.name}{!p.is_active && " (inactivo)"}</option>)}</Select></FormField>
          {form.plan_name && !form.plan_id && <p>Plan anterior: {form.plan_name}</p>}
          {([['member_number', 'Número de afiliado / póliza'], ['policy_holder', 'Titular'], ['relationship_to_holder', 'Relación con el titular'], ['valid_from', 'Vigente desde'], ['valid_until', 'Vigente hasta'], ['administrative_notes', 'Observaciones administrativas']] as const).map(([key, label]) => <FormField key={key} label={label} required={key === 'member_number'}><Input type={key.startsWith('valid_') ? 'date' : 'text'} maxLength={key === 'administrative_notes' ? 1000 : key === 'member_number' ? 100 : key === 'relationship_to_holder' ? 80 : 150} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></FormField>)}
          <Checkbox label="Seguro activo" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked, is_primary: e.target.checked && form.is_primary })} />
          <Checkbox label="Seguro principal" checked={form.is_primary} disabled={!form.is_active} onChange={e => setForm({ ...form, is_primary: e.target.checked })} />
          <Button type="submit" disabled={!form.insurance_company_id} loading={saving}>Guardar seguro</Button>
          {editing && <Button variant="outline" disabled={saving} onClick={() => { setEditing(null); setForm(empty); }}>Cancelar edición</Button>}
        </form>}
      </>}
    </div>
  </Modal>;
}
