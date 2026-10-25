/** Synthetic DEV visual fixture: no network, credentials or official DB. */
import React from "react";
import {createRoot} from "react-dom/client";
import {api} from "../../src/services/api";
import SharedClinicalAccess from "../../src/components/patients/SharedClinicalAccess";
import ClinicalSharingPolicySettings from "../../src/components/ClinicalSharingPolicySettings";
import "../../src/index.css";

if(!import.meta.env.DEV)throw new Error("QA preview is development only");
const user={id:9001,email:"qa-sharing@example.com",full_name:"Médico QA",is_active:true,roles:["doctor"],permissions:["patients:view","clinical:access"]};
const policy={enabled:true,revision:1,mode:"active_relationship",limit_to_same_center:true,clinical_history:true,clinical_documents:true,patient_safety:true};
api.defaults.adapter=async config=>{
 if(!config.url?.startsWith("/clinical-sharing/"))throw new Error("Non-QA request blocked");
 const data=config.url.endsWith("/policy")?policy:config.url.endsWith("/capabilities")?{enabled:true,resources:["clinical_history","clinical_documents","patient_safety"]}:
 {read_only:true,resource:config.url.split("/").at(-1),items:[{id:1,title:"Consulta sintética QA",date:"2030-01-01",doctor_name:"Médica sintética QA — nombre largo para verificar ajuste",status:"completed",read_only:true,fields:[{label:"Motivo de consulta",value:"Texto QA sintético; no representa atención clínica real."},{label:"Notas clínicas",value:"Contenido de prueba conservado en modo solo lectura. "+"Detalle QA para verificar ajuste. ".repeat(8)}]}],total:1,offset:0,limit:25};
 return{data,status:200,statusText:"QA only",headers:{},config};
};
createRoot(document.getElementById("root")!).render(<main style={{maxWidth:1100,margin:"0 auto",padding:"1rem"}}>
 <h1>QA sintético — Política clínica compartida</h1><p>Vista aislada, sin conexión a la base oficial.</p>
 <ClinicalSharingPolicySettings/>
 <SharedClinicalAccess patientId={9002} patientName="Paciente sintético QA" user={user}/>
</main>);
