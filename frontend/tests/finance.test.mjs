import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';
const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Finance } = await server.ssrLoadModule('/src/pages/Finance.tsx');
const { default: Charge } = await server.ssrLoadModule('/src/components/FinanceCharge.tsx');
const { default: CardCorrection } = await server.ssrLoadModule('/src/components/FinanceCardCorrection.tsx');
const { Sidebar } = await server.ssrLoadModule('/src/layouts/AtlasAppShell.tsx');
const { getFinanceNavigationGroups, getNavigationItems } = await server.ssrLoadModule('/src/navigation/navigation.ts');
const { api } = await server.ssrLoadModule('/src/services/api.ts');
const original = api.defaults.adapter;
const user = { id: 1, roles: ['secretary'], permissions: ['finance:read','finance:collect'] };
const zeros = { cash:'0',card:'0',transfer:'0',check:'0',other:'0' };
const cash = { id:1,opened_by:1,state:'open',opening_amount:'100',opened_at:'2026-09-25T10:00:00',totals:{collected:zeros,reversed:zeros,expected_cash:'100',adjustments_in:'0',adjustments_out:'0'} };
const invoice = { id:3,number:'INT-1-00000003',center_id:1,patient_id:7,patient_name:'Paciente sintético',concept:'Consulta',base_amount:'1500',ars_amount:'1000',expected_ars:'1000',patient_amount:'500',paid_amount:'200',balance:'300',state:'partial',created_at:'2026-09-25T10:00:00',coverage_snapshot:{},movements:[] };
let root, calls, registers, preview, rejectPayment, batches, providers;
const response = (config, data) => ({ config, data, status:200, statusText:'OK', headers:{} });
beforeEach(() => {
  root = createRoot(document.getElementById('root')); calls=[]; registers=[cash]; preview={coverage:null,invoice:null}; rejectPayment=false;
  batches=[]; providers=[{provider:'CARDNET',enabled:true},{provider:'AZUL',enabled:false},{provider:'VISANET',enabled:false}];
  api.defaults.adapter = async config => {
    calls.push(config);
    if (config.method === 'post') { if (rejectPayment) throw {response:{status:409,data:{detail:'Caja cerrada'}}}; return response(config, {...invoice,balance:'0'}); }
    if (config.method === 'put' && config.url.includes('/card-providers/')) {
      const provider=config.url.split('/').pop(); providers=providers.map(p=>p.provider===provider?{...p,...JSON.parse(config.data)}:p);
      return response(config,providers.find(p=>p.provider===provider));
    }
    const data = config.url === '/finance/centers' ? [{id:1,name:'Centro sintético'}]
      : config.url === '/finance/centers/1/card-providers' ? providers
      : config.url === '/finance/registers/1/card-batches' ? batches
      : config.url === '/finance/registers/1/card-batch-history' ? []
      : config.url === '/finance/registers' ? registers
      : config.url === '/finance/summary' ? {collected:zeros,reversed:zeros,copays:'0',private:'0',patient_pending:'300',ars_expected:'1000',adjustments:'0'}
      : config.url === '/finance/invoices' ? [invoice]
      : config.url === '/finance/invoices/3' ? invoice
      : config.url === '/finance/patients' ? [{id:7,name:'Paciente sintético'}]
      : config.url === '/finance/appointments' ? [{id:9,date:'2026-09-25',status:'completed'}]
      : config.url === '/finance/preview' ? preview : [];
    return response(config,data);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter=original; });
after(async () => { await server.close(); dom.window.close(); });
const button = text => [...document.querySelectorAll('button')].find(b => b.textContent===text);
const field = text => { const label=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(text)); assert.ok(label,text); return document.getElementById(label.htmlFor); };
async function click(text) { const b=button(text); assert.ok(b,text); await act(async () => b.click()); }
async function change(label,value) { const el=field(label); await act(async () => { Object.getOwnPropertyDescriptor(el.tagName==='SELECT' ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype,'value').set.call(el,value); el.dispatchEvent(new dom.window.Event(el.tagName==='SELECT' ? 'change':'input',{bubbles:true})); }); }
async function submit(form=document.querySelector('form')) { await act(async () => form.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}))); }
async function mountCharge(props={}) { await act(async () => root.render(h(Charge,{centerId:1,register:cash,onDone(){},onCancel(){},...props}))); }
async function selectPatient() { await change('Buscar paciente','Paciente'); await act(async () => { await new Promise(resolve=>setTimeout(resolve,300)); }); await change('Paciente','7'); }
async function addPayment(amount) { await click('Añadir método'); await change('Importe 1',amount); }

