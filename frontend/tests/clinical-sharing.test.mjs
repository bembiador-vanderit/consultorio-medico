import {after,afterEach,beforeEach,test} from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createServer} from "vite";
import {createBrowser} from "./browser.mjs";
const {dom,setDesktop}=createBrowser();
const {createElement:h,act}=await import("react");
const {createRoot}=await import("react-dom/client");
const server=await createServer({server:{middlewareMode:true,ws:false},appType:"custom",optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Shared}=await server.ssrLoadModule("/src/components/patients/SharedClinicalAccess.tsx");
const {default:Settings}=await server.ssrLoadModule("/src/components/ClinicalSharingPolicySettings.tsx");
const {default:Patients}=await server.ssrLoadModule("/src/pages/Patients.tsx");
const {api}=await server.ssrLoadModule("/src/services/api.ts");
const adapter=api.defaults.adapter,host=document.getElementById("root");
const doctor={id:2,roles:["doctor"],permissions:["patients:view","clinical:access"]};
const defaultPolicy={enabled:true,revision:0,mode:"assigned",limit_to_same_center:true,clinical_history:false,clinical_documents:false,patient_safety:false};
let root,requests,resources,policy,fail;
beforeEach(()=>{
 root=createRoot(host);requests=[];resources=["clinical_history","clinical_documents","patient_safety"];policy={...defaultPolicy};fail=false;setDesktop(true);
 api.defaults.adapter=async config=>{
   requests.push(config);if(fail&&config.url.includes("/records/"))throw Error("QA denial");
   let data;
   if(config.url==="/feature-visibility/resolved")data={features:{clinical_safety_full:true,clinical_safety_critical_alert:true}};
   else if(config.url.endsWith("/policy"))data=config.method==="put"?{...JSON.parse(config.data),enabled:true,revision:1}:policy;
   else if(config.url.endsWith("/capabilities"))data={enabled:true,resources};
   else data={read_only:true,resource:config.url.split("/").at(-1),items:[{id:7,title:"Registro clínico QA",date:"2030-01-01",doctor_name:"Doctora QA",status:"signed",read_only:true,fields:[{label:"Valor QA",value:false}]}],total:1,offset:0,limit:25};
   return {data,status:200,statusText:"OK",headers:{},config};
 };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=adapter;});
after(async()=>{await server.close();dom.window.close();});
const mount=async(user=doctor,patientId=8)=>act(async()=>root.render(h(Shared,{patientId,patientName:"Paciente QA",user})));
const button=name=>[...document.querySelectorAll("button")].find(e=>e.textContent.trim()===name);
const click=async e=>{assert.ok(e);await act(async()=>e.click());};
const panel=()=>[...document.querySelectorAll("dialog[open]")].at(-1);

test("default restrictive capabilities hide shared resources and never fetch content",async()=>{
 resources=[];await mount();assert.equal(host.textContent,"");assert.equal(requests.length,2);assert.equal(requests.filter(r=>r.url.endsWith("/capabilities")).length,1);assert.equal(requests.filter(r=>r.url.includes("/records/")).length,0);
});
for(const permissions of [[],["patients:view"],["clinical:access"]]){
 test(`missing baseline permission never queries sharing ${permissions}`,async()=>{await mount({...doctor,permissions});assert.equal(requests.length,0);assert.equal(host.textContent,"");});
}
test("administrative role never receives medical content",async()=>{
 await mount({...doctor,roles:["admin"]});assert.equal(requests.length,0);assert.equal(host.textContent,"");
});
test("opening is explicit with read-only indicator; technical render does not read",async()=>{
 await mount();assert.match(host.textContent,/Historial compartido en modo solo lectura/);
 assert.equal(requests.filter(r=>r.url.includes("/records/")).length,0);
 await click(button("Ver historia clínica"));assert.match(panel().textContent,/Historia clínica · Solo lectura/);
 assert.match(panel().textContent,/Doctora QA/);assert.match(panel().textContent,/Valor QA.*No/);
 assert.equal(panel().querySelector("input,textarea,select,form"),null);
 assert.equal(requests.filter(r=>r.url.includes("/records/")).length,1);
 assert.equal(button("Editar"),undefined);assert.equal(button("Guardar"),undefined);
 await click(button("Cerrar"));assert.equal(panel(),undefined);
});
for(const [resource,label] of [["clinical_documents","documentos clínicos"],["patient_safety","seguridad clínica"]]){
 test(`${resource} is a read-only projection, not an editable form`,async()=>{
  resources=[resource];await mount();assert.equal(button("Ver historia clínica"),undefined);
  await click(button(`Ver ${label}`));assert.match(panel().textContent,/Solo lectura/);assert.equal(panel().querySelector("form,input,textarea"),null);
  assert.equal(requests.at(-1).method,"get");
 });
}
test("resource denied after capability loads reveals no stale content",async()=>{
 await mount();fail=true;await click(button("Ver historia clínica"));assert.match(panel().textContent,/autorización puede haber cambiado/);
 assert.doesNotMatch(panel().textContent,/Registro clínico QA/);
});
test("switching patient clears content and closes previous record",async()=>{
 await mount();await click(button("Ver historia clínica"));resources=[];await mount(doctor,9);
 assert.equal(panel(),undefined);assert.doesNotMatch(host.textContent,/Registro clínico QA/);
});
test("mobile and desktop use shared modal without editable controls",async()=>{
 setDesktop(false);await mount();await click(button("Ver historia clínica"));assert.equal(document.querySelectorAll("dialog[open]").length,1);
 await act(async()=>setDesktop(true));assert.equal(panel().querySelector("form"),null);
 const css=await readFile(new URL("../src/components/patients/sharedClinicalAccess.css",import.meta.url),"utf8");
 assert.match(css,/minmax\(0,1fr\)/);assert.match(css,/overflow-wrap:anywhere/);assert.match(css,/@media\(max-width:600px\)/);
});
test("administration defaults conservative and configures modes and resource opt-ins",async()=>{
 await act(async()=>root.render(h(Settings)));assert.equal(host.querySelector("select").value,"assigned");
 const boxes=host.querySelectorAll('input[type="checkbox"]');assert.equal(boxes.length,4);
 assert.equal(boxes[0].checked,true);assert.ok([...boxes].slice(1).every(e=>!e.checked));
 const select=host.querySelector("select");await act(async()=>{select.value="active_relationship";select.dispatchEvent(new window.Event("change",{bubbles:true}));});
 await click(boxes[1]);
 const textarea=host.querySelector("textarea");await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,"value").set.call(textarea,"Motivo sintético QA");textarea.dispatchEvent(new window.Event("input",{bubbles:true}));});
 await act(async()=>host.querySelector("form").dispatchEvent(new window.Event("submit",{bubbles:true,cancelable:true})));
 const payload=JSON.parse(requests.find(r=>r.method==="put").data);
 assert.equal(payload.mode,"active_relationship");assert.equal(payload.clinical_history,true);assert.equal(payload.patient_safety,false);assert.equal(payload.revision,0);
 assert.match(host.textContent,/Política guardada y auditada/);
});
test("staged schema absent prevents administrative writes",async()=>{
 policy={...defaultPolicy,enabled:false};await act(async()=>root.render(h(Settings)));
 assert.match(host.textContent,/pendiente de activación/);assert.equal(host.querySelector("form"),null);assert.equal(requests.length,1);
});
test("shared-only patient identity has no edit, scheduling or normal history actions",async()=>{
 const patient={id:8,first_name:"Paciente",last_name:"QA",date_of_birth:"1990-01-01",phone:null,email:null,created_at:"2030-01-01"};
 api.defaults.adapter=async config=>{
  requests.push(config);assert.equal(config.method,"get");
  const data=config.url==="/patients"?[patient]:config.url==="/patients/8"?{...patient,shared_read_only:true}:
   config.url.endsWith("/capabilities")?{enabled:true,resources:["clinical_history"]}:[];
  return {data,status:200,statusText:"OK",headers:{},config};
 };
 await act(async()=>root.render(h(Patients,{user:{...doctor,permissions:[...doctor.permissions,"patients:edit"]},onBack(){},onPatientChanged(){},onScheduleAppointment(){throw Error("not shared access");}})));
 await click(host.querySelector(".patients-row"));
 assert.equal(button("Historia clínica"),undefined);assert.equal(button("Agendar cita"),undefined);assert.equal(button("Seguro"),undefined);
 assert.ok(button("Ver historia clínica"));await click(button("Ver ficha"));
 assert.equal(button("Editar"),undefined);assert.equal(button("Guardar cambios"),undefined);
});
