import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';
const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Coverage } = await server.ssrLoadModule('/src/components/agenda/AppointmentInsurancePanel.tsx');
const { default: PatientInsurance } = await server.ssrLoadModule('/src/components/patients/PatientInsurancePanel.tsx');
const { default: Catalog } = await server.ssrLoadModule('/src/pages/InsuranceCatalog.tsx');
const { api } = await server.ssrLoadModule('/src/services/api.ts');
const original = api.defaults.adapter;
let root, calls, existing, patientPolicies, companyCatalog, planCatalog;
const policy = { id: 3, insurance_company_id: 1, insurance_company_name: 'ARS Prueba', member_number: 'SYNTHETIC', plan_id: 2, plan_name: 'Plan prueba', is_primary: true, is_active: true, valid_from: '2026-01-01', valid_until: '2026-12-31' };
const appointment = { id: 10, patient_id: 7, appointment_date: '2026-10-12', status: 'scheduled' };
const user = { roles: ['secretary'], permissions: ['patients:access', 'patients:view', 'insurance:manage'] };
const states = [{ code: 'pending', label: 'Pendiente' }, { code: 'authorized', label: 'Autorizada' }, { code: 'rejected', label: 'Rechazada' }, { code: 'not_required', label: 'No requerida' }];
const sample = { id: 8, appointment_id: 10, patient_insurance_id: 3, service: 'Consulta', currency: 'DOP', base_amount: '1500.00', covered_amount: '1000.00', patient_copay: '500.00', expected_insurer_balance: '1000.00', authorization_status: 'pending', insurance_snapshot: { company_name: 'ARS histórica', plan_name: 'Plan histórico', member_number: 'OLD' }, revision: 1 };
const response = (config, data) => ({ config, data, status: 200, statusText: 'OK', headers: {} });
beforeEach(() => {
 root = createRoot(document.getElementById('root')); calls = []; existing = null;
 patientPolicies = [policy]; companyCatalog = [{id:1,name:'ARS Prueba',code:null,is_active:true}];
 planCatalog = [{id:2,insurance_company_id:1,name:'Plan prueba',code:null,description:null,is_active:true}];
 api.defaults.adapter = async config => {
   calls.push(config);
   if(config.method === 'put' && config.url.endsWith('/coverage')) { const body=JSON.parse(config.data); existing={...sample,...body,revision:body.revision+1}; return response(config,existing); }
   if(config.method !== 'get') return response(config, { id: 5, ...JSON.parse(config.data || '{}') });
   return response(config, config.url.endsWith('/coverage') ? existing : config.url.includes('authorization-states') ? states : config.url.includes('/patients/') ? patientPolicies : config.url.includes('/companies') ? companyCatalog : planCatalog);
 };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = original; });
after(async () => { await server.close(); dom.window.close(); });
const button = text => [...document.querySelectorAll('button')].find(x => x.textContent===text);
function field(label) { const el=[...document.querySelectorAll('label')].find(x => x.textContent.startsWith(label)); assert.ok(el,label); return document.getElementById(el.htmlFor); }
async function change(el,value) {
 await act(async () => { Object.getOwnPropertyDescriptor(el.tagName==='SELECT' ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype,'value').set.call(el,value); el.dispatchEvent(new dom.window.Event(el.tagName==='SELECT' ? 'change' : 'input',{bubbles:true})); });
}
async function submit() { await act(async () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}))); }
async function chooseCoverage(value) { await act(async () => document.querySelector(`input[type="radio"][value="${value}"]`).click()); }
const hasField = label => [...document.querySelectorAll('label')].some(x => x.textContent.startsWith(label));

test('particular and con seguro are explicit choices; particular hides ARS and authorization fields', async () => {
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.match(document.body.textContent,/Tipo de cobertura/);
 assert.equal(document.querySelector('input[value="insured"]').checked,true);
 await chooseCoverage('particular');
 assert.equal(document.querySelector('input[value="particular"]').checked,true);
 assert.equal(hasField('Seguro / ARS'),false);
 assert.equal(hasField('Plan'),false);
 assert.equal(hasField('Monto cubierto'),false);
 assert.equal(hasField('Estado de autorización'),false);
 assert.equal(hasField('Tarifa base'),true);
});

test('particular saves zero ARS amount, patient total and no authorization without creating a payment', async () => {
 await act(async () => root.render(h(Coverage,{appointment,user})));
 await chooseCoverage('particular'); await change(field('Servicio /'),'Consulta particular'); await change(field('Tarifa base'),'1200');
 await submit();
 const body=JSON.parse(calls.find(c=>c.method==='put').data);
 assert.equal(body.patient_insurance_id,null); assert.equal(body.covered_amount,'0.00');
 assert.equal(body.patient_copay,'1200'); assert.equal(body.authorization_status,'not_required');
 assert.equal(body.authorization_number,null);
 assert.match(document.body.textContent,/No se registró un cobro en Caja/);
});

