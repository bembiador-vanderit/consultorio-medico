import { useEffect, useRef, useState, type FormEvent } from "react";
import { Alert, Button, FormField, Input, Modal, Select, Textarea } from "../../ui";
import { api } from "../../services/api";
import type { User } from "../../types/user";
import { safetySeverities, safetySources, safetyStatuses, safetyTypes, type PatientSafetyEntry } from "../../types/patientSafety";
import "./patientSafety.css";

type Props = { patientId:number; patientName:string; user:User; fullVisible?:boolean; criticalAlertsVisible?:boolean };
type Draft = { entry_type:string; substance_or_agent:string; reaction_description:string; severity:string; status:string; onset_date:string; notes:string; source_type:string; source_description:string; change_reason:string };
type Audit = { id:number; actor_id:number; at:string; action:string; context:{before:unknown; after:unknown; reason:string|null} };
const blank = (): Draft => ({ entry_type:"", substance_or_agent:"", reaction_description:"", severity:"unknown", status:"active", onset_date:"", notes:"", source_type:"", source_description:"", change_reason:"" });
const fromEntry = (e:PatientSafetyEntry):Draft => ({ entry_type:e.entry_type, substance_or_agent:e.substance_or_agent, reaction_description:e.reaction_description, severity:e.severity, status:e.status, onset_date:e.onset_date||"", notes:e.notes||"", source_type:e.source_type, source_description:e.source_description||"", change_reason:"" });
const at = (date:string) => new Date(date).toLocaleString("es-DO");

