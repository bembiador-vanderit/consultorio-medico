import { useEffect, useState } from "react";
import { Alert, Button, Modal } from "../../ui";
import { api } from "../../services/api";
import type { User } from "../../types/user";
import { careOrigins, careStatuses, careTypes, type PatientCareRelationship } from "../../types/patientCare";
import "./patientRelatedDoctors.css";

const dateLabel = (value:string|null) => value
  ? new Date(value).toLocaleDateString("es-DO") : "Sin atención registrada";

export default function PatientRelatedDoctors({ patientId, patientName, user }:{ patientId:number; patientName:string; user:User }) {
  const allowed = !!user.permissions?.includes("patients:view") && !!user.permissions?.includes("patient_care:view")
    && user.roles.some(role=>["doctor","admin"].includes(role));
  const [rows,setRows] = useState<PatientCareRelationship[]>([]);
  const [enabled,setEnabled] = useState(false), [loading,setLoading] = useState(true);
  const [error,setError] = useState(""), [open,setOpen] = useState(false);
  useEffect(()=>{
    if(!allowed){setLoading(false);return;}
    let live = true;
    async function load(){
      try {
        const {data:cap} = await api.get<{enabled:boolean}>("/patient-care/capabilities");
        if(!live)return;
        setEnabled(cap.enabled);
        if(cap.enabled){
          const {data} = await api.get<PatientCareRelationship[]>(`/patient-care/patients/${patientId}/relationships`);
          if(live)setRows(data);
        }
      } catch { if(live){setEnabled(true);setError("No fue posible consultar los médicos relacionados.");} }
      finally { if(live)setLoading(false); }
    }
    void load();
    return()=>{live=false;};
  },[patientId,allowed]);
  if(!allowed || (!enabled&&!loading))return null;
  const relevant = rows.filter(row=>["active","follow_up"].includes(row.status));
  const summary = (relevant.length?relevant:rows).slice(0,3);
  return <section className="patient-related-doctors" aria-label="Médicos relacionados">
    <h4>Médicos relacionados</h4>
    {loading?<p role="status">Consultando relaciones asistenciales...</p>:<>
      {error?<Alert tone="warning" title="Consulta no disponible">{error}</Alert>:<>
        {!rows.length?<p>No hay relaciones asistenciales registradas. No equivale a ausencia de atenciones previas.</p>:
          <ul>{summary.map(row=><li key={row.id}>
            <span>{row.specialty_name||"Especialidad no registrada"}</span>
            <strong>{row.doctor_name}</strong>
            <span>{careStatuses[row.status]} · Última atención: {dateLabel(row.last_seen_at)}</span>
          </li>)}</ul>}
        {rows.length>summary.length&&<p>Hay {rows.length-summary.length} {rows.length-summary.length===1?"relación adicional":"relaciones adicionales"} en el detalle.</p>}
        <Button variant="outline" onClick={()=>setOpen(true)}>Ver médicos relacionados</Button>
      </>}
    </>}
    {open&&<Modal open title="Médicos relacionados con el paciente" description={patientName}
      onClose={()=>setOpen(false)} footer={<Button variant="outline" onClick={()=>setOpen(false)}>Cerrar</Button>}>
      <div className="patient-related-doctors-detail">
        <p>Relación longitudinal: no asigna responsabilidad del episodio actual ni concede acceso al historial clínico.</p>
        {!rows.length&&<p>Sin relaciones asistenciales registradas.</p>}
        <ul>{rows.map(row=><li key={row.id}><article>
          <h3>{row.doctor_name}</h3>
          <dl>
            <div><dt>Especialidad</dt><dd>{row.specialty_name||"No registrada"}</dd></div>
            <div><dt>Organización</dt><dd>{row.organization_name}</dd></div>
            <div><dt>Centro de referencia más reciente</dt><dd>{row.center_name||"Sin centro específico"}</dd></div>
            <div><dt>Tipo de relación</dt><dd>{careTypes[row.relationship_type]}</dd></div>
            <div><dt>Origen</dt><dd>{careOrigins[row.origin]}</dd></div>
            <div><dt>Estado</dt><dd>{careStatuses[row.status]}</dd></div>
            <div><dt>Inicio de la relación</dt><dd>{dateLabel(row.started_at)}</dd></div>
            <div><dt>Primera atención</dt><dd>{dateLabel(row.first_seen_at)}</dd></div>
            <div><dt>Última atención</dt><dd>{dateLabel(row.last_seen_at)}</dd></div>
            {row.ended_at&&<div><dt>Finalización de la relación</dt><dd>{dateLabel(row.ended_at)}</dd></div>}
          </dl>
        </article></li>)}</ul>
      </div>
    </Modal>}
  </section>;
}