test('active tenant catalog filters inactive insurers and plans and plans follow insurer', async () => {
 companyCatalog.push({id:2,name:'ARS Otra',code:null,is_active:true},{id:3,name:'ARS Inactiva',code:null,is_active:false});
 planCatalog.push({id:3,insurance_company_id:2,name:'Plan Otra',is_active:true},{id:4,insurance_company_id:1,name:'Plan Inactivo',is_active:false});
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.deepEqual([...field('Seguro / ARS').options].map(o=>o.textContent),['Seleccione...','ARS Prueba','ARS Otra']);
 assert.deepEqual([...field('Plan').options].map(o=>o.textContent),['Sin plan de catálogo','Plan prueba']);
 await change(field('Seguro / ARS'),'2');
 assert.deepEqual([...field('Plan').options].map(o=>o.textContent),['Sin plan de catálogo','Plan Otra']);
 assert.equal(field('Afiliación del paciente').value,'');
});

test('another valid patient affiliation can be selected; inactive and expired affiliations are excluded', async () => {
 companyCatalog.push({id:2,name:'ARS Otra',code:null,is_active:true});
 planCatalog.push({id:3,insurance_company_id:2,name:'Plan Otra',is_active:true});
 patientPolicies.push({...policy,id:4,insurance_company_id:2,insurance_company_name:'ARS Otra',plan_id:3,plan_name:'Plan Otra',is_primary:false},
   {...policy,id:5,is_active:false,is_primary:false}, {...policy,id:6,is_primary:false,valid_until:'2026-01-01'});
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.equal(field('Afiliación del paciente').value,'3');
 await change(field('Seguro / ARS'),'2');
 assert.equal(field('Afiliación del paciente').value,'4');
 assert.equal([...field('Afiliación del paciente').options].some(o=>o.value==='5'||o.value==='6'),false);
});

test('patient without affiliation can choose particular or is guided to register insurance', async () => {
 patientPolicies=[];
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.equal(document.querySelector('input[value="particular"]').checked,true);
 await chooseCoverage('insured'); await change(field('Seguro / ARS'),'1');
 assert.match(document.body.textContent,/Afiliación necesaria/);
 assert.ok(button('Registrar o editar seguro del paciente'));
 await change(field('Servicio /'),'Consulta'); await submit();
 assert.match(document.body.textContent,/Registre o seleccione una afiliación válida/);
 assert.equal(calls.some(c=>c.method==='put'),false);
 await act(async () => button('Registrar o editar seguro del paciente').click());
 assert.match(document.querySelector('dialog').textContent,/Registrar seguro/);
 assert.ok(calls.some(c=>c.url==='/insurance/companies?include_inactive=true'));
});

test('catalog plan is optional when existing affiliation has no catalog plan', async () => {
 planCatalog=[]; patientPolicies=[{...policy,plan_id:null,plan_name:'Plan legado'}];
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.equal(document.querySelector('input[value="insured"]').checked,true);
 assert.equal(field('Plan').value,'');
 assert.match(document.body.textContent,/Plan registrado en la afiliación: Plan legado/);
 await change(field('Servicio /'),'Consulta'); await change(field('Tarifa base'),'1500');
 await change(field('Monto cubierto'),'1000'); await change(field('Copago'),'500'); await submit();
 assert.equal(JSON.parse(calls.find(c=>c.method==='put').data).patient_insurance_id,3);
});

test('secretary selects affiliation and saves amounts and authorization with revision',async () => {
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.equal(field('Seguro / ARS').value,'1'); assert.equal(field('Plan').value,'2'); assert.equal(field('Afiliación del paciente').value,'3');
 await change(field('Servicio /'),'Consulta');
 await change(field('Tarifa base'),'1500'); await change(field('Monto cubierto'),'1000'); await change(field('Copago'),'500');
 await change(field('Estado de'),'authorized'); await change(field('Número de autorización'),'SYNTHETIC-AUTH');
 await submit(); const body=JSON.parse(calls.find(c=>c.method==='put').data);
 assert.equal(body.patient_insurance_id,3); assert.equal(body.patient_copay,'500'); assert.equal(body.revision,0); assert.equal(body.authorization_number,'SYNTHETIC-AUTH');
 assert.match(document.body.textContent,/Cobertura guardada/);
});

test('clinical reader sees snapshot and balances without administrative form',async () => {
 existing=sample; await act(async () => root.render(h(Coverage,{appointment,user:{roles:['doctor'],permissions:['patients:view','patients:access','clinical:access']}})));
 assert.match(document.body.textContent,/ARS histórica/); assert.match(document.body.textContent,/500.00 DOP/); assert.match(document.body.textContent,/1000.00 DOP/);
 assert.equal(document.querySelector('form'),null);
});

test('completed appointment preserves selected historical affiliation',async () => {
 existing=sample; await act(async () => root.render(h(Coverage,{appointment:{...appointment,status:'completed'},user})));
 assert.equal(field('Afiliación del paciente').disabled,true); assert.equal(field('Afiliación del paciente').value,'3');
});

