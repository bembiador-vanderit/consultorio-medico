import {after,afterEach,beforeEach,test} from "node:test";
import assert from "node:assert/strict";
import {createServer} from "vite";
import {createBrowser} from "./browser.mjs";
const {dom,setDesktop}=createBrowser();
const {createElement:h,act}=await import("react");
const {createRoot}=await import("react-dom/client");
const server=await createServer({server:{middlewareMode:true,ws:false},appType:"custom",optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Related}=await server.ssrLoadModule("/src/components/patients/PatientRelatedDoctors.tsx");
const {default:Patients}=await server.ssrLoadModule("/src/pages/Patients.tsx");
const {api}=await server.ssrLoadModule("/src/services/api.ts");
const adapter=api.defaults.adapter;
const host=document.getElementById("root");
const doctor={id:1,roles:["doctor"],permissions:["patients:view","patient_care:view"]};
const record={id:5,organization_id:1,patient_id:8,doctor_id:1,doctor_name:"Doctora sintética QA",center_id:1,center_name:"Centro QA",specialty_id:1,specialty_name:"Especialidad QA",organization_name:"Organización QA",relationship_type:"treating",origin:"consultation",status:"active",started_at:"2030-01-01T10:00:00Z",first_seen_at:"2030-01-01T10:00:00Z",last_seen_at:"2030-01-02T10:00:00Z",ended_at:null};
let root,rows,requests,enabled,fail;
beforeEach(()=>{
 root=createRoot(host);rows=[record];requests=[];enabled=true;fail=false;setDesktop(true);
 api.defaults.adapter=async config=>{
  requests.push(config);assert.equal(config.method,"get");if(fail)throw Error("QA failure");
  const data=config.url==="/patient-care/capabilities"?{enabled,can_manage:false}:rows;
  return{data,status:200,statusText:"OK",headers:{},config};
 };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=adapter;});
after(async()=>{await server.close();dom.window.close();});
const mount=async(user=doctor)=>act(async()=>root.render(h(Related,{patientId:8,patientName:"Paciente QA",user})));
const button=name=>[...document.querySelectorAll("button")].find(e=>e.textContent.trim()===name);
const click=async e=>{assert.ok(e);await act(async()=>e.click());};
const panel=()=>[...document.querySelectorAll("dialog[open]")].at(-1);

test("compact summary shows doctor specialty state and last care",async()=>{
 await mount();assert.match(host.textContent,/Médicos relacionados/);assert.match(host.textContent,/Doctora sintética QA/);
 assert.match(host.textContent,/Especialidad QA/);assert.match(host.textContent,/Activa.*Última atención/);
 assert.ok(button("Ver médicos relacionados"));
});
test("empty and failed loads are not assertions of absent historical care",async()=>{
 rows=[];await mount();assert.match(host.textContent,/No equivale a ausencia de atenciones previas/);
 await act(async()=>root.unmount());root=createRoot(host);fail=true;await mount();assert.match(host.textContent,/No fue posible consultar/);
 assert.doesNotMatch(host.textContent,/No hay relaciones asistenciales registradas/);
});
test("staged schema absence hides feature without requesting missing table",async()=>{
 enabled=false;await mount();assert.equal(host.textContent,"");assert.equal(requests.length,1);
});
for(const user of [{...doctor,permissions:["patients:view"]},{...doctor,permissions:["patient_care:view"]},{...doctor,roles:["secretary"]}]){
 test(`unauthorized profile makes no requests: ${JSON.stringify(user)}`,async()=>{await mount(user);assert.equal(host.textContent,"");assert.equal(requests.length,0);});
}
test("active/follow-up are prioritized and summary remains bounded",async()=>{
 rows=[{...record,id:1,status:"historical",doctor_name:"Histórico QA"},...Array.from({length:5},(_,i)=>({...record,id:i+2,status:i===0?"follow_up":"active",doctor_name:`Actual QA ${i}`}))];
 await mount();assert.equal(host.querySelectorAll("li").length,3);assert.doesNotMatch(host.textContent,/Histórico QA/);assert.match(host.textContent,/3 relaciones adicionales/);
});
test("historical relationship remains visible if no current ones",async()=>{
 rows=[{...record,status:"historical"}];await mount();assert.match(host.textContent,/Histórica/);
});
test("read-only modal shows origin context and warns discovery is not access",async()=>{
 await mount();await click(button("Ver médicos relacionados"));assert.equal(panel().querySelector("h2").textContent,"Médicos relacionados con el paciente");
 assert.match(panel().textContent,/Consulta finalizada/);assert.match(panel().textContent,/Centro QA/);assert.match(panel().textContent,/Organización QA/);
 assert.match(panel().textContent,/no asigna responsabilidad del episodio actual ni concede acceso al historial/);
 assert.equal(panel().querySelector("input,select,textarea,form"),null);
 assert.equal(button("Editar"),undefined);assert.equal(requests.filter(r=>r.method!=="get").length,0);
 await click(button("Cerrar"));assert.equal(panel(),undefined);
});
test("admin discovery does not expose editing controls even with manage capability",async()=>{
 await mount({...doctor,roles:["admin"],permissions:[...doctor.permissions,"patient_care:manage","users:manage"]});
 await click(button("Ver médicos relacionados"));assert.equal(panel().querySelector("form,input,select"),null);assert.equal(button("Asignar médico"),undefined);
});
test("administrative origin is not presented as an actual first attention",async()=>{
 rows=[{...record,origin:"administrative_assignment",first_seen_at:null,last_seen_at:null,center_name:null,specialty_name:null}];
 await mount();assert.match(host.textContent,/Sin atención registrada/);await click(button("Ver médicos relacionados"));
 assert.match(panel().textContent,/Asignación administrativa/);assert.match(panel().textContent,/Sin centro específico/);
});
test("mobile and desktop keep one accessible read-only modal",async()=>{
 setDesktop(false);await mount();await click(button("Ver médicos relacionados"));assert.equal(document.querySelectorAll("dialog[open]").length,1);
 assert.equal(panel().querySelectorAll("dl").length,1);assert.equal(panel().querySelector("form"),null);
 await act(async()=>setDesktop(true));assert.equal(document.querySelectorAll("dialog[open]").length,1);
});
test("patient workspace queries the selected patient only and clears old associations",async()=>{
 const a={id:8,first_name:"Paciente",last_name:"QA Uno",date_of_birth:"1990-01-01"},b={...a,id:9,last_name:"QA Dos"};
 api.defaults.adapter=async config=>{
  requests.push(config);assert.equal(config.method,"get");
  const data=config.url==="/patients"?[a,b]:config.url==="/patients/8"?a:config.url==="/patients/9"?b:
   config.url==="/patient-care/capabilities"?{enabled:true}:config.url==="/patient-care/patients/8/relationships"?[record]:config.url==="/patient-care/patients/9/relationships"?[]:undefined;
  assert.notEqual(data,undefined,config.url);return{data,status:200,statusText:"OK",headers:{},config};
 };
 await act(async()=>root.render(h(Patients,{user:doctor,onBack(){},onPatientChanged(){},onScheduleAppointment(){}})));
 await click(host.querySelectorAll(".patients-row")[0]);assert.ok(host.querySelector(".patients-detail-body .patient-related-doctors"));
 assert.match(host.textContent,/Doctora sintética QA/);await click(host.querySelectorAll(".patients-row")[1]);
 assert.doesNotMatch(host.textContent,/Doctora sintética QA/);assert.match(host.textContent,/No hay relaciones asistenciales registradas/);
});
