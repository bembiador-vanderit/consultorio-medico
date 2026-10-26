/** Visual QA only. No backend requests, authentication, or real patient data. */
import React from "react";
import { createRoot } from "react-dom/client";
import PatientSafetyProfile from "../../src/components/patients/PatientSafetyProfile";
import { api } from "../../src/services/api";
import type { PatientSafetyEntry } from "../../src/types/patientSafety";
import "../../src/index.css";

if (!import.meta.env.DEV) throw new Error("Synthetic preview is development-only");
const user = { id:9001, email:"qa-safety@example.com", full_name:"Médico sintético QA", is_active:true,
  roles:["doctor"], permissions:["patients:view","clinical:access","patient_safety:view","patient_safety:edit"] };
const entry:PatientSafetyEntry = { id:1, patient_id:9002, organization_id:9003, clinical_history_id:null,
  entry_type:"allergy", substance_or_agent:"Agente sintético QA — no representa un paciente real",
  reaction_description:"Descripción sintética para comprobar legibilidad y ajuste de texto en pantallas estrechas.",
  severity:"critical", status:"active", source_type:"patient_reported", source_description:"Referencia sintética, no confirmación médica",
  onset_date:null, notes:"Datos exclusivamente sintéticos; no se envían al backend.",
  recorded_by_user_id:9001, updated_by_user_id:9001, recorded_by_name:user.full_name, updated_by_name:user.full_name,
  recorded_at:"2030-01-01T10:00:00Z", updated_at:"2030-01-01T10:00:00Z", revision:1 };
let entries:PatientSafetyEntry[] = [entry, {...entry,id:2,entry_type:"adverse_reaction",severity:"unknown",substance_or_agent:"Segundo agente QA",source_type:"family_reported"}];
api.defaults.adapter = async config => {
  if (!config.url?.startsWith("/patient-safety/")) throw new Error("Non-QA request blocked");
  let data:unknown;
  if(config.url.endsWith("capabilities")) data={enabled:true,can_edit:true};
  else if(config.url.endsWith("/history")) data=[{id:1,actor_id:9001,at:entry.recorded_at,action:"patient_safety.created",context:{before:null,after:entry,reason:null}}];
  else if(config.method==="get") data=entries;
  else if(config.method==="put" || config.method==="post") {
    const id=config.method==="post"?entries.length+1:Number(config.url.split("/").at(-1));
    const next={...entry,...JSON.parse(config.data),id};
    entries=[next,...entries.filter(e=>e.id!==id)];data=next;
  } else throw new Error("Unsupported QA request");
  return {data,status:200,statusText:"QA only",headers:{},config};
};
createRoot(document.getElementById("root")!).render(<main className="atlas-page-container">
  <h1>QA sintético — Seguridad clínica</h1>
  <p>Vista aislada de presentación. Sin conexión a la base oficial.</p>
  <PatientSafetyProfile patientId={9002} patientName="Paciente sintético QA" user={user}/>
</main>);
