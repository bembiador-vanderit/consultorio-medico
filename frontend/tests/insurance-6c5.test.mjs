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
let root, calls, existing;
const policy = { id: 3, insurance_company_id: 1, insurance_company_name: 'ARS Prueba', member_number: 'SYNTHETIC', plan_id: 2, plan_name: 'Plan prueba', is_primary: true, is_active: true, valid_from: '2026-01-01', valid_until: '2026-12-31' };
const appointment = { id: 10, patient_id: 7, status: 'scheduled' };
const user = { roles: ['secretary'], permissions: ['patients:access', 'insurance:manage'] };
const states = [{ code: 'pending', label: 'Pendiente' }, { code: 'authorized', label: 'Autorizada' }, { code: 'rejected', label: 'Rechazada' }, { code: 'not_required', label: 'No requerida' }];
const sample = { id: 8, appointment_id: 10, patient_insurance_id: 3, service: 'Consulta', currency: 'DOP', base_amount: '1500.00', covered_amount: '1000.00', patient_copay: '500.00', expected_insurer_balance: '1000.00', authorization_status: 'pending', insurance_snapshot: { company_name: 'ARS histórica', plan_name: 'Plan histórico', member_number: 'OLD' }, revision: 1 };
const response = (config, data) => ({ config, data, status: 200, statusText: 'OK', headers: {} });
beforeEach(() => {
 root = createRoot(document.getElementById('root')); calls = []; existing = null;
 api.defaults.adapter = async config => {
   calls.push(config);
   if(config.method === 'put' && config.url.endsWith('/coverage')) { const body=JSON.parse(config.data); existing={...sample,...body,revision:body.revision+1}; return response(config,existing); }
   if(config.method !== 'get') return response(config, { id: 5, ...JSON.parse(config.data || '{}') });
   return response(config, config.url.endsWith('/coverage') ? existing : config.url.includes('authorization-states') ? states : config.url.includes('/patients/') ? [policy] : config.url.includes('/companies') ? [{id:1,name:'ARS Prueba',code:null,is_active:true}] : [{id:2,insurance_company_id:1,name:'Plan prueba',code:null,description:null,is_active:true}]);
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

test('secretary selects affiliation and saves amounts and authorization with revision',async () => {
 await act(async () => root.render(h(Coverage,{appointment,user})));
 await change(field('Seguro para'), '3'); await change(field('Servicio /'),'Consulta');
 await change(field('Tarifa base'),'1500'); await change(field('Monto cubierto'),'1000'); await change(field('Copago'),'500');
 await change(field('Estado de'),'authorized'); await change(field('Número de autorización'),'SYNTHETIC-AUTH');
 await submit(); const body=JSON.parse(calls.find(c=>c.method==='put').data);
 assert.equal(body.patient_insurance_id,3); assert.equal(body.patient_copay,'500'); assert.equal(body.revision,0); assert.equal(body.authorization_number,'SYNTHETIC-AUTH');
 assert.match(document.body.textContent,/Cobertura guardada/);
});

test('clinical reader sees snapshot and balances without administrative form',async () => {
 existing=sample; await act(async () => root.render(h(Coverage,{appointment,user:{roles:['doctor'],permissions:['patients:access','clinical:access']}})));
 assert.match(document.body.textContent,/ARS histórica/); assert.match(document.body.textContent,/500.00 DOP/); assert.match(document.body.textContent,/1000.00 DOP/);
 assert.equal(document.querySelector('form'),null);
});

test('completed appointment preserves selected historical affiliation',async () => {
 existing=sample; await act(async () => root.render(h(Coverage,{appointment:{...appointment,status:'completed'},user})));
 assert.equal(field('Seguro para').disabled,true); assert.equal(field('Seguro para').value,'3');
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

test('patient affiliation editing includes plan, holder, validity and primary status',async () => {
 await act(async () => root.render(h(PatientInsurance,{patientId:7,patientName:'Paciente prueba',user,onClose(){}})));
 await act(async () => button('Editar seguro').click()); await change(field('Titular'),'Titular prueba'); await change(field('Vigente hasta'),'2027-01-01'); await submit();
 const call=calls.find(c=>c.method==='put'); assert.equal(call.url,'/insurance/patients/7/3');
 const data=JSON.parse(call.data); assert.equal(data.plan_id,2); assert.equal(data.policy_holder,'Titular prueba'); assert.equal(data.valid_until,'2027-01-01'); assert.equal(data.is_primary,true);
});

test('patient insurance reader cannot edit or deactivate',async () => {
 await act(async () => root.render(h(PatientInsurance,{patientId:7,patientName:'Paciente prueba',user:{roles:['doctor'],permissions:['patients:access']},onClose(){}})));
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
