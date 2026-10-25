/** Isolated DEV preview: synthetic data, no HTTP or access to the official DB. */
import React from "react";
import {createRoot} from "react-dom/client";
import {api} from "../../src/services/api";
import PatientRelatedDoctors from "../../src/components/patients/PatientRelatedDoctors";
import type {PatientCareRelationship} from "../../src/types/patientCare";
import "../../src/index.css";

if(!import.meta.env.DEV)throw new Error("Synthetic preview is development-only");
const user={id:9001,email:"qa-care@example.com",full_name:"Médico QA",is_active:true,roles:["doctor"],permissions:["patients:view","patient_care:view"]};
const row:PatientCareRelationship={id:1,organization_id:9003,patient_id:9002,doctor_id:9001,doctor_name:"Médica sintética QA — nombre largo para comprobar ajuste en pantallas estrechas",center_id:1,center_name:"Centro sintético QA",specialty_id:1,specialty_name:"Especialidad sintética QA",organization_name:"Organización sintética QA",relationship_type:"treating",origin:"consultation",status:"active",started_at:"2030-01-01T10:00:00Z",first_seen_at:"2030-01-01T10:00:00Z",last_seen_at:"2030-01-02T10:00:00Z",ended_at:null,created_from_clinical_history_id:null,last_clinical_history_id:null,created_by_user_id:9001,updated_by_user_id:9001,created_at:"2030-01-01T10:00:00Z",updated_at:"2030-01-02T10:00:00Z",revision:1};
const rows=[row,{...row,id:2,doctor_name:"Segundo médico sintético QA",status:"follow_up",relationship_type:"specialist_followup"},{...row,id:3,doctor_name:"Tercera médica sintética QA",status:"historical"}];
api.defaults.adapter=async config=>{
 if(config.method!=="get"||!config.url?.startsWith("/patient-care/"))throw new Error("Non-QA request blocked");
 return{data:config.url.endsWith("capabilities")?{enabled:true,can_manage:false}:rows,status:200,statusText:"QA only",headers:{},config};
};
createRoot(document.getElementById("root")!).render(<main style={{maxWidth:1050,margin:"0 auto",padding:"1rem"}}>
 <h1>QA sintético — Médicos relacionados</h1><p>Presentación aislada. Sin conexión a la base oficial.</p>
 <PatientRelatedDoctors patientId={9002} patientName="Paciente sintético QA" user={user}/>
</main>);