test('conflict prevents overwrite until explicit reload',async () => {
 existing=sample; const adapter=api.defaults.adapter;
 api.defaults.adapter=async c => { if(c.method==='put') throw {response:{status:409,data:{detail:'La cobertura cambió'}}}; return adapter(c); };
 await act(async () => root.render(h(Coverage,{appointment,user}))); await submit();
 assert.equal(button('Guardar cobertura').disabled,true); assert.match(document.body.textContent,/La cobertura cambió/);
 await act(async () => button('Recargar cobertura').click()); assert.equal(button('Guardar cobertura').disabled,false);
});

test('validation errors allow correction and retry without discarding form',async () => {
 const adapter=api.defaults.adapter; api.defaults.adapter=async c => { if(c.method==='put') throw {response:{status:422,data:{detail:[{msg:'Importes inconsistentes'}]}}}; return adapter(c); };
 await act(async () => root.render(h(Coverage,{appointment,user}))); await change(field('Servicio /'),'Prueba'); await submit();
 assert.match(document.body.textContent,/Importes inconsistentes/); assert.equal(field('Servicio /').value,'Prueba'); assert.equal(button('Guardar cobertura').disabled,false);
});

test('cobertura muestra asteriscos y errores de requeridos solo después de guardar', async () => {
 await act(async () => root.render(h(Coverage,{appointment,user})));
 assert.match(document.body.textContent, /\* Campos obligatorios/);
 assert.doesNotMatch(document.body.textContent, /\(obligatorio\)|Monto autorizado \(opcional\)/);
 assert.equal(field('Servicio /').getAttribute('aria-invalid'), null);
 assert.equal(field('Seguro / ARS').required, true);
 await act(async () => button('Guardar cobertura').click());
 assert.equal(field('Servicio /').getAttribute('aria-invalid'), 'true');
 assert.match(document.body.textContent, /Este campo es obligatorio\./);
 assert.equal(calls.some(c => c.method === 'put'), false);
 await change(field('Servicio /'), 'Consulta');
 assert.equal(field('Servicio /').getAttribute('aria-invalid'), null);
});

test('patient affiliation editing includes plan, holder, validity and primary status',async () => {
 await act(async () => root.render(h(PatientInsurance,{patientId:7,patientName:'Paciente prueba',user,onClose(){}})));
 await act(async () => button('Editar seguro').click()); await change(field('Titular'),'Titular prueba'); await change(field('Vigente hasta'),'2027-01-01'); await submit();
 const call=calls.find(c=>c.method==='put'); assert.equal(call.url,'/insurance/patients/7/3');
 const data=JSON.parse(call.data); assert.equal(data.plan_id,2); assert.equal(data.policy_holder,'Titular prueba'); assert.equal(data.valid_until,'2027-01-01'); assert.equal(data.is_primary,true);
});

test('patient insurance reader cannot edit or deactivate',async () => {
 await act(async () => root.render(h(PatientInsurance,{patientId:7,patientName:'Paciente prueba',user:{roles:['doctor'],permissions:['patients:view','patients:access']},onClose(){}})));
 assert.equal(button('Editar seguro'),undefined); assert.equal(button('Desactivar'),undefined); assert.equal(document.querySelector('form'),null);
 assert.match(document.body.textContent,/SYNTHETIC/);
});

test('catalog edits insurer state without changing its identity',async () => {
 await act(async () => root.render(h(Catalog)));
 await act(async () => button('Editar ARS Prueba').click());
 await change(field('Nombre de la ARS'),'ARS Actualizada');
 await act(async () => document.querySelector('input[type=checkbox]').click()); await submit();
 const call=calls.find(c=>c.method==='put'); assert.equal(call.url,'/insurance/companies/1'); assert.equal(JSON.parse(call.data).is_active,false);
});

test('catálogo administrativo no marca campos vacíos antes del intento de guardar', async () => {
 await act(async () => root.render(h(Catalog)));
 assert.match(document.body.textContent, /\* Campos obligatorios/);
 assert.equal(field('Nombre de la ARS').getAttribute('aria-invalid'), null);
 await act(async () => button('Guardar aseguradora').click());
 assert.equal(field('Nombre de la ARS').getAttribute('aria-invalid'), 'true');
 assert.match(document.body.textContent, /Este campo es obligatorio\./);
 assert.equal(calls.some(c => c.method === 'post'), false);
 await change(field('Nombre de la ARS'), 'ARS ficticia');
 assert.equal(field('Nombre de la ARS').getAttribute('aria-invalid'), null);
});

test('insurance catalog navigation requires explicit administrative capability', async () => {
 const { getNavigationItems } = await server.ssrLoadModule('/src/navigation/navigation.ts');
 assert.ok(getNavigationItems({roles:['admin'],permissions:['users:manage']}).some(x=>x.view==='insurance'));
 assert.ok(!getNavigationItems({roles:['doctor'],permissions:['patients:view','patients:access']}).some(x=>x.view==='insurance'));
 assert.ok(!getNavigationItems({roles:['admin'],permissions:[]}).some(x=>x.view==='insurance'));
});
