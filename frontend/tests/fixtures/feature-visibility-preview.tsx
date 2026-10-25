/** DEV visual fixture. Every request is synthetic; no authentication or DB writes. */
import React,{useState} from "react";
import {createRoot} from "react-dom/client";
import {api} from "../../src/services/api";
import FeatureVisibilitySettings from "../../src/components/FeatureVisibilitySettings";
import CardiologyModule from "../../src/components/consultation/CardiologyModule";
import Patients from "../../src/pages/Patients";
import "../../src/index.css";

if(!import.meta.env.DEV)throw new Error("QA preview is development-only");
let audience="doctor";
let items=["clinical_safety_full","clinical_safety_critical_alert"].flatMap(feature_code=>["doctor","secretary"].map(audience=>({feature_code,context_code:"ambulatory",audience,visibility_mode:null as string|null,revision:0,visible:false,source:"system_default"})));
const patient={id:9001,first_name:"Paciente sintético",last_name:"QA Visibilidad",date_of_birth:"1990-01-01",phone:null,email:null};
const assessment={revision:1,symptoms:{},cardiovascular_history:{},examination:{},impression:"Impresión exclusivamente sintética QA",plan:"Plan sintético QA",studies:[],follow_up:{kind:"none"}};
const safety={id:9005,patient_id:9001,entry_type:"allergy",substance_or_agent:"Agente sintético QA",reaction_description:"Reacción sintética QA, no corresponde a ninguna persona real",severity:"critical",status:"active",source_type:"patient_reported",recorded_by_name:"Médico sintético QA",updated_by_name:"Médico sintético QA",recorded_at:"2030-01-01T12:00:00Z",updated_at:"2030-01-01T12:00:00Z"};
api.defaults.adapter=async config=>{
 let data:unknown;
 if(config.url==="/feature-visibility/settings"){
   if(config.method==="put")items=JSON.parse(config.data).changes.map((i:any)=>({...i,revision:i.revision+1,visible:i.visibility_mode==="visible",source:i.visibility_mode?"organization":"system_default"}));
   data={enabled:true,center_id:null,items,centers:[{id:1,name:"Centro sintético QA"}]};
 }else{
   if(config.method!=="get")throw Error("Non-QA mutation blocked");
   if(config.url==="/feature-visibility/resolved")data={features:Object.fromEntries(items.filter(i=>i.audience===audience).map(i=>[i.feature_code,i.visible]))};
   else if(config.url==="/patient-safety/capabilities")data={enabled:audience==="doctor",can_edit:false};
   else if(config.url==="/patient-safety/patients/9001")data=[safety];
   else if(config.url==="/patients")data=[patient];
   else if(config.url==="/patients/9001")data=patient;
   else if(config.url?.endsWith("/cardiology"))data=assessment;
   else if(config.url?.endsWith("/capabilities"))data={enabled:true,resources:[]};
   else if(config.url?.startsWith("/patient-care/"))data=[];
   else throw Error("Non-QA request blocked: "+config.url);
 }
 return{data,status:200,statusText:"QA isolated",headers:{},config};
};
function Preview(){
 const [view,setView]=useState("Administración"),[role,setRole]=useState("doctor");
 const user:any={id:9002,full_name:"Usuario sintético QA",email:"visibility-qa@example.com",is_active:true,roles:[role],permissions:role==="doctor"?["patients:view","clinical:access","patient_safety:view"]:["patients:view"]};
 const item:any={appointment:{id:9000,patient_id:9001,patient_name:"Paciente sintético QA Visibilidad",doctor_name:"Médico sintético QA",center_name:"Centro sintético QA",center_id:1},context:{appointment_reason:"QA aislado de presentación"},saved:{id:9003,reason_for_visit:"Motivo sintético QA",consultation_date:"2030-01-01"},completed:true,saving:false,bootstrapVersion:0,currentUser:user,onAnamnesisDirty(){},saveHistory(){}};
 return <main style={{maxWidth:1200,margin:"auto",padding:16,minWidth:0}}><h1>QA aislado · Visibilidad contextual</h1><p>Sin conexión a datos oficiales. Configurar aquí solo modifica la fixture en memoria.</p><nav style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:16}} aria-label="Escenarios QA">
 {['Administración','Consulta','Paciente'].map(label=><button key={label} disabled={role==='secretary'&&label==='Consulta'} onClick={()=>setView(label)}>{label}</button>)}
 <label>Audiencia QA <select value={role} onChange={e=>{audience=e.target.value;setRole(e.target.value);if(e.target.value==='secretary')setView('Paciente');}}><option value="doctor">Médico</option><option value="secretary">Secretaría sin permiso clínico</option></select></label></nav>
 {view==='Administración'?<FeatureVisibilitySettings/>:view==='Consulta'?<CardiologyModule key={role} item={item}/>:<Patients key={role} user={user} onBack={()=>setView('Administración')} onPatientChanged={()=>{}} onScheduleAppointment={()=>{}}/>}</main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
