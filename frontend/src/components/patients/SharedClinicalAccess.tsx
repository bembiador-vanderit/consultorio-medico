import { useEffect, useRef, useState } from "react";
import { api } from "../../services/api";
import { Alert, Button, Modal } from "../../ui";
import type { User } from "../../types/user";
import { sharedResources, type SharedResource, type SharedProjection } from "../../types/clinicalSharing";
import { safetySeverities, safetySources, safetyStatuses, safetyTypes } from "../../types/patientSafety";
import "./sharedClinicalAccess.css";
import {useFeatureVisibility} from "../../services/featureVisibility";

function SharedSafetyCriticalAlert({patientId}:{patientId:number}) {
  const [critical,setCritical]=useState(false);
  useEffect(()=>{let live=true;setCritical(false);
    // Still uses the unchanged 0060 authorized read gateway (including its audit).
    async function load(){
      let offset=0;
      do {
        const {data}=await api.get<SharedProjection>(`/clinical-sharing/patients/${patientId}/records/patient_safety`,{params:{offset,limit:50}});
        if(!live)return;
        const found=data.items.some(row=>{
          const field=(label:string)=>row.fields.find(f=>f.label===label)?.value;
          return field("Estado")==="active"&&field("Tipo")==="allergy"&&["critical","severe"].includes(String(field("Severidad")));
        });
        if(found){setCritical(true);return;}
        offset+=data.items.length;
        if(!data.items.length||offset>=data.total)return;
      } while(live);
    }
    void load().catch(()=>{if(live)setCritical(false);});
    return()=>{live=false;};
  },[patientId]);
  return critical?<Alert tone="danger" title="Alergia crítica registrada">Alerta compartida de solo lectura. Consulte por las vías autorizadas.</Alert>:null;
}

function valueText(value:unknown):string {
  if(value===null||value===undefined||value==="")return "—";
  if(typeof value==="boolean")return value?"Sí":"No";
  return typeof value==="object"?JSON.stringify(value):String(value);
}
const statusLabels:Record<string,string>={signed:"Firmada",completed:"Completada",active:"Activo",inactive:"Inactivo",entered_in_error:"Registrado por error"};
function fieldText(resource:SharedResource,label:string,value:unknown){
  if(resource==="patient_safety"&&typeof value==="string"){
    const labels:Record<string,Record<string,string>>={Tipo:safetyTypes,Severidad:safetySeverities,Estado:safetyStatuses,Procedencia:safetySources};
    return labels[label]?.[value]||valueText(value);
  }
  return valueText(value);
}
export default function SharedClinicalAccess({patientId,patientName,user}:{patientId:number;patientName:string;user:User}) {
  const allowed=user.roles.includes("doctor")&&["patients:view","clinical:access"].every(p=>user.permissions?.includes(p));
  const visibility=useFeatureVisibility(user,undefined,"ambulatory",allowed);
  const [resources,setResources]=useState<SharedResource[]>([]), [open,setOpen]=useState<SharedResource|null>(null);
  const [data,setData]=useState<SharedProjection|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const request=useRef(0);
  useEffect(()=>{
    const id=++request.current;setResources([]);setData(null);setOpen(null);setError("");
    if(allowed)void api.get<{enabled:boolean;resources:SharedResource[]}>(`/clinical-sharing/patients/${patientId}/capabilities`).then(({data})=>{
      if(id===request.current&&data?.enabled)setResources(data.resources.filter(r=>r in sharedResources));
    }).catch(()=>{/* No inferred grants or content on unavailable capabilities. */});
    return()=>{request.current++;};
  },[patientId,allowed]);
  async function load(resource:SharedResource,offset=0){
    if(busy)return;const id=++request.current;setOpen(resource);setData(null);setBusy(true);setError("");
    try{const {data}=await api.get<SharedProjection>(`/clinical-sharing/patients/${patientId}/records/${resource}`,{params:{offset,limit:25}});if(id===request.current)setData(data);}
    catch{if(id===request.current)setError("No fue posible consultar este recurso. La autorización puede haber cambiado.");}
    finally{if(id===request.current)setBusy(false);}
  }
  function close(){request.current++;setOpen(null);setData(null);setBusy(false);setError("");}
  const displayResources=resources.filter(r=>r!=="patient_safety"||visibility.clinical_safety_full);
  const compact=visibility.clinical_safety_critical_alert&&!visibility.clinical_safety_full&&resources.includes("patient_safety")&&user.permissions?.includes("patient_safety:view");
  if(!allowed||(!displayResources.length&&!compact))return null;
  return <>{compact&&<SharedSafetyCriticalAlert key={patientId} patientId={patientId}/>}{displayResources.length>0&&<section className="shared-clinical-access" aria-label="Acceso clínico compartido">
    <h4>Historial compartido en modo solo lectura</h4>
    <p>Consulta según la política clínica de la organización. No permite modificar contenido ajeno.</p>
    <div className="shared-clinical-actions">{displayResources.map(resource=><Button key={resource} variant="outline" disabled={busy} onClick={()=>void load(resource)}>Ver {sharedResources[resource].toLocaleLowerCase("es")}</Button>)}</div>
    {open&&displayResources.includes(open)&&<Modal open title={`${sharedResources[open]} · Solo lectura`} description={patientName} onClose={close} footer={<Button variant="outline" onClick={close}>Cerrar</Button>}>
      <div className="shared-clinical-records"><p>Historial compartido en modo solo lectura. La consulta queda auditada.</p>
        {busy&&<p role="status">Consultando…</p>}
        {error&&<Alert tone="warning" title="Consulta no disponible">{error}</Alert>}
        {data&&!data.items.length&&<p>No hay registros finalizados disponibles para esta consulta.</p>}
        {data?.items.map((row,i)=><article key={`${row.kind||open}-${row.id}-${i}`}><h3>{row.title}</h3><p>{row.date?.slice(0,10)} · {row.doctor_name||"Profesional no registrado"} · {statusLabels[row.status]||row.status}</p><dl>{row.fields.map((field,i)=><div key={i}><dt>{field.label}</dt><dd>{fieldText(open,field.label,field.value)}</dd></div>)}</dl></article>)}
        {data&&data.total>data.limit&&<nav aria-label="Páginas del historial compartido"><Button variant="outline" disabled={busy||data.offset===0} onClick={()=>void load(open,Math.max(0,data.offset-data.limit))}>Anterior</Button><Button variant="outline" disabled={busy||data.offset+data.limit>=data.total} onClick={()=>void load(open,data.offset+data.limit)}>Siguiente</Button></nav>}
      </div>
    </Modal>}
  </section>}</>;
}
