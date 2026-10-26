import { useEffect, useState, type FormEvent } from "react";
import { api } from "../services/api";
import { Alert, Button, FormField, Select, Textarea } from "../ui";
import { sharedResources, type SharingPolicy } from "../types/clinicalSharing";

export default function ClinicalSharingPolicySettings() {
  const [policy,setPolicy] = useState<SharingPolicy|null>(null);
  const [reason,setReason] = useState(""), [busy,setBusy] = useState(false), [error,setError] = useState(""), [saved,setSaved] = useState(false);
  useEffect(()=>{let live=true; void api.get<SharingPolicy>("/clinical-sharing/policy").then(({data})=>{if(live)setPolicy(data);}).catch(()=>{if(live)setError("No fue posible consultar la política clínica.");});return()=>{live=false;};},[]);
  async function save(event:FormEvent) {
    event.preventDefault();if(!policy||busy)return;setBusy(true);setError("");setSaved(false);
    try { const {enabled,...values}=policy;const {data}=await api.put<SharingPolicy>("/clinical-sharing/policy",{...values,reason});setPolicy(data);setReason("");setSaved(true); }
    catch {setError("No fue posible guardar. Si la política cambió, vuelva a cargar antes de reintentar.");}
    finally{setBusy(false);}
  }
  return <section className="rounded-xl border bg-white p-5" aria-label="Política clínica">
    <h3 className="font-bold">Acceso clínico entre médicos</h3>
    <p>La política permite consulta, no edición ni responsabilidad del episodio. Siempre exige permisos clínicos y pertenencia activa a esta organización.</p>
    {error&&<Alert tone="warning" title="Política clínica">{error}</Alert>}
    {policy&&!policy.enabled&&<p>Configuración pendiente de activación de la base. El acceso actual sigue sin cambios.</p>}
    {policy?.enabled&&<form onSubmit={save} className="space-y-3">
      <FormField label="Política base"><Select value={policy.mode} onChange={e=>setPolicy({...policy,mode:e.target.value as SharingPolicy["mode"]})}>
        <option value="assigned">Solo médicos asignados (acceso actual)</option>
        <option value="active_relationship">Médicos con relación asistencial activa</option>
        <option value="same_center">Médicos del mismo centro</option>
        <option value="organization">Médicos de la organización</option>
      </Select></FormField>
      <label className="block"><input type="checkbox" checked={policy.limit_to_same_center||policy.mode==="same_center"} disabled={policy.mode==="same_center"} onChange={e=>setPolicy({...policy,limit_to_same_center:e.target.checked})}/> Limitar lectura al mismo centro</label>
      <fieldset><legend>Recursos compartibles (solo lectura)</legend>{Object.entries(sharedResources).map(([key,label])=><label className="block" key={key}><input type="checkbox" checked={policy[key as keyof typeof sharedResources]} onChange={e=>setPolicy({...policy,[key]:e.target.checked})}/> {label}</label>)}</fieldset>
      <p>Sin recursos marcados no se comparte contenido. Las relaciones históricas o finalizadas no habilitan la política de relación activa. No se comparte entre organizaciones.</p>
      <FormField label="Motivo del cambio" required><Textarea value={reason} required minLength={5} maxLength={500} onChange={e=>setReason(e.target.value)}/></FormField>
      <Button type="submit" disabled={busy||reason.trim().length<5}>{busy?"Guardando…":"Guardar política clínica"}</Button>
      {saved&&<p role="status">Política guardada y auditada.</p>}
    </form>}
  </section>;
}
