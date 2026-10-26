/** Synthetic DEV fixture. All requests intercepted; NEVER official clinical data. */
import React,{useState} from "react";
import {createRoot} from "react-dom/client";
import {api} from "../../src/services/api";
import CardiologyModule from "../../src/components/consultation/CardiologyModule";
import FollowUpInbox from "../../src/components/FollowUpInbox";
import VitalSignsModule from "../../src/components/consultation/VitalSignsModule";
import "../../src/index.css";
if(!import.meta.env.DEV)throw new Error("Development-only QA fixture");
let assessment={revision:1,symptoms:{chest_pain:{present:true,detail:"Texto exclusivamente sintético QA"}},cardiovascular_history:{hypertension:{present:false,detail:""}},examination:{rhythm:"QA ritmo"},impression:"QA impresión",plan:"QA plan",studies:[{category:"holter",status:"pending",note:"QA sin equipo conectado"}],follow_up:{kind:"days",value:10,reason:"Retorno QA",condition:"Holter y laboratorio QA"}};
let contacts:any[]=[];
const qaDoctor={id:9002,email:"cardiology-qa@example.com",full_name:"Médico sintético QA",is_active:true,roles:["doctor"],permissions:["patients:view","clinical:access","patient_safety:view"]};
const qaSafety={id:1,patient_id:9001,organization_id:1,entry_type:"allergy",substance_or_agent:"Agente exclusivamente sintético QA",reaction_description:"Descripción sintética; no corresponde a una persona real",severity:"critical",status:"active",source_type:"patient_reported",recorded_by_name:"Médico QA",updated_by_name:"Médico QA",recorded_at:"2030-01-01T12:00:00Z",updated_at:"2030-01-01T12:00:00Z"};
api.defaults.adapter=async config=>{
 let data:any;
 if(config.url?.endsWith("/cardiology")){if(config.method==="put"){const {expected_revision,...v}=JSON.parse(config.data);assessment={...v,revision:expected_revision+1};}data=assessment;}
 else if(config.url==="/follow-ups/inbox")data={enabled:true,items:[{id:1,patient_id:9001,patient_name:"Paciente sintético QA — nombre largo para verificar ajuste",doctor_id:9002,doctor_name:"Médico sintético QA",center_id:1,specialty_id:1,due_at:"2030-01-11T00:00:00",reason:"Retorno QA",condition:"Holter y laboratorios QA",status:"pending",appointment_id:null}]};
 else if(config.url?.endsWith("/contacts")){if(config.method==="post")contacts.push({id:contacts.length+1,...JSON.parse(config.data),actor_id:9003,created_at:"2030-01-01T12:00:00"});data=contacts;}
 else if(config.url==="/patient-safety/capabilities")data={enabled:true,can_edit:false};
 else if(config.url==="/patient-safety/patients/9001")data=[qaSafety];
 else if(config.url?.endsWith("/vital-signs")&&config.method==="put")data={id:1,...JSON.parse(config.data)};
 else throw new Error("Non-QA request blocked");
 return{data,status:200,statusText:"QA isolated",headers:{},config};
};
function Preview(){const [saved,setSaved]=useState<any>({id:1,consultation_date:"2030-01-01",reason_for_visit:"Motivo clínico QA",current_illness:"Historia sintética QA"}),[dirty,setDirty]=useState(false),[readonly,setReadonly]=useState(false),[vitals,setVitals]=useState<any>({id:1,systolic_pressure:120,diastolic_pressure:80,heart_rate:72,respiratory_rate:16,oxygen_saturation:98,weight_kg:80,height_cm:180,bmi:24.69});
 const item:any={appointment:{id:9000,patient_id:9001,patient_name:"Paciente sintético QA — nombre largo para verificar ajuste",patient_date_of_birth:"1990-01-01",doctor_name:"Médico sintético QA",center_name:"Centro sintético QA"},context:{appointment_reason:"Motivo administrativo QA",patient_registered_sex:"female"},saved,completed:readonly,saving:false,bootstrapVersion:0,currentUser:qaDoctor,onAnamnesisDirty:setDirty,saveHistory:setSaved};
 return <main style={{maxWidth:1200,margin:"auto",padding:"1rem"}}><h1>QA aislado · Cardiología</h1><p>No conectado a la base oficial. Seguridad, signos, diagnósticos, recetas y documentos se reutilizan en la consulta real.</p><button onClick={()=>setReadonly(!readonly)}>{readonly?"Ver borrador QA":"Ver completada QA"}</button><p role="status">{dirty?"Cambios QA sin guardar":"QA guardado"}</p><CardiologyModule item={item}/><section className="my-4"><h2>Signos vitales — componente existente</h2><VitalSignsModule episodeId={9000} historyId={1} vitalSigns={vitals} completed={readonly} loading={false} onSaved={setVitals}/></section><FollowUpInbox user={{id:9003,roles:["secretary"]} as any} onSchedule={()=>window.alert("QA: callback al flujo existente de Agenda")}/></main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
