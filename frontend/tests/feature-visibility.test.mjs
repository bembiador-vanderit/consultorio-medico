import {after,afterEach,beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';
import {createBrowser} from './browser.mjs';
const {dom,setDesktop}=createBrowser();
const {createElement:h,act}=await import('react');
const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Safety}=await server.ssrLoadModule('/src/components/patients/ContextualSafetyProfile.tsx');
const {default:Settings}=await server.ssrLoadModule('/src/components/FeatureVisibilitySettings.tsx');
const {default:Cardiology}=await server.ssrLoadModule('/src/components/consultation/CardiologyModule.tsx');
const {default:Patients}=await server.ssrLoadModule('/src/pages/Patients.tsx');
const {default:Shared}=await server.ssrLoadModule('/src/components/patients/SharedClinicalAccess.tsx');
const {api}=await server.ssrLoadModule('/src/services/api.ts');
const adapter=api.defaults.adapter,host=document.getElementById('root');
const doctor={id:7,roles:['doctor'],permissions:['patients:view','clinical:access','patient_safety:view']};
const patient={id:8,first_name:'Paciente',last_name:'QA',date_of_birth:'1990-01-01'};
const entry={id:3,entry_type:'allergy',substance_or_agent:'Agente sensible QA',reaction_description:'Reacción sensible QA',severity:'critical',status:'active',source_type:'patient_reported',recorded_at:'2030-01-01T10:00:00Z',updated_at:'2030-01-01T10:00:00Z'};
const hidden=()=>({clinical_safety_full:false,clinical_safety_critical_alert:false});
const rows=()=>Object.keys(hidden()).flatMap(feature_code=>['doctor','secretary'].map(audience=>({feature_code,context_code:'ambulatory',audience,visibility_mode:null,revision:0,visible:false,source:'system_default'})));
let root,requests,features,settings,fail;
beforeEach(()=>{root=createRoot(host);requests=[];features=hidden();fail=false;setDesktop(true);settings={enabled:true,center_id:null,items:rows(),centers:[{id:1,name:'Centro QA'}]};
 api.defaults.adapter=async config=>{requests.push(config);let data;
  if(config.url==='/feature-visibility/resolved'){if(fail)throw Error('QA unavailable');data={features};}
  else if(config.url==='/feature-visibility/settings'){
   if(config.method==='put'){const payload=JSON.parse(config.data);settings={...settings,items:payload.changes.map(i=>({...i,revision:i.revision+1,visible:i.visibility_mode==='visible'}))};}
   data=settings;
  }
  else if(config.url==='/patient-safety/capabilities')data={enabled:true,can_edit:false};
  else if(config.url==='/patient-safety/patients/8')data=[entry];
  else if(config.url==='/patients')data=[patient];
  else if(config.url==='/patients/8')data=patient;
  else if(config.url.endsWith('/cardiology'))data={revision:0,symptoms:{},cardiovascular_history:{},examination:{},studies:[],follow_up:{kind:'none'}};
  else if(config.url.endsWith('/capabilities'))data={enabled:true,resources:['patient_safety']};
  else if(config.url.endsWith('/records/patient_safety'))data={read_only:true,items:[{fields:[{label:'Estado',value:'active'},{label:'Tipo',value:'allergy'},{label:'Severidad',value:'critical'},{label:'Agente',value:'No exponer QA'}]}],offset:0,limit:50,total:1};
  else data=[];
  return{data,status:200,statusText:'QA',headers:{},config};
 };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=adapter;});
after(async()=>{await server.close();dom.window.close();});
const button=name=>[...document.querySelectorAll('button')].find(e=>e.textContent.trim()===name);
const click=async e=>{assert.ok(e);await act(async()=>e.click());};
const mount=async(user=doctor)=>act(async()=>root.render(h(Safety,{patientId:8,patientName:'Paciente QA',user,centerId:1})));
async function value(e,next){assert.ok(e);await act(async()=>{const proto=e.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLSelectElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,next);e.dispatchEvent(new window.Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));});}

