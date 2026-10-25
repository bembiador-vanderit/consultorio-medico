import {after,afterEach,beforeEach,test} from "node:test";
import assert from "node:assert/strict";
import {createServer} from "vite";
import {createBrowser} from "./browser.mjs";
const {dom,setDesktop}=createBrowser();
const {createElement:h,act}=await import("react");
const {createRoot}=await import("react-dom/client");
const server=await createServer({server:{middlewareMode:true,ws:false},appType:"custom",optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Profile}=await server.ssrLoadModule("/src/components/patients/PatientSafetyProfile.tsx");
const {default:Patients}=await server.ssrLoadModule("/src/pages/Patients.tsx");
const {api}=await server.ssrLoadModule("/src/services/api.ts");
const adapter=api.defaults.adapter;
const host=document.getElementById("root");
const doctor={id:1,roles:["doctor"],permissions:["patients:view","clinical:access","patient_safety:view","patient_safety:edit"]};
const record={id:4,patient_id:8,organization_id:1,entry_type:"allergy",substance_or_agent:"Agente QA",reaction_description:"Reacción sintética QA",severity:"critical",status:"active",source_type:"patient_reported",source_description:null,notes:null,onset_date:null,clinical_history_id:null,recorded_by_user_id:1,updated_by_user_id:1,recorded_by_name:"Médico QA",updated_by_name:"Médico QA",recorded_at:"2030-01-01T10:00:00Z",updated_at:"2030-01-01T10:00:00Z",revision:1};
let root,requests,rows,canEdit,enabled,fail;
beforeEach(()=>{root=createRoot(host);requests=[];rows=[record];canEdit=true;enabled=true;fail=false;setDesktop(true);
 api.defaults.adapter=async config=>{
  requests.push(config);if(fail)throw {response:{data:{detail:"Error sintético"}}};let data;
  if(config.url==="/patient-safety/capabilities")data={enabled,can_edit:canEdit};
  else if(config.url.endsWith("/history"))data=[{id:1,actor_id:1,at:record.recorded_at,action:"patient_safety.created",context:{before:null,after:record,reason:null}}];
  else if(config.method==="get")data=rows;
  else if(config.method==="post"){data={...record,...JSON.parse(config.data),id:10};rows=[data,...rows];}
  else if(config.method==="put"){data={...record,...JSON.parse(config.data),revision:2};rows=[data];}
  else throw Error("Unexpected endpoint");return{data,status:200,statusText:"OK",headers:{},config};
 };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=adapter;});
after(async()=>{await server.close();dom.window.close();});
const mount=async(user=doctor)=>act(async()=>root.render(h(Profile,{patientId:8,patientName:"Paciente QA",user})));
const button=name=>[...document.querySelectorAll("button")].find(e=>e.textContent.trim()===name);
const click=async e=>{assert.ok(e);await act(async()=>e.click());};
const panel=()=>[...document.querySelectorAll("dialog[open]")].at(-1);
const field=name=>{const label=[...panel().querySelectorAll("label")].find(e=>e.textContent.startsWith(name));assert.ok(label,name);return document.getElementById(label.htmlFor);};
async function value(e,next){await act(async()=>{const proto=e.tagName==="SELECT"?dom.window.HTMLSelectElement.prototype:e.tagName==="TEXTAREA"?dom.window.HTMLTextAreaElement.prototype:dom.window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,"value").set.call(e,next);e.dispatchEvent(new dom.window.Event(e.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const submit=async()=>act(async()=>panel().querySelector("form").dispatchEvent(new dom.window.Event("submit",{bubbles:true,cancelable:true})));

test("active severe allergy is visible with provenance and detail starts read-first",async()=>{
 await mount();assert.match(host.textContent,/ALERGIA ACTIVA REGISTRADA/);assert.match(host.textContent,/Referido por paciente/);
 await click(button("Ver seguridad clínica"));assert.equal(panel().querySelector("h2").textContent,"Seguridad clínica del paciente");
 assert.equal(panel().querySelector("input,select,textarea"),null);assert.match(panel().textContent,/Médico QA/);assert.ok(button("Agregar"));
 assert.equal(requests.filter(r=>r.method!=="get").length,0);
});
test("no clinical permission or a secretary never requests safety information",async()=>{
 await mount({...doctor,roles:["secretary"]});assert.equal(host.textContent,"");assert.equal(requests.length,0);
});
test("pending schema activation hides the staged feature",async()=>{
 enabled=false;await mount();assert.equal(host.textContent,"");assert.equal(requests.length,1);
});
test("empty profile does not assert absence of allergy and a load failure is not empty",async()=>{
 rows=[];await mount();assert.match(host.textContent,/no equivale a ausencia de alergias/);
 await act(async()=>root.unmount());root=createRoot(host);fail=true;await mount();
 assert.match(host.textContent,/No fue posible consultar/);assert.doesNotMatch(host.textContent,/No hay registros activos/);
});
test("inactive or entered-in-error allergy never triggers an active warning",async()=>{
 rows=[{...record,status:"inactive"},{...record,id:5,status:"entered_in_error"}];await mount();
 assert.doesNotMatch(host.textContent,/ALERGIA ACTIVA REGISTRADA/);await click(button("Ver seguridad clínica"));assert.match(panel().textContent,/Registrado por error/);assert.equal(button("Editar Agente QA")?.textContent,"Editar Agente QA");
});
test("view-only clinician can read but not add or edit",async()=>{
 canEdit=false;await mount({...doctor,permissions:doctor.permissions.filter(p=>p!=="patient_safety:edit")});await click(button("Ver seguridad clínica"));
 assert.equal(button("Agregar"),undefined);assert.equal(button("Editar Agente QA"),undefined);
});
test("add explicitly captures type, source, severity and saves only once",async()=>{
 rows=[];await mount();await click(button("Ver seguridad clínica"));await click(button("Agregar"));
 assert.equal(field("Tipo").value,"");assert.equal(field("Procedencia").value,"");assert.equal(field("Severidad").value,"unknown");
 for(const[name,next]of[["Tipo","adverse_reaction"],["Sustancia / Agente","Agente nuevo QA"],["Reacción / Descripción clínica","Descripción QA"],["Procedencia","family_reported"],["Severidad","moderate"]])await value(field(name),next);
 await act(async()=>{panel().querySelector("form").dispatchEvent(new dom.window.Event("submit",{bubbles:true,cancelable:true}));panel().querySelector("form").dispatchEvent(new dom.window.Event("submit",{bubbles:true,cancelable:true}));});
 assert.equal(requests.filter(r=>r.method==="post").length,1);assert.equal(panel().querySelector("form"),null);assert.match(panel().textContent,/Referido por familiar/);
 const payload=JSON.parse(requests.find(r=>r.method==="post").data);assert.equal(payload.patient_id,undefined);assert.equal(payload.entry_type,"adverse_reaction");
});
test("cancel dirty edits confirms discard, never writes, and restores original entry",async()=>{
 await mount();await click(button("Ver seguridad clínica"));await click(button("Editar Agente QA"));await value(field("Sustancia / Agente"),"No guardar QA");
 await click(button("Cancelar"));assert.match(panel().textContent,/Hay cambios sin guardar/);await click(button("Seguir editando"));assert.equal(field("Sustancia / Agente").value,"No guardar QA");
 await click(button("Cancelar"));await click(button("Descartar cambios"));assert.match(panel().textContent,/Agente QA/);assert.equal(requests.some(r=>r.method==="put"),false);
});
test("state change includes required reason and revision; noop edit does not write",async()=>{
 await mount();await click(button("Ver seguridad clínica"));await click(button("Editar Agente QA"));await submit();assert.equal(requests.some(r=>r.method==="put"),false);
 await click(button("Editar Agente QA"));await value(field("Estado"),"entered_in_error");assert.ok(field("Motivo del cambio").required);await value(field("Motivo del cambio"),"Corrección sintética QA");await submit();
 const sent=JSON.parse(requests.find(r=>r.method==="put").data);assert.equal(sent.revision,1);assert.equal(sent.change_reason,"Corrección sintética QA");assert.equal(button("Editar Agente QA"),undefined);
});
test("history is fetched on demand and shown only in the medical panel",async()=>{
 await mount();await click(button("Ver seguridad clínica"));assert.equal(requests.some(r=>r.url.endsWith("history")),false);
 await click(button("Ver trazabilidad de Agente QA"));assert.match(panel().textContent,/Trazabilidad/);assert.match(panel().textContent,/Usuario #1/);
});
test("mobile and desktop share semantic controls without parallel forms",async()=>{
 setDesktop(false);await mount();await click(button("Ver seguridad clínica"));await click(button("Agregar"));assert.equal(panel().querySelectorAll("form").length,1);
 assert.equal(panel().querySelectorAll(".patient-safety-grid").length,1);assert.equal(panel().querySelectorAll(".atlas-field").length,10);
 await act(async()=>setDesktop(true));assert.equal(panel().querySelectorAll("form").length,1);
});

test("patient workspace keeps safety visible in scroll body and never mixes selected patients",async()=>{
 const first={id:8,first_name:"Paciente",last_name:"QA Uno",date_of_birth:"1990-01-01",phone:null,email:null};
 const second={...first,id:9,last_name:"QA Dos"};
 api.defaults.adapter=async config=>{
  requests.push(config);
  const data=config.url==="/patients"?[first,second]:config.url==="/patients/8"?first:config.url==="/patients/9"?second:
   config.url==="/feature-visibility/resolved"?{features:{clinical_safety_full:true,clinical_safety_critical_alert:true}}:
   config.url==="/patient-safety/capabilities"?{enabled:true,can_edit:true}:config.url==="/patient-safety/patients/8"?[record]:config.url==="/patient-safety/patients/9"?[]:undefined;
  assert.notEqual(data,undefined,config.url);return{data,status:200,statusText:"OK",headers:{},config};
 };
 await act(async()=>root.render(h(Patients,{user:doctor,onBack(){},onPatientChanged(){},onScheduleAppointment(){}})));
 await click(host.querySelectorAll(".patients-row")[0]);
 assert.ok(host.querySelector(".patients-detail-body .patient-safety"));
 assert.equal(host.querySelector(".patients-detail-fixed .patient-safety"),null);
 assert.match(host.textContent,/ALERGIA ACTIVA REGISTRADA/);
 await click(host.querySelectorAll(".patients-row")[1]);
 assert.doesNotMatch(host.textContent,/ALERGIA ACTIVA REGISTRADA|Agente QA/);
 assert.match(host.textContent,/No hay registros activos documentados/);
 assert.equal(requests.some(r=>r.method!=="get"),false);
});
