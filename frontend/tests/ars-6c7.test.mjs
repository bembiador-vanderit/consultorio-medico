import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';
const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: ArsFinance } = await server.ssrLoadModule('/src/components/ArsFinance.tsx');
const { api } = await server.ssrLoadModule('/src/services/api.ts');
const original = api.defaults.adapter;
const user = { id: 1, roles: ['admin'], permissions: ['ars:read','ars:claim','ars:send','ars:glosa','ars:payment','ars:reconcile','ars:report'] };
const claim = { id: 9, center_id: 1, patient_id: 7, appointment_id: 12, patient_name: 'Paciente sintético', insurance_company_id: 2, service_date: '2026-09-01', state: 'received', display_state: 'received', claimed_amount: '1000', approved_amount: null, disputed_amount: '0', paid_amount: '0', balance: '1000', snapshot: { insurance: { company_name: 'ARS sintética', plan_name: 'Plan A' }, service: 'Consulta', authorization_status: 'authorized', authorization_number: 'AUTH-1' }, events: [], applications: [] };
const remittance = { id: 3, center_id: 1, insurance_company_id: 2, company_name: 'ARS sintética', received_on: '2026-09-10', reference: 'R-1', amount: '700', applied_amount: '0', unapplied: '700', applications: [] };
const response = (config, data) => ({ config, data, status: 200, statusText: 'OK', headers: {} });
let root, calls;
beforeEach(() => {
  root = createRoot(document.getElementById('root')); calls = [];
  api.defaults.adapter = async config => {
    calls.push(config);
    const url = config.url;
    const data = config.method === 'post' ? {} : url === '/ars/companies' ? [{ id: 2, name: 'ARS sintética' }]
      : url === '/ars/claims' || url === '/ars/receivables' ? [claim]
      : url === '/ars/remittances' ? [remittance]
      : url === '/ars/reconciliation' ? [{ insurance_company_id: 2, company_name: 'ARS sintética', claims: 1, claimed: '1000', approved: '0', collectible: '1000', disputed: '0', paid: '0', pending: '1000', aging: { '0-30': '1000' } }]
      : url === '/ars/claims/9' ? claim : url === '/ars/remittances/3' ? remittance
      : url === '/ars/eligible-appointments' ? [{ id: 12, date: '2026-09-01', patient_name: 'Paciente sintético', coverage_revision: 4, ars_amount: '1000' }] : [];
    return response(config, data);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = original; });
after(async () => { await server.close(); dom.window.close(); });
const button = text => [...document.querySelectorAll('button')].find(b => b.textContent === text);
const field = text => { const label = [...document.querySelectorAll('label')].find(l => l.textContent.startsWith(text)); assert.ok(label, text); return document.getElementById(label.htmlFor); };
async function click(text) { const b = button(text); assert.ok(b, text); await act(async () => b.click()); }
async function change(label, value) { const el = field(label); await act(async () => { Object.getOwnPropertyDescriptor(el.tagName === 'SELECT' ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype, 'value').set.call(el, value); el.dispatchEvent(new dom.window.Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); }); }
async function mount(section) { await act(async () => root.render(h(ArsFinance, { section, centerId: 1, user }))); }

test('claim screen shows historical authorization, amounts and status history', async () => {
  await mount(0);
  assert.match(document.body.textContent, /Reclamaciones ARS/);
  assert.match(document.body.textContent, /Paciente sintético/);
  await click('Detalle');
  assert.match(document.body.textContent, /AUTH-1/);
  assert.match(document.body.textContent, /Pendiente/);
});

test('claim creation uses selected coverage revision', async () => {
  await mount(0);
  await change('Buscar paciente', 'Paciente');
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 300)); });
  await change('Cita asegurada', '12');
  await click('Crear reclamación');
  const posted = calls.find(c => c.method === 'post');
  assert.equal(posted.url, '/ars/claims');
  assert.deepEqual(JSON.parse(posted.data), { appointment_id: 12, coverage_revision: 4 });
});

test('remittance distributes an explicit amount to a claim', async () => {
  await mount(1);
  await click('Detalle');
  await change('#9 · Paciente sintético', '500');
  assert.match(document.body.textContent, /500/);
  await click('Aplicar importes');
  const posted = calls.find(c => c.method === 'post');
  assert.equal(posted.url, '/ars/remittances/3/apply');
  assert.deepEqual(JSON.parse(posted.data), { allocations: [{ claim_id: 9, amount: '500' }] });
});

test('receivables and reconciliation show aging and ARS totals', async () => {
  await mount(2); assert.match(document.body.textContent, /Cuentas por cobrar ARS/);
  await mount(3); assert.match(document.body.textContent, /Conciliación por ARS/);
  assert.match(document.body.textContent, /0-30/);
});