test('financial navigation requires explicit capability even for admin',async () => {
  assert.ok(getNavigationItems(user).some(x=>x.view==='finance'));
  assert.equal(getNavigationItems(user).find(x=>x.view==='finance').group,'general');
  assert.ok(!getNavigationItems(user).some(x=>x.view==='finance' && x.group==='administration'));
  assert.ok(!getNavigationItems({roles:['admin'],permissions:[]}).some(x=>x.view==='finance'));
  assert.ok(!getNavigationItems({roles:['doctor']}).some(x=>x.view==='finance'));
});
test('finance navigation groups reuse capabilities and hide empty groups',async () => {
  assert.deepEqual(getFinanceNavigationGroups({permissions:['finance:read']}),[{id:'daily',label:'Operación diaria',sections:[
    {index:1,label:'Facturación'},{index:2,label:'Movimientos'},{index:3,label:'Pendientes'},
  ]}]);
  assert.deepEqual(getFinanceNavigationGroups({permissions:['ars:read']}),[{id:'ars',label:'ARS',sections:[
    {index:4,label:'Reclamaciones'},
  ]}]);
  const limited=getFinanceNavigationGroups({permissions:['ars:read','ars:payment','ars:report','ars:reconcile']});
  assert.deepEqual(limited.map(group=>group.id),['ars','control']);
  assert.deepEqual(limited[0].sections.map(option=>option.label),['Reclamaciones','Pagos / remesas','CxC ARS']);
});
test('finance sidebar accordion shares section selection and accessible active state',async () => {
  const userWithArs={roles:['secretary'],permissions:['finance:read','ars:read','ars:report','ars:reconcile']};
  const items=getNavigationItems(userWithArs);
  let selectedView='dashboard',selectedSection=0;
  const renderSidebar=async()=>await act(async()=>root.render(h(Sidebar,{items,user:userWithArs,activeView:selectedView,activeFinanceSection:selectedSection,onNavigate(view){selectedView=view;},onNavigateFinanceSection(section){selectedSection=section;selectedView='finance';}})));
  await renderSidebar();
  const financeToggle=[...document.querySelectorAll('.atlas-navigation-finance-toggle')][0];
  assert.equal(financeToggle.getAttribute('aria-expanded'),'false');
  assert.ok(document.getElementById(financeToggle.getAttribute('aria-controls')).hidden);
  await act(async()=>financeToggle.click());
  assert.equal(financeToggle.getAttribute('aria-expanded'),'true');
  assert.equal(selectedView,'finance');
  const claims=[...document.querySelectorAll('.atlas-navigation-finance-panel button')].find(button=>button.textContent.includes('Reclamaciones'));
  assert.ok(claims);
  await act(async()=>claims.click());
  assert.equal(selectedSection,4);
  await renderSidebar();
  assert.equal([...document.querySelectorAll('.atlas-navigation-finance-panel button')].find(button=>button.textContent.includes('Reclamaciones')).getAttribute('aria-current'),'page');
});
test('doctor cannot load financial page or request financial data',async () => {
  await act(async () => root.render(h(Finance,{user:{id:1,roles:['doctor'],permissions:['clinical:access']}})));
  assert.match(document.body.textContent,/Sin permiso/); assert.equal(calls.length,0);
});
test('cash page exposes all sections and keeps ARS outside collected totals',async () => {
  await act(async () => root.render(h(Finance,{user})));
  for(const name of ['Caja','Facturación','Movimientos','Pendientes']) assert.ok(button(name));
  assert.match(document.body.textContent,/No cobrada en Caja/); assert.ok(field('Efectivo contado'));
  assert.equal(button('Registrar ajuste'),undefined);
});
test('finance mobile groups behave as a single-open accordion and keep active section',async () => {
  const fullUser={...user,permissions:[...user.permissions,'ars:read','ars:report','ars:reconcile']};
  await act(async()=>root.render(h(Finance,{user:fullUser})));
  const daily=document.querySelectorAll('.finance-mobile-group-toggle')[0];
  const ars=document.querySelectorAll('.finance-mobile-group-toggle')[1];
  const control=document.querySelectorAll('.finance-mobile-group-toggle')[2];
  assert.equal(daily.getAttribute('aria-expanded'),'true');
  assert.equal(ars.getAttribute('aria-expanded'),'false');
  await act(async()=>ars.click());
  assert.equal(daily.getAttribute('aria-expanded'),'false');
  assert.equal(ars.getAttribute('aria-expanded'),'true');
  assert.equal(document.querySelectorAll('.finance-mobile-group .finance-section-options:not([hidden])').length,1);
  const activeClaims=[...document.querySelectorAll('.finance-mobile-group .finance-section-options button')].find(button=>button.textContent==='Reclamaciones');
  assert.equal(activeClaims.getAttribute('aria-current'),'page');
  await act(async()=>control.click());
  assert.equal(ars.getAttribute('aria-expanded'),'false');
  assert.equal(control.getAttribute('aria-expanded'),'true');
  assert.equal(document.querySelectorAll('.finance-mobile-group .finance-section-options:not([hidden])').length,1);
});
test('open register confirms center and initial cash',async () => {
  registers=[]; await act(async () => root.render(h(Finance,{user})));
  await change('Monto inicial','250'); await submit(); await click('Confirmar');
  const body=JSON.parse(calls.find(c=>c.method==='post').data); assert.equal(body.center_id,1); assert.equal(body.opening_amount,'250');
});
test('cash difference requires explanation and sends close values',async () => {
  await act(async () => root.render(h(Finance,{user})));
  await change('Efectivo contado','90'); assert.equal(field('Observación de cierre').required,true);
  await change('Observación de cierre','Diferencia sintética'); await submit(); await click('Confirmar');
  const c=calls.find(c=>c.method==='post'); assert.equal(c.url,'/finance/registers/1/close'); assert.equal(JSON.parse(c.data).notes,'Diferencia sintética');
});
test('admin configures only needed card providers and closes own register batch with POS figures',async () => {
  batches=[{id:null,provider:'CARDNET',batch_number:'QA-07',state:'open',atlas_count:2,atlas_amount:'300.00',declared_count:null,declared_amount:null,count_difference:null,amount_difference:null,closed_by:null,closed_at:null,ever_closed:false}];
  await act(async () => root.render(h(Finance,{user:{...user,permissions:[...user.permissions,'finance:manage']}})));
  const azul=[...document.querySelectorAll('label')].find(l=>l.textContent.includes('AZUL'))?.querySelector('input[type=checkbox]');
  assert.ok(azul); assert.equal(azul.checked,false);
  await act(async () => azul.click());
  const toggle=calls.find(c=>c.method==='put' && c.url.endsWith('/AZUL'));
  assert.deepEqual(JSON.parse(toggle.data),{enabled:true});
  await change('Cantidad del voucher CARDNET QA-07','2');
  await change('Monto del voucher CARDNET QA-07','300');
  const closeForm=button('Cerrar lote').closest('form'); await submit(closeForm);
  const close=calls.find(c=>c.method==='post' && c.url.endsWith('/card-batches'));
  assert.deepEqual(JSON.parse(close.data),{provider:'CARDNET',batch_number:'QA-07',declared_count:2,declared_amount:'300',notes:''});
});
test('private mixed payment uses one operation and shows residual balance',async () => {
  await mountCharge(); await selectPatient(); await change('Tarifa base','1500');
  await addPayment('200'); await click('Añadir método'); await change('Importe 2','300');
  await change('Número de lote del voucher 2','LOTE-07'); await submit();
  assert.match(document.body.textContent,/Saldo restante/); await click('Confirmar operación');
  const callsPosted=calls.filter(c=>c.method==='post'); assert.equal(callsPosted.length,1);
  const body=JSON.parse(callsPosted[0].data); assert.equal(body.payment.parts.length,2); assert.equal(body.payment.parts[1].batch_number,'LOTE-07'); assert.equal(body.payment.parts[1].provider,'CARDNET'); assert.equal(body.base_amount,'1500'); assert.equal(body.coverage_revision,null);
});

