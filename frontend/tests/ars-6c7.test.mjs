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
  assert.match(JSON.parse(posted.data).request_key, /^[0-9a-f-]{36}$/);
  assert.deepEqual(JSON.parse(posted.data).allocations, [{ claim_id: 9, amount: '500' }]);
});

test('lost response keeps immutable key and payload; deliberate next apply gets a new key', async () => {
  const adapter = api.defaults.adapter;
  let lost = true;
  const attempts = [];
  api.defaults.adapter = async config => {
    if (config.url.endsWith('/apply')) {
      attempts.push(JSON.parse(config.data));
      if (lost) { lost = false; throw new Error('Response lost after server commit'); }
    }
    return adapter(config);
  };
  await mount(1); await click('Detalle'); await change('#9 · Paciente sintético', '250');
  await click('Aplicar importes');
  assert.equal(field('#9 · Paciente sintético').disabled, true);
  assert.equal(button('Cerrar').disabled, true);
  await click('Reintentar aplicación');
  assert.deepEqual(attempts[0], attempts[1]);
  await change('#9 · Paciente sintético', '250'); await click('Aplicar importes');
  assert.notEqual(attempts[2].request_key, attempts[0].request_key);
});

test('pending double click sends only one request and retains key until settled', async () => {
  const adapter = api.defaults.adapter;
  let release;
  const attempts = [];
  api.defaults.adapter = async config => {
    if (config.url.endsWith('/apply')) {
      attempts.push(JSON.parse(config.data));
      await new Promise(resolve => { release = resolve; });
    }
    return adapter(config);
  };
  await mount(1); await click('Detalle'); await change('#9 · Paciente sintético', '250');
  const b = button('Aplicar importes');
  await act(async () => { b.click(); b.click(); });
  assert.equal(attempts.length, 1);
  assert.equal(button('Reintentar aplicación').disabled, true);
  await act(async () => release());
  assert.equal(button('Aplicar importes').disabled, true); // Cleared only on success.
});

test('409 is displayed and cannot silently replace the operation key', async () => {
  const adapter = api.defaults.adapter;
  const attempts = [];
  api.defaults.adapter = async config => {
    if (config.url.endsWith('/apply')) {
      attempts.push(JSON.parse(config.data));
      throw { response: { status: 409, data: { detail: 'La clave corresponde a otra intención' } } };
    }
    return adapter(config);
  };
  await mount(1); await click('Detalle'); await change('#9 · Paciente sintético', '250');
  await click('Aplicar importes');
  assert.match(document.body.textContent, /La clave corresponde a otra intención/);
  await click('Reintentar aplicación');
  assert.deepEqual(attempts[0], attempts[1]);
});

test('receivables and reconciliation show aging and ARS totals', async () => {
  await mount(2); assert.match(document.body.textContent, /Cuentas por cobrar ARS/);
  await mount(3); assert.match(document.body.textContent, /Conciliación por ARS/);
  assert.match(document.body.textContent, /0-30/);
});

function detailApplications() {
  const adapter = api.defaults.adapter;
  api.defaults.adapter = async config => {
    if (config.url === '/ars/remittances/3' && config.method !== 'post') {
      calls.push(config);
      return response(config, { ...remittance, applied_amount: '150', unapplied: '550', applications: [
        { id: 21, claim_id: 9, amount: '150', reversed_at: null, reversal_reason: null },
        { id: 22, claim_id: 9, amount: '25', reversed_at: '2026-09-11T12:00:00', reversal_reason: 'QA reverso' },
      ] });
    }
    return adapter(config);
  };
}

test('remittance detail separates totals, application history and compact allocation without writes', async () => {
  detailApplications();
  await mount(1); await click('Detalle');
  const totals = document.querySelector('.ars-remittance-totals');
  assert.deepEqual([...totals.querySelectorAll('dt')].map(x => x.textContent), ['Total recibido', 'Aplicado neto', 'Disponible para aplicar']);
  assert.deepEqual([...totals.querySelectorAll('dd')].map(x => x.textContent.replace(/\s/g, '')), ['RD$700.00', 'RD$150.00', 'RD$550.00']);
  assert.equal(document.querySelectorAll('.ars-applications-table tbody tr').length, 2);
  assert.equal(document.querySelectorAll('.ars-application-reversed').length, 1);
  assert.equal(document.querySelectorAll('.ars-remittance-reverse').length, 1);
  assert.equal(document.querySelector('.ars-remittance-reverse').getAttribute('aria-label'), 'Revertir aplicación #21');
  assert.match(document.querySelector('.ars-remittance-distribution').textContent, /Paciente sintético/);
  const input = field('#9 · Paciente sintético');
  assert.equal(input.max, '1000'); assert.equal(input.min, '0'); assert.equal(input.step, '0.01');
  assert.equal(input.inputMode, 'decimal');
  assert.equal(calls.filter(c => c.method === 'post').length, 0);
});

test('read-only ARS permission keeps history but hides allocation and reversal actions', async () => {
  detailApplications();
  await act(async () => root.render(h(ArsFinance, { section: 1, centerId: 1, user: { ...user, permissions: ['ars:read'] } })));
  await click('Detalle');
  assert.equal(document.querySelectorAll('.ars-applications-table tbody tr').length, 2);
  assert.equal(document.querySelector('.ars-remittance-distribution'), null);
  assert.equal(button('Revertir'), undefined);
  assert.equal(button('Registrar remesa'), undefined);
  assert.equal(calls.filter(c => c.method === 'post').length, 0);
});

test('redesigned reverse action preserves original endpoint, reason and cancel behavior', async () => {
  detailApplications();
  const previousPrompt = globalThis.prompt;
  try {
    globalThis.prompt = () => null;
    await mount(1); await click('Detalle'); await click('Revertir');
    assert.equal(calls.filter(c => c.method === 'post').length, 0);
    globalThis.prompt = () => 'QA motivo de reverso';
    await click('Revertir');
    const posts = calls.filter(c => c.method === 'post');
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, '/ars/applications/21/reverse');
    assert.deepEqual(JSON.parse(posts[0].data), { reason: 'QA motivo de reverso' });
  } finally {
    if (previousPrompt === undefined) delete globalThis.prompt;
    else globalThis.prompt = previousPrompt;
  }
});

test('empty remittance history and close remain non-mutating', async () => {
  await mount(1); await click('Detalle');
  assert.match(document.body.textContent, /Esta remesa todavía no tiene aplicaciones/);
  assert.equal(button('Aplicar importes').disabled, true);
  await change('#9 · Paciente sintético', '10');
  await click('Cerrar');
  assert.equal(document.querySelector('.ars-remittance-detail'), null);
  await click('Detalle');
  assert.equal(field('#9 · Paciente sintético').value, '');
  assert.equal(calls.filter(c => c.method === 'post').length, 0);
});
