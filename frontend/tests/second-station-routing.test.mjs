import {after,afterEach,beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {createBrowser} from './browser.mjs';

const {dom}=createBrowser();
const {createElement:h,act}=await import('react');
const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {default:Action}=await server.ssrLoadModule('/src/components/FakePrintAction.tsx');
const {api}=await server.ssrLoadModule('/src/services/api.ts');
const original=api.defaults.adapter;
const first='10000000-0000-4000-8000-000000000001',second='10000000-0000-4000-8000-000000000002';
let root,calls;
beforeEach(()=>{
  root=createRoot(document.getElementById('root'));calls=[];
  api.defaults.adapter=async c=>{
    calls.push(c);
    const data=c.url.endsWith('/destinations')?{destinations:[
      {target_agent:first,target_printer:'printer-first-only',station_name:'QA Station One',printer_name:'QA First Only',online:false,available:true},
      {target_agent:second,target_printer:'printer-second-only',station_name:'QA Station Two',printer_name:'QA Second Only',online:true,available:true}
    ]}:{job_id:JSON.parse(c.data).job_id,status:'printed',copies:1,origin_type:JSON.parse(c.data).origin_type,execution_mode:'safe_validation',result:{outcome:'printed',synthetic_spooler_id:1234,error_code:null}};
    return {config:c,status:200,headers:{},data};
  };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=original;});
after(async()=>{await server.close();dom.window.close();});
async function change(el,value){await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('change',{bubbles:true}));});}

for(const [width,origin] of [[1440,'WEB_DESKTOP'],[390,'WEB_MOBILE'],[820,'WEB_TABLET']]) {
  test(`two-station selection at ${width}px resets printer and targets only second station`,async()=>{
    Object.defineProperty(window,'innerWidth',{value:width,configurable:true});
    await act(async()=>root.render(h(Action,{origin:'WEB_DESKTOP',official:true})));
    const findButton=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
    await act(async()=>findButton('Imprimir').click());
    let [station,printer]=document.querySelectorAll('dialog select');
    assert.match(station.textContent,/QA Station One/);assert.match(station.textContent,/QA Station Two/);
    await change(station,first);await change(printer,'printer-first-only');
    await change(station,second);
    [station,printer]=document.querySelectorAll('dialog select');
    assert.equal(printer.value,'');
    assert.doesNotMatch(printer.textContent,/QA First Only/);
    assert.match(printer.textContent,/QA Second Only/);
    assert.ok(findButton('Validar sin imprimir').disabled);
    await change(printer,'printer-second-only');
    await act(async()=>findButton('Validar sin imprimir').click());
    const submits=calls.filter(c=>c.method==='post');assert.equal(submits.length,1);
    const payload=JSON.parse(submits[0].data);
    assert.equal(submits[0].url,'/print-routing');assert.equal(payload.target_agent,second);
    assert.equal(payload.target_printer,'printer-second-only');assert.equal(payload.origin_type,origin);
    assert.equal(payload.source_agent,undefined);assert.equal(payload.copies,1);
    assert.match(document.body.textContent,/Validación completada \(sin impresión física\)/);
  });
}
