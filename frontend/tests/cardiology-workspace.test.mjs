import {after,afterEach,beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';
import {createBrowser} from './browser.mjs';
const {dom,setDesktop}=createBrowser();const {createElement:h,act}=await import('react');const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Cardiology}=await server.ssrLoadModule('/src/components/consultation/CardiologyModule.tsx');
const {default:Inbox}=await server.ssrLoadModule('/src/components/FollowUpInbox.tsx');
const {AppointmentForm}=await server.ssrLoadModule('/src/components/agenda/AppointmentForm.tsx');
const {api}=await server.ssrLoadModule('/src/services/api.ts');const adapter=api.defaults.adapter,host=document.getElementById('root');
let root,requests,item,record,contacts,savedNarrative,scheduled,task;
const fresh=()=>({revision:0,symptoms:{},cardiovascular_history:{},examination:{},impression:'',plan:'',studies:[],follow_up:{kind:'none'}});
beforeEach(()=>{setDesktop(true);root=createRoot(host);requests=[];record=fresh();contacts=[];scheduled=null;savedNarrative=null;
 task={id:22,patient_id:6,patient_name:'Paciente QA',doctor_id:2,doctor_name:'Médico QA',center_id:1,specialty_id:3,due_at:null,reason:'Retorno QA',condition:'Holter QA',status:'pending',appointment_id:null};
 item={appointment:{id:81,patient_id:6,patient_name:'Paciente QA',patient_date_of_birth:'1990-01-01',doctor_name:'Médico QA',center_name:'Centro QA'},context:{appointment_reason:'Motivo administrativo QA',patient_registered_sex:'female'},saved:{id:42,revision:1,consultation_date:'2030-01-01',reason_for_visit:'Motivo QA'},completed:false,saving:false,bootstrapVersion:0,currentUser:null,onAnamnesisDirty(){},saveHistory(value){savedNarrative=value;}};
 api.defaults.adapter=async config=>{requests.push(config);let data;
  if(config.url.endsWith('/cardiology')){if(config.method==='put'){const {expected_revision,...values}=JSON.parse(config.data);record={...values,revision:expected_revision+1};}data=record;}
  else if(config.url==='/follow-ups/inbox')data={enabled:true,items:[task]};
  else if(config.url.endsWith('/contacts')){if(config.method==='post'){const p=JSON.parse(config.data);contacts.push({id:contacts.length+1,...p,created_at:'2030-01-01T12:00:00',actor_id:9});task={...task,status:'contacted'};}data=contacts;}
  else if(config.url==='/appointments/queue-capabilities')data={booking_order_enabled:true};
  else if(config.url==='/appointments/effective-mode')data={schedule_mode:'timed',allowed_timed:true,allowed_queue:true,default_mode:'timed',queue_line_available:true,multimode_enabled:true};
  else if(config.url==='/appointments/doctors')data=[{id:2,full_name:'Médico QA',center_ids:[1],specialties:[{id:3,name:'Cardiología'}]}];
  else if(config.url==='/appointments'&&config.method==='post')data={id:90,...JSON.parse(config.data)};
  else throw Error('Unexpected QA request '+config.url);
  return{data,status:200,statusText:'OK',headers:{},config};};
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=adapter;});after(async()=>{await server.close();dom.window.close();});
const mount=async()=>act(async()=>root.render(h(Cardiology,{item})));
const button=name=>[...host.querySelectorAll('button')].find(e=>e.textContent===name);
const click=async name=>{assert.ok(button(name),name);await act(async()=>button(name).click());};
const field=label=>[...host.querySelectorAll('label')].find(e=>[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('')===label)?.querySelector('input,textarea,select');
async function change(el,value){assert.ok(el);await act(async()=>{const proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:el.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new window.Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));});}

