import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';
const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode:true, ws:false }, appType:'custom', optimizeDeps:{ noDiscovery:true, include:[] } });
const { default: Documents } = await server.ssrLoadModule('/src/pages/DocumentPersonalization.tsx');
const { api } = await server.ssrLoadModule('/src/services/api.ts');
const original = api.defaults.adapter;
const user = { id:1, roles:['admin'], permissions:['users:manage','finance:read','documents:view','documents:pdf','documents:print','documents:reprint','documents:manage','documents:publish'] };
let root, calls;
const response = (config,data) => ({ config,data,status:200,statusText:'OK',headers:{} });
beforeEach(() => {
  root=createRoot(document.getElementById('root')); calls=[];
  api.defaults.adapter=async config => {
    calls.push(config);
    if(config.url==='/finance/centers') return response(config,[{id:1,name:'CEMER'}]);
    if(config.url?.startsWith('/documents/effective/')) return response(config,{definition:{page_format:'LETTER',print_mode:'color',ink_saver:true},source:'atlas_default',version:null});
    if(config.url==='/documents/drafts') return response(config,{template_id:10,version_id:12,version:1,status:'draft'});
    if(config.url?.endsWith('/publish')) return response(config,{template_id:10,version_id:12,version:1,status:'published'});
    if(config.url==='/documents/preview/pdf') return response(config,new Blob(['%PDF'],{type:'application/pdf'}));
    return response(config,[]);
  };
});
afterEach(async()=>{await act(async()=>root.unmount());api.defaults.adapter=original;});
after(async()=>{await server.close();dom.window.close();});
const buttons=()=>[...document.querySelectorAll('button')];
const button=text=>buttons().find(b=>b.textContent.includes(text));
async function click(text){const target=button(text);assert.ok(target,text);await act(async()=>target.click());}
async function mount(){await act(async()=>root.render(h(Documents,{user})));}

test('one administration entry integrates normal personalization and advanced designer',async()=>{
  const {getNavigationItems}=await server.ssrLoadModule('/src/navigation/navigation.ts');
  const nav=getNavigationItems(user);
  assert.equal(nav.filter(x=>x.view==='documents').length,1);
  assert.equal(nav.some(x=>x.view==='clinical-forms'),false);
  await mount();assert.equal(document.querySelector('.doc-design-crumb')?.textContent,'Herramientas › Documentos');
  await click('Diseñador avanzado');assert.match(document.body.textContent,/Diseñador avanzado/);
  await click('Personalización normal');assert.match(document.body.textContent,/Vista previa del documento/);
});
test('three financial types and live color/BW compare without downloading',async()=>{
  await mount();
  assert.match(document.body.textContent,/Factura interna/);
  assert.equal(document.querySelectorAll('.doc-design-paper').length,2);
  assert.ok(document.querySelector('.doc-design-paper--bw'));
  await click('Recibo de pago');assert.match(document.querySelector('.doc-design-paper').textContent,/PAGO-00000001/);
  await click('Cierre de Caja');assert.match(document.querySelector('.doc-design-paper').textContent,/CAJA-00000001/);
  await click('Solo negro');assert.equal(button('Solo negro').getAttribute('aria-pressed'),'true');
  await click('Vista única');assert.equal(document.querySelectorAll('.doc-design-paper').length,1);
});
test('save draft then publish a distinct version with typed settings',async()=>{
  await mount();await click('Solo negro');await click('Guardar borrador');
  const saved=calls.find(c=>c.url==='/documents/drafts');assert.ok(saved);
  const payload=JSON.parse(saved.data);assert.equal(payload.document_type,'invoice');assert.equal(payload.definition.print_mode,'bw');
  assert.match(document.body.textContent,/Borrador v1 guardado/);
  await click('Publicar versión');assert.ok(calls.some(c=>c.url==='/documents/templates/10/versions/12/publish'));
});
test('mobile uses bounded stacked layout and accessible controls',async()=>{
  await mount();const css=await readFile(new URL('../src/pages/documentPersonalization.css',import.meta.url),'utf8');
  assert.match(css,/@media\(max-width:420px\)/);assert.match(css,/min-width:0/);
  for(const item of document.querySelectorAll('.doc-design-document-tiles button,.doc-design-choices button')) assert.ok(item.hasAttribute('aria-pressed'));
  assert.ok(document.querySelector('label select'));assert.ok(document.querySelector('label input[type=checkbox]'));
});
