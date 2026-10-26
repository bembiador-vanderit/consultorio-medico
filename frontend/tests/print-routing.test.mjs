import{after,afterEach,beforeEach,test}from'node:test';import assert from'node:assert/strict';import{readFile}from'node:fs/promises';
import{createServer}from'vite';import{createBrowser}from'./browser.mjs';
const{dom}=createBrowser();const{createElement:h,act}=await import('react');const{createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const{default:Action}=await server.ssrLoadModule('/src/components/FakePrintAction.tsx');const{api}=await server.ssrLoadModule('/src/services/api.ts');const{printStateLabels}=await server.ssrLoadModule('/src/services/printRouting.ts');
const original=api.defaults.adapter;let root,calls,state,denied,destinations;
const jobId='11111111-1111-4111-8111-111111111111';
beforeEach(()=>{root=createRoot(document.getElementById('root'));calls=[];state='queued';denied=false;destinations=[{target_agent:'22222222-2222-4222-8222-222222222222',target_printer:'printer-fake',station_name:'Estación autorizada QA',printer_name:'Fake spooler · SIN PAPEL',online:true,available:true}];
 api.defaults.adapter=async c=>{calls.push(c);if(denied)throw{response:{status:403}};return{config:c,status:200,statusText:'OK',headers:{},data:c.url.endsWith('destinations')?{fake_only:true,destinations}:c.url.endsWith('/cancel')?{job_id:jobId,status:'cancelled',copies:1,origin_type:'WEB_DESKTOP',result:null}:{job_id:jobId,status:state,copies:1,origin_type:'WEB_DESKTOP',result:null}}};});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=original});after(async()=>{await server.close();dom.window.close()});
const button=t=>[...document.querySelectorAll('button')].find(x=>x.textContent===t);
async function click(t){assert.ok(button(t),t);await act(async()=>button(t).click())}
async function change(el,value){await act(async()=>{Object.getOwnPropertyDescriptor(el.tagName==='SELECT'?dom.window.HTMLSelectElement.prototype:dom.window.HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))})}
async function mount(origin='WEB_DESKTOP'){await act(async()=>root.render(h(Action,{origin})));await click('Imprimir')}
async function select(){const all=document.querySelectorAll('dialog select');await change(all[0],destinations[0].target_agent);await change(all[1],destinations[0].target_printer)}
for(const origin of['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET'])test(`${origin} selects station printer copies without source_agent`,async()=>{await mount(origin);assert.ok(document.querySelector('dialog[open]'));assert.ok(button('Enviar a fake spooler').disabled);await select();await change(document.querySelector('dialog input'),'3');await click('Enviar a fake spooler');const data=JSON.parse(calls.find(c=>c.method==='post'&&c.url==='/print-jobs').data);assert.equal(data.origin_type,origin);assert.equal(data.copies,3);assert.equal(data.source_agent,undefined);assert.equal(data.requested_by,undefined);assert.equal(data.target_printer,'printer-fake');assert.match(document.body.textContent,/En cola/)});
for(const stateName of['queued','received','ready','printing','printed','failed','cancelled','expired','unknown'])test(`status ${stateName} is explicit and cannot imply an automatic reprint`,async()=>{state=stateName;await mount();await select();await click('Enviar a fake spooler');assert.ok(document.body.textContent.includes(printStateLabels[stateName]));assert.equal(button('Enviar a fake spooler'),undefined);if(['queued','received','ready'].includes(stateName))assert.ok(button('Cancelar trabajo'));else assert.equal(button('Cancelar trabajo'),undefined)});
test('copy limits and unavailable printer disable submit without fallback',async()=>{destinations[0].available=false;await mount();await change(document.querySelector('dialog select'),destinations[0].target_agent);const option=[...document.querySelectorAll('option')].find(x=>x.value==='printer-fake');assert.ok(option.disabled);assert.ok(button('Enviar a fake spooler').disabled);assert.equal(calls.filter(x=>x.method==='post').length,0)});
test('invalid copies cannot be submitted',async()=>{await mount();await select();for(const value of['0','1000','1.5']){await change(document.querySelector('dialog input'),value);assert.ok(button('Enviar a fake spooler').disabled)}await change(document.querySelector('dialog input'),'999');assert.equal(button('Enviar a fake spooler').disabled,false)});
test('offline destination queues deliberately and cancel is explicit',async()=>{destinations[0].online=false;await mount();await select();assert.match(document.body.textContent,/permanecerá en cola/);await click('Enviar a fake spooler');await click('Cancelar trabajo');assert.match(document.body.textContent,/Cancelado/)});
test('failed response retry keeps immutable job id and locks selections',async()=>{await mount();await select();const adapter=api.defaults.adapter;let first=true;api.defaults.adapter=async c=>{if(c.method==='post'&&first){first=false;calls.push(c);throw Error('Synthetic lost response')}return adapter(c)};await click('Enviar a fake spooler');const id=JSON.parse(calls.find(x=>x.method==='post').data).job_id;assert.ok(document.querySelector('dialog select').disabled);await click('Reintentar mismo trabajo');assert.equal(JSON.parse(calls.filter(x=>x.method==='post').at(-1).data).job_id,id)});
test('permission error does not invent destinations and responsive CSS wraps',async()=>{denied=true;await mount();assert.match(document.body.textContent,/No se pudieron cargar destinos/);assert.ok(button('Enviar a fake spooler').disabled);const css=await readFile(new URL('../src/components/fakePrintAction.css',import.meta.url),'utf8');assert.match(css,/max-width:600px/);assert.match(css,/min-width:0/);assert.match(css,/overflow-wrap:anywhere/)});