test('cardiology uses clinical episode and keeps administrative reason separate',async()=>{await mount();assert.match(host.textContent,/Consulta cardiológica/);assert.match(host.textContent,/Motivo administrativo QA/);await change(field('Motivo de consulta'),'Complemento clínico QA');await click('Actualizar consulta');assert.equal(savedNarrative.reason_for_visit,'Complemento clínico QA');assert.equal(item.context.appointment_reason,'Motivo administrativo QA');assert.equal(host.querySelector('label')?.textContent.includes('Alergias'),false);});
test('symptoms preserve explicit no, detail and dirty state with optimistic revision',async()=>{const dirty=[];item.onAnamnesisDirty=v=>dirty.push(v);await mount();await click('Síntomas');const group=[...host.querySelectorAll('fieldset')].find(e=>e.querySelector('legend')?.textContent==='Dolor torácico');await act(async()=>[...group.querySelectorAll('button')].find(b=>b.textContent==='No').click());await change(field('Detalle de Dolor torácico'),'QA optional');assert.equal(dirty.at(-1),true);await click('Guardar evaluación cardiológica');const body=JSON.parse(requests.find(r=>r.method==='put').data);assert.equal(body.symptoms.chest_pain.present,false);assert.equal(body.symptoms.chest_pain.detail,'QA optional');assert.equal(body.expected_revision,0);assert.equal(dirty.at(-1),false);});
test('examination and impression are separate from coded diagnoses and vitals',async()=>{await mount();await click('Examen');await change(field('Soplos'),'QA hallazgo');await click('Plan');await change(field('Impresión clínica'),'QA impresión');await change(field('Plan'),'QA plan');await click('Guardar evaluación cardiológica');assert.equal(record.examination.murmurs,'QA hallazgo');assert.equal(record.impression,'QA impresión');assert.equal(record.plan,'QA plan');assert.equal('diagnoses' in record,false);assert.equal('systolic_pressure' in record,false);});
for(const kind of ['days','weeks','months','studies','date'])test('structured follow-up '+kind,async()=>{await mount();await click('Seguimiento');await change(field('Indicación de seguimiento'),kind);if(['days','weeks','months'].includes(kind))await change(field('Plazo de seguimiento'),'10');if(kind==='date')await change(field('Fecha de retorno'),'2030-03-01');await change(field('Motivo del seguimiento'),'QA retorno');await change(field('Estudios o documentos antes del retorno'),'QA Holter');await click('Guardar evaluación cardiológica');assert.equal(record.follow_up.kind,kind);assert.equal(record.follow_up.reason,'QA retorno');assert.equal(record.follow_up.condition,'QA Holter');assert.equal(requests.some(r=>r.url==='/appointments'),false);});
test('completed is read-only and has no save actions',async()=>{item.completed=true;await mount();await click('Síntomas');assert.ok([...host.querySelectorAll('fieldset')].every(e=>e.disabled));assert.equal(button('Guardar evaluación cardiológica'),undefined);assert.equal(button('Actualizar consulta'),undefined);});
test('draft fields survive tab changes and tab order remains native',async()=>{await mount();await click('Examen');await change(field('Ritmo cardíaco'),'QA ritmo');await click('Plan');await click('Examen');assert.equal(field('Ritmo cardíaco').value,'QA ritmo');assert.equal(host.querySelector('[tabindex="-1"]'),null);const css=await readFile(new URL('../src/components/consultation/cardiology.css',import.meta.url),'utf8');assert.match(css,/@media\(max-width:600px\)/);assert.match(css,/minmax\(0,1fr\)/);});
test('secretary inbox records append-only contacts without clinical fields',async()=>{await act(async()=>root.render(h(Inbox,{user:{roles:['secretary']},onSchedule:t=>{scheduled=t;}})));assert.match(host.textContent,/Retorno QA/);await click('Ver / registrar contacto');await change(field('Resultado del contacto'),'no_answer');await click('Registrar contacto');await change(field('Resultado del contacto'),'retry');await click('Registrar contacto');assert.equal(contacts.length,2);assert.match(host.textContent,/No respondió/);assert.match(host.textContent,/Llamar nuevamente/);assert.equal(field('Impresión clínica'),undefined);await click('Agendar cita');assert.equal(scheduled.id,22);assert.equal(requests.filter(r=>r.method==='post').length,2);});
test('return booking reuses AppointmentForm and posts follow_up_id atomically',async()=>{let appointment;await act(async()=>root.render(h(AppointmentForm,{appointment:null,initialPatient:{id:6,first_name:'Paciente',last_name:'QA',date_of_birth:'1990-01-01'},initialFollowUp:task,date:'2030-01-02',centers:[{id:1,name:'Centro QA'}],user:{id:9,roles:['secretary'],permissions:['patients:access']},onClose(){},onSaved:v=>{appointment=v;}})));const timeInput=document.querySelector('input[type="time"]');await change(timeInput,'10:00');const btn=[...document.querySelectorAll('button')].find(b=>b.textContent==='Guardar cita');assert.ok(btn);await act(async()=>btn.click());assert.equal(appointment.follow_up_id,22);assert.equal(appointment.patient_id,6);assert.equal(appointment.doctor_id,2);assert.equal(appointment.center_id,1);assert.equal(appointment.specialty_id,3);});

test('409 de Seguimientos conserva contexto y permite reintento sin cerrar',async()=>{
 let saved=null,closed=false;const normal=api.defaults.adapter;
 api.defaults.adapter=async config=>{if(config.url==='/appointments'&&config.method==='post')throw{response:{status:409,data:{detail:'El médico ya tiene una cita activa en ese horario.'}}};return normal(config);};
 await act(async()=>root.render(h(AppointmentForm,{appointment:null,initialPatient:{id:6,first_name:'Paciente',last_name:'QA',date_of_birth:'1990-01-01'},initialFollowUp:task,date:'2030-01-02',centers:[{id:1,name:'Centro QA'}],user:{id:9,roles:['secretary'],permissions:['patients:access']},onClose(){closed=true;},onSaved:v=>{saved=v;}})));
 const modal=()=>document.querySelector('dialog[open]');
 const save=()=>[...modal().querySelectorAll('button')].find(b=>b.textContent==='Guardar cita');
 await act(async()=>save().click());
 assert.match(modal().textContent,/El médico ya tiene una cita activa en ese horario/);
 assert.match(modal().textContent,/Paciente QA/);assert.equal(saved,null);assert.equal(closed,false);
 assert.equal(modal().querySelector('input[type="date"]').value,'2030-01-02');
 await change(modal().querySelector('input[type="time"]'),'08:30');api.defaults.adapter=normal;
 await act(async()=>save().click());
 assert.equal(saved.follow_up_id,22);assert.equal(saved.appointment_time,'08:30');assert.equal(saved.doctor_id,2);assert.equal(saved.center_id,1);assert.equal(saved.patient_id,6);
});