export default function PatientSafetyProfile({ patientId, patientName, user, fullVisible=true, criticalAlertsVisible=true }:Props) {
  const allowed = !!user.permissions?.includes("patient_safety:view") && !!user.permissions?.includes("patients:view") && !!user.permissions?.includes("clinical:access") && user.roles.includes("doctor");
  const [enabled,setEnabled]=useState(false), [canEdit,setCanEdit]=useState(false);
  const [entries,setEntries]=useState<PatientSafetyEntry[]>([]), [loading,setLoading]=useState(true), [error,setError]=useState("");
  const [open,setOpen]=useState(false), [editing,setEditing]=useState<PatientSafetyEntry|null|undefined>(undefined);
  const [draft,setDraft]=useState<Draft>(blank), [notice,setNotice]=useState(""), [saving,setSaving]=useState(false);
  const [discard,setDiscard]=useState<"close"|"cancel"|null>(null), [audit,setAudit]=useState<{entryId:number; rows:Audit[]}|null>(null);
  const submitting=useRef(false), initial=useRef("");
  const base=`/patient-safety/patients/${patientId}`;
  const dirty=editing!==undefined && JSON.stringify(draft)!==initial.current;
  useEffect(()=>{
    if(!allowed){setLoading(false);return;}
    let live=true;
    async function load(){
      try{
        const {data:cap}=await api.get<{enabled:boolean;can_edit:boolean}>("/patient-safety/capabilities");
        if(!live)return; setEnabled(cap.enabled);setCanEdit(cap.can_edit);
        if(cap.enabled){const {data}=await api.get<PatientSafetyEntry[]>(base);if(live)setEntries(data);}
      }catch{if(live){setEnabled(true);setError("No fue posible consultar la seguridad clínica. No asuma ausencia de alergias.");}}
      finally{if(live)setLoading(false);}
    }
    void load();return()=>{live=false;};
  },[patientId,allowed]);
  useEffect(()=>{
    if(!dirty)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);
  },[dirty]);
  if(!allowed || (!enabled && !loading))return null;
  const active=entries.filter(e=>e.status==="active");
  const alerts=active.filter(e=>e.entry_type==="allergy" && ["severe","critical"].includes(e.severity));
  // Compact presentation never exposes agent, reaction, notes or an edit action.
  // It still loads only through the original authorized Safety endpoint.
  if(!fullVisible)return criticalAlertsVisible&&alerts.length>0?<section className="patient-safety" aria-label="Alerta crítica de seguridad"><Alert tone="danger" title="Alergia crítica registrada">Revise la información de seguridad por las vías autorizadas antes de la atención.</Alert></section>:null;
  function edit(entry:PatientSafetyEntry|null){
    if(!canEdit)return;
    const next=entry?fromEntry(entry):blank();initial.current=JSON.stringify(next);setDraft(next);setEditing(entry);setNotice("");setError("");setAudit(null);
  }
  function leave(action:"close"|"cancel"){
    if(submitting.current)return;
    if(dirty){setDiscard(action);return;}
    setEditing(undefined);setError("");if(action==="close")setOpen(false);
  }
  async function save(event:FormEvent){
    event.preventDefault();if(submitting.current||!canEdit||editing===undefined)return;
    if(!dirty){setEditing(undefined);return;}
    submitting.current=true;setSaving(true);setError("");
    try{
      const payload={...draft, onset_date:draft.onset_date||null, notes:draft.notes.trim()||null, source_description:draft.source_description.trim()||null, change_reason:draft.change_reason.trim()||undefined};
      if(editing) Object.assign(payload,{revision:editing.revision});
      const {data}=editing?await api.put<PatientSafetyEntry>(`${base}/entries/${editing.id}`,payload):await api.post<PatientSafetyEntry>(base,payload);
      setEntries(current=>[data,...current.filter(e=>e.id!==data.id)]);setEditing(undefined);setNotice("Registro de seguridad guardado.");
    }catch(err:any){const detail=err?.response?.data?.detail;setError(typeof detail==="string"?detail:"Revise los datos. No fue posible guardar el registro de seguridad.");}
    finally{submitting.current=false;setSaving(false);}
  }
  async function history(entryId:number){
    try{const {data}=await api.get<Audit[]>(`${base}/entries/${entryId}/history`);setAudit({entryId,rows:data});}
    catch{setError("No fue posible consultar el historial de seguridad.");}
  }
  const field=(key:keyof Draft,value:string)=>setDraft(current=>({...current,[key]:value}));
  const options=(items:Record<string,string>)=>Object.entries(items).map(([key,label])=><option key={key} value={key}>{label}</option>);
  return <section className="patient-safety" aria-label="Seguridad clínica">
    <h4>Seguridad clínica</h4>
    {loading?<p role="status">Consultando seguridad clínica...</p>:<>
      {criticalAlertsVisible&&alerts.slice(0,2).map(e=><Alert key={e.id} className="patient-safety-alert" tone="danger" title="ALERGIA ACTIVA REGISTRADA"><strong>{e.substance_or_agent}</strong><p>Reacción: {e.reaction_description}</p><p>{safetySeverities[e.severity]} · {safetySources[e.source_type]}</p></Alert>)}
      {criticalAlertsVisible&&alerts.length>2&&<p>Hay {alerts.length-2} alertas graves adicionales. Consulte el detalle completo.</p>}
      {!error&&(!active.length?<p>No hay registros activos documentados. Esto no equivale a ausencia de alergias.</p>:<ul>{active.filter(e=>!criticalAlertsVisible||!alerts.includes(e)).slice(0,criticalAlertsVisible&&alerts.length?1:3).map(e=><li key={e.id}><strong>{safetyTypes[e.entry_type]}: {e.substance_or_agent}</strong><span>{safetySeverities[e.severity]} · {safetySources[e.source_type]}</span></li>)}</ul>)}
      {error && !open && <Alert tone="warning" title="Información de seguridad no disponible">{error}</Alert>}
      <Button variant="outline" onClick={()=>setOpen(true)}>Ver seguridad clínica</Button>
    </>}
    {open && <Modal open title="Seguridad clínica del paciente" description={patientName} onClose={()=>leave("close")} closeDisabled={saving} footer={<div className="patient-safety-actions">{editing===undefined?<><Button variant="outline" onClick={()=>leave("close")}>Cerrar</Button>{canEdit&&<Button onClick={(event)=>{event.preventDefault();edit(null);}}>Agregar</Button>}</>:<><Button variant="outline" disabled={saving} onClick={()=>leave("cancel")}>Cancelar</Button><Button type="submit" form="patient-safety-form" loading={saving}>Guardar</Button></>}</div>}>
      {error&&<Alert tone="danger" title="Revise el registro">{error}</Alert>}{notice&&<p role="status">{notice}</p>}
      {editing===undefined?<><p>Los datos referidos no equivalen a confirmación médica. Este perfil es longitudinal.</p>{!error&&!entries.length&&<p>Sin registros de seguridad clínica documentados.</p>}
        <ul className="patient-safety-list">{entries.map(e=><li key={e.id}><article><h3>{safetyTypes[e.entry_type]} · {e.substance_or_agent}</h3><dl><div><dt>Reacción</dt><dd>{e.reaction_description}</dd></div><div><dt>Severidad</dt><dd>{safetySeverities[e.severity]}</dd></div><div><dt>Estado</dt><dd>{safetyStatuses[e.status]}</dd></div><div><dt>Procedencia</dt><dd>{safetySources[e.source_type]}{e.source_description&&` · ${e.source_description}`}</dd></div><div><dt>Registrado por</dt><dd>{e.recorded_by_name} · {at(e.recorded_at)}</dd></div><div><dt>Actualizado por</dt><dd>{e.updated_by_name} · {at(e.updated_at)}</dd></div>{e.onset_date&&<div><dt>Inicio referido</dt><dd>{e.onset_date}</dd></div>}{e.notes&&<div><dt>Observaciones</dt><dd>{e.notes}</dd></div>}</dl><div className="patient-safety-actions">{canEdit&&e.status!=="entered_in_error"&&<Button variant="outline" onClick={()=>edit(e)}>Editar {e.substance_or_agent}</Button>}<Button variant="outline" onClick={()=>void history(e.id)}>Ver trazabilidad de {e.substance_or_agent}</Button></div></article></li>)}</ul>
        {audit&&<section aria-label="Historial de seguridad"><h3>Trazabilidad</h3>{audit.rows.map(row=><details key={row.id}><summary>{at(row.at)} · Usuario #{row.actor_id} · {row.action}</summary><p>Motivo: {row.context.reason||"No indicado"}</p><pre>{JSON.stringify({anterior:row.context.before,nuevo:row.context.after},null,2)}</pre></details>)}</section>}
      </>:<form id="patient-safety-form" onSubmit={save}><p>{editing?"Editando registro de seguridad":"Nuevo registro de seguridad"} · * Campos obligatorios</p><fieldset disabled={saving} className="patient-safety-grid">
        <FormField label="Tipo" required><Select value={draft.entry_type} onChange={e=>field("entry_type",e.target.value)}><option value="">Seleccione tipo</option>{options(safetyTypes)}</Select></FormField>
        <FormField label="Sustancia / Agente" required><Input maxLength={200} value={draft.substance_or_agent} onChange={e=>field("substance_or_agent",e.target.value)}/></FormField>
        <FormField label="Reacción / Descripción clínica" required><Textarea maxLength={3000} value={draft.reaction_description} onChange={e=>field("reaction_description",e.target.value)}/></FormField>
        <FormField label="Severidad" required><Select value={draft.severity} onChange={e=>field("severity",e.target.value)}>{options(safetySeverities)}</Select></FormField>
        <FormField label="Procedencia" required><Select value={draft.source_type} onChange={e=>field("source_type",e.target.value)}><option value="">Seleccione procedencia</option>{options(safetySources)}</Select></FormField>
        <FormField label="Detalle de procedencia"><Input maxLength={1000} value={draft.source_description} onChange={e=>field("source_description",e.target.value)}/></FormField>
        <FormField label="Estado" required><Select value={draft.status} onChange={e=>field("status",e.target.value)}>{options(safetyStatuses)}</Select></FormField>
        <FormField label="Fecha de inicio"><Input type="date" value={draft.onset_date} onChange={e=>field("onset_date",e.target.value)}/></FormField>
        <FormField label="Observaciones"><Textarea maxLength={3000} value={draft.notes} onChange={e=>field("notes",e.target.value)}/></FormField>
        <FormField label="Motivo del cambio" required={editing?draft.status!==editing.status:draft.status!=="active"}><Textarea maxLength={1000} value={draft.change_reason} onChange={e=>field("change_reason",e.target.value)}/></FormField>
      </fieldset></form>}
    </Modal>}
    {discard&&<Modal open title="Cambios sin guardar" onClose={()=>setDiscard(null)} footer={<div className="patient-safety-actions"><Button variant="outline" onClick={()=>setDiscard(null)}>Seguir editando</Button><Button onClick={()=>{setEditing(undefined);setDiscard(null);setError("");if(discard==="close")setOpen(false);}}>Descartar cambios</Button></div>}><p>Hay cambios sin guardar. ¿Deseas descartarlos?</p></Modal>}
  </section>;
}