for(const[width,origin]of[[1440,'WEB_DESKTOP'],[390,'WEB_MOBILE'],[820,'WEB_TABLET']])test(`official flow ${origin} uses production API and marks no physical execution`,async()=>{
 Object.defineProperty(window,'innerWidth',{value:width,configurable:true});await act(async()=>root.render(h(Action,{origin:'WEB_DESKTOP',official:true})));await click('Imprimir');
 assert.match(document.body.textContent,/SafeValidation/);await select();await click('Validar sin imprimir');
 const sent=calls.find(c=>c.method==='post'&&c.url==='/print-routing');assert.ok(sent);assert.equal(JSON.parse(sent.data).origin_type,origin);
 assert.ok(calls.some(c=>c.url==='/print-routing/destinations'));assert.ok(calls.every(c=>!c.url.includes('local-agent:')));
});
test('official empty destination stays disabled',async()=>{destinations=[];await act(async()=>root.render(h(Action,{origin:'WEB_DESKTOP',official:true})));await click('Imprimir');assert.match(document.body.textContent,/No hay destinos autorizados/);assert.ok(button('Validar sin imprimir').disabled)});

async function physicalStatus(kind='AWAITING_HUMAN_CONFIRMATION',canConfirm=true,width=1440,hasReceipt=true){
 Object.defineProperty(window,'innerWidth',{value:width,configurable:true});
 let evidence=kind;let human=null;
 api.defaults.adapter=async c=>{calls.push(c);if(c.url.endsWith('destinations'))return{config:c,status:200,headers:{},data:{destinations}};
  if(c.url.endsWith('confirm-physical')){const p=JSON.parse(c.data);assert.equal(Object.keys(p).includes('confirmed_by'),false);human={confirmed:p.confirmed,actor_id:42,at:'2026-10-21T19:00:00Z'};evidence=p.confirmed?'HUMAN_CONFIRMED_PRINTED':'UNKNOWN_AFTER_SPOOL';canConfirm=false}
  return{config:c,status:200,headers:{},data:{job_id:jobId,status:evidence==='OS_REPORTED_PRINTED'||evidence==='HUMAN_CONFIRMED_PRINTED'?'printed':evidence==='UNKNOWN_AFTER_SPOOL'?'unknown':'submitted',execution_mode:'physical_qa',copies:1,origin_type:'WEB_DESKTOP',printer_name:'QA Printer',can_confirm_physical:canConfirm,physical_evidence:{kind:evidence,confirmation:human},result:hasReceipt?{outcome:'submitted',synthetic_spooler_id:123,error_code:null}:null}}};
 await act(async()=>root.render(h(Action,{origin:'WEB_DESKTOP',official:true})));await click('Imprimir');
 await change(document.querySelector('input[placeholder="UUID del trabajo"]'),jobId);await click('Consultar estado');
}
for(const width of[1440,390,820])for(const yes of[true,false])test(`human ${yes?'YES':'NO'} at ${width}px updates evidence without creating/printing another job`,async()=>{
 await physicalStatus('AWAITING_HUMAN_CONFIRMATION',true,width);assert.match(document.body.textContent,/Enviado a la impresora · confirmar resultado/);
 assert.doesNotMatch(document.body.textContent,/simulado|spooler fake/);await click('Confirmar impresión');assert.ok(button('Guardar confirmación').disabled);
 await click(yes?'Sí, salió correctamente':'No salió / hubo un problema');await click('Guardar confirmación');
 assert.match(document.body.textContent,yes?/Impresión confirmada/:/Resultado de impresión incierto/);assert.equal(button('Confirmar impresión'),undefined);
 assert.equal(calls.filter(c=>c.method==='post'&&c.url==='/print-routing').length,0);
 assert.equal(calls.filter(c=>c.url.endsWith('confirm-physical')).length,1);
});
test('OS completed has no human action and no fake label',async()=>{await physicalStatus('OS_REPORTED_PRINTED',false);assert.match(document.body.textContent,/Impresión completada/);assert.equal(button('Confirmar impresión'),undefined)});
test('physical no permission and absent receipt never expose confirmation',async()=>{await physicalStatus('AWAITING_HUMAN_CONFIRMATION',false);assert.equal(button('Confirmar impresión'),undefined)});
test('even inconsistent can-confirm cannot bypass missing receipt in UI',async()=>{await physicalStatus('AWAITING_HUMAN_CONFIRMATION',true,390,false);assert.equal(button('Confirmar impresión'),undefined)});
test('SafeValidation completion stays explicitly nonphysical',async()=>{
 state='printed';const adapter=api.defaults.adapter;api.defaults.adapter=async c=>{const r=await adapter(c);if(!c.url.endsWith('destinations'))r.data.execution_mode='safe_validation';return r};
 await act(async()=>root.render(h(Action,{origin:'WEB_DESKTOP',official:true})));await click('Imprimir');await select();await click('Validar sin imprimir');
 assert.match(document.body.textContent,/Validación completada \(sin impresión física\)/);assert.equal(button('Confirmar impresión'),undefined);
});