test('card payment cannot advance without voucher batch',async () => {
  await mountCharge(); await selectPatient(); await change('Tarifa base','1500');
  await addPayment('200'); await change('Método 1','card');
  assert.equal(field('Prestadora de tarjeta 1').value,'CARDNET');
  assert.ok(field('Número de lote del voucher 1'));
  await submit();
  assert.match(document.body.textContent,/número de lote del voucher/i);
  assert.equal(button('Confirmar operación'),undefined);
  assert.equal(calls.filter(c=>c.method==='post').length,0);
});
test('admin card correction sends provider, lot and reason without editing the amount',async () => {
  providers[1].enabled=true;
  const movement={id:91,register_id:1,invoice_id:3,kind:'payment',amount:'100.00',parts:[{method:'card',amount:'100.00',provider:'CARDNET',batch_number:'OLD'}]};
  let done=false;
  await act(async () => root.render(h(CardCorrection,{centerId:1,movement,onDone(){done=true;}})));
  await change('Prestadora corregida #91','AZUL'); await change('Lote corregido #91','NEW');
  await change('Motivo de corrección #91','Error sintético'); await submit();
  const request=calls.find(c=>c.method==='put' && c.url==='/finance/movements/91/card-assignment');
  assert.deepEqual(JSON.parse(request.data),{provider:'AZUL',batch_number:'NEW',reason:'Error sintético'});
  assert.equal(done,true);
});
test('insured appointment reuses locked coverage and revision',async () => {
  await mountCharge(); await selectPatient();
  preview={coverage:{revision:4,concept:'Consulta cubierta',base_amount:'1500',ars_amount:'1000',patient_amount:'500',insurance:{company_name:'ARS sintética'},authorization_status:'pending'},invoice:null};
  await change('Cita / atención','9'); assert.equal(field('Tarifa base').disabled,true);
  assert.match(document.body.textContent,/ARS sintética/); await addPayment('200'); await submit(); await click('Confirmar operación');
  const body=JSON.parse(calls.find(c=>c.method==='post').data); assert.equal(body.coverage_revision,4); assert.equal(body.appointment_id,9); assert.equal(body.base_amount,'1500');
});
test('private invoice with no payment creates patient pending balance',async () => {
  await mountCharge({register:undefined}); await selectPatient(); await change('Tarifa base','750'); await submit(); await click('Confirmar operación');
  const body=JSON.parse(calls.find(c=>c.method==='post').data); assert.equal(body.payment,null);
});
test('pending account applies payment to same invoice',async () => {
  await act(async () => root.render(h(Finance,{user})));
  await click('Pendientes'); assert.ok(calls.some(c=>c.params?.pending===true));
  await click('Aplicar pago'); await addPayment('100'); await submit(); await click('Confirmar operación');
  const c=calls.find(c=>c.method==='post'); assert.equal(c.url,'/finance/invoices/3/payments'); assert.equal(JSON.parse(c.data).parts[0].amount,'100');
});
test('overpayment and closed register do not submit',async () => {
  await mountCharge({invoice}); await addPayment('301'); await submit(); assert.match(document.body.textContent,/no puede exceder/); assert.equal(calls.filter(c=>c.method==='post').length,0);
});
test('no active cash register blocks receiving payment',async () => {
  await mountCharge({invoice,register:undefined}); await addPayment('100'); await submit(); assert.match(document.body.textContent,/Abra una caja/); assert.equal(button('Confirmar operación'),undefined);
});
test('failed confirmation retries identical UUID without duplicating operation',async () => {
  await mountCharge({invoice}); await addPayment('100'); await submit(); rejectPayment=true; await click('Confirmar operación');
  assert.match(document.body.textContent,/Caja cerrada/); assert.equal(button('Corregir').disabled,true);
  rejectPayment=false; await click('Reintentar misma operación');
  const posts=calls.filter(c=>c.method==='post'); assert.equal(posts.length,2); assert.deepEqual(JSON.parse(posts[0].data),JSON.parse(posts[1].data));
});