for(const role of ['doctor','secretary'])test(role+' default hidden never loads Safety',async()=>{
 await mount({...doctor,roles:[role]});assert.equal(host.textContent,'');assert.equal(requests.length,1);assert.equal(requests[0].url,'/feature-visibility/resolved');assert.equal(requests[0].params.center_id,1);
});
test('full visible restores original permission-gated panel and modal',async()=>{
 features.clinical_safety_full=true;await mount();assert.ok(button('Ver seguridad clínica'));assert.doesNotMatch(host.textContent,/ALERGIA ACTIVA REGISTRADA/);
 await click(button('Ver seguridad clínica'));assert.match(document.querySelector('dialog').textContent,/Agente sensible QA/);assert.equal(button('Agregar'),undefined);
});
test('critical independent shows only compact warning, no agent or full button',async()=>{
 features.clinical_safety_critical_alert=true;await mount();assert.match(host.textContent,/Alergia crítica registrada/);assert.doesNotMatch(host.textContent,/Agente sensible|Reacción sensible/);assert.equal(button('Ver seguridad clínica'),undefined);
});
for(const user of [{...doctor,roles:['secretary']},{...doctor,permissions:['patients:view']},{...doctor,roles:['admin']}])test('visible does not bypass clinical authorization '+JSON.stringify(user.roles)+user.permissions.length,async()=>{
 features={clinical_safety_full:true,clinical_safety_critical_alert:true};await mount(user);assert.equal(host.textContent,'');assert.equal(requests.some(r=>r.url.startsWith('/patient-safety')),false);
});
test('focus refresh applies admin changes and hides an open detail without session-long cache',async()=>{
 features.clinical_safety_full=true;await mount();await click(button('Ver seguridad clínica'));features=hidden();
 await act(async()=>window.dispatchEvent(new window.Event('focus')));assert.equal(host.textContent,'');assert.equal(document.querySelector('dialog[open]'),null);
});
test('unavailable resolver fails hidden, not permission fallback',async()=>{fail=true;await mount();assert.equal(host.textContent,'');assert.equal(requests.some(r=>r.url.startsWith('/patient-safety')),false);});
test('admin switches for each audience and feature save reason/revisions only',async()=>{
 await act(async()=>root.render(h(Settings)));assert.match(host.textContent,/Consulta ambulatoria/);const boxes=host.querySelectorAll('input[type=checkbox]');assert.equal(boxes.length,4);assert.ok([...boxes].every(b=>!b.checked));
 await click(boxes[0]);await click(boxes[3]);await value(host.querySelector('textarea'),'QA cambio visible');
 await act(async()=>host.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 const p=JSON.parse(requests.find(r=>r.method==='put').data);assert.equal(p.changes[0].visibility_mode,'visible');assert.equal(p.changes[1].visibility_mode,'hidden');assert.equal(p.changes[3].visibility_mode,'visible');assert.equal(p.reason,'QA cambio visible');assert.equal(p.changes[0].revision,0);assert.match(host.textContent,/guardada y auditada/);
});
test('admin supports center override and restoring inheritance',async()=>{
 await act(async()=>root.render(h(Settings)));await value(host.querySelector('select'),'1');assert.equal(requests.at(-1).params.center_id,1);await value(host.querySelector('textarea'),'QA heredar centro');await click(button('Heredar organización'));assert.ok(JSON.parse(requests.find(r=>r.method==='put').data).changes.every(i=>i.visibility_mode===null));
});
test('schema pending prevents admin writes',async()=>{settings.enabled=false;await act(async()=>root.render(h(Settings)));assert.match(host.textContent,/pendiente de activación/);assert.equal(host.querySelector('form'),null);});
test('cardiology uses the central resolver with appointment center',async()=>{
 const item={appointment:{id:9,patient_id:8,patient_name:'Paciente QA',center_id:1},context:{},saved:null,completed:false,saving:false,bootstrapVersion:0,currentUser:doctor,onAnamnesisDirty(){},saveHistory(){}};
 await act(async()=>root.render(h(Cardiology,{item})));assert.match(host.textContent,/Consulta cardiológica/);assert.equal(button('Ver seguridad clínica'),undefined);assert.equal(requests.find(r=>r.url.includes('visibility')).params.center_id,1);
});
test('patient page hides safety by default but leaves unrelated patient controls',async()=>{
 await act(async()=>root.render(h(Patients,{user:doctor,onBack(){},onPatientChanged(){},onScheduleAppointment(){}})));await click(host.querySelector('.patients-row'));assert.equal(button('Ver seguridad clínica'),undefined);assert.ok(button('Historia clínica'));assert.equal(requests.some(r=>r.url==='/patient-safety/patients/8'),false);
});
test('shared safety hidden does not automatically open content despite sharing permission',async()=>{
 await act(async()=>root.render(h(Shared,{patientId:8,patientName:'Paciente QA',user:doctor})));assert.equal(host.textContent,'');assert.equal(requests.some(r=>r.url.includes('/records/')),false);
});
test('shared compact alert uses authorized 0060 projection and exposes no sensitive detail',async()=>{
 features.clinical_safety_critical_alert=true;await act(async()=>root.render(h(Shared,{patientId:8,patientName:'Paciente QA',user:doctor})));assert.match(host.textContent,/Alergia crítica registrada/);assert.doesNotMatch(host.textContent,/No exponer QA/);assert.equal(button('Ver seguridad clínica'),undefined);assert.ok(requests.some(r=>r.url.includes('/records/patient_safety')));
});
test('responsive semantic controls and bounded layout, no clinical or commercial inputs',async()=>{
 setDesktop(false);await act(async()=>root.render(h(Settings)));assert.equal(host.querySelectorAll('input[type=checkbox]').length,4);assert.ok([...host.querySelectorAll('input')].every(e=>e.closest('label')));
 const css=await readFile(new URL('../src/components/featureVisibility.css',import.meta.url),'utf8');assert.match(css,/@media\(max-width:600px\)/);assert.match(css,/min-width:0/);assert.doesNotMatch(host.textContent,/Base\/Plus|PayPal|Hospitalización/);
});
