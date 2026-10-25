import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';

const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: PrintManagement } = await server.ssrLoadModule('/src/pages/PrintManagement.tsx');
const { api } = await server.ssrLoadModule('/src/services/api.ts');
const { getNavigationItems } = await server.ssrLoadModule('/src/navigation/navigation.ts');
const originalAdapter = api.defaults.adapter;
const user = { roles: ['admin'], permissions: ['local_agents:view'] };
const inventory = {
  organization: { id: 1, name: 'QA Organización' },
  centers: [{ id: 1, name: 'QA Centro' }],
  agents: [
    { id: 1, station_name: 'QA Estación A', agent_uuid: '00000000-0000-0000-0000-000000000001', center_id: 1, status: 'online', last_seen_at: '2026-10-23T12:00:00Z', printers: [] },
    { id: 2, station_name: 'QA Estación B', agent_uuid: '00000000-0000-0000-0000-000000000002', center_id: 1, status: 'offline', last_seen_at: '2026-10-22T12:00:00Z', printers: [
      { id: 12, local_id: 'printer-local-12', display_name: 'QA Impresora local', driver: 'QA Driver', connection: 'Local', available: true, is_virtual: false, last_seen_at: '2026-10-23T11:00:00Z' },
      { id: 17, local_id: 'printer-network-17', display_name: 'QA Impresora histórica', driver: 'QA Network', connection: 'Network', available: false, is_virtual: false, last_seen_at: '2026-10-20T11:00:00Z' },
    ] },
  ],
};
let root;
let data;
let calls;
let fail;
beforeEach(() => {
  root = createRoot(document.getElementById('root'));
  data = structuredClone(inventory);
  calls = [];
  fail = false;
  api.defaults.adapter = async (config) => {
    calls.push(config);
    if (fail) throw new Error('QA backend error');
    return { config, data, status: 200, statusText: 'OK', headers: {} };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });
async function mount(who = user) { await act(async () => root.render(h(PrintManagement, { user: who }))); }
function stationToggle(name) {
  const button = [...document.querySelectorAll('.print-management-station')].find((item) => item.textContent.includes(name));
  assert.ok(button, name);
  return button;
}
async function selectStation(name) {
  const button = stationToggle(name);
  await act(async () => button.click());
}
async function refresh() {
  const button = [...document.querySelectorAll('button')].find((item) => item.textContent === 'Actualizar inventario');
  assert.ok(button);
  await act(async () => button.click());
}

test('authorized navigation and station list use the scoped read endpoint only', async () => {
  assert.ok(getNavigationItems(user).some((item) => item.view === 'print-management' && item.label === 'Gestión de impresión'));
  await mount();
  assert.match(document.body.textContent, /QA Organización/);
  assert.match(document.body.textContent, /QA Estación A/);
  assert.match(document.body.textContent, /QA Estación B/);
  assert.match(document.body.textContent, /Conectada/);
  assert.match(document.body.textContent, /Desconectada/);
  assert.match(document.body.textContent, /1 impresora disponible/);
  assert.doesNotMatch(document.body.textContent, /históricas en total/);
  for (const button of document.querySelectorAll('.print-management-station')) {
    assert.equal(button.getAttribute('aria-expanded'), 'false');
    assert.ok(document.getElementById(button.getAttribute('aria-controls')).hidden);
    assert.match(button.textContent, /Ver impresoras/);
  }
  assert.equal(document.querySelectorAll('.print-management-printer').length, 0);
  assert.deepEqual(calls.map((call) => [call.method, call.url]), [['get', '/local-agents/registry']]);
});

test('station accordion opens and closes with accessible controls, showing available printers only', async () => {
  await mount();
  const button = stationToggle('QA Estación B');
  const panelId = button.getAttribute('aria-controls');
  assert.ok(panelId);
  assert.equal(button.tagName, 'BUTTON');
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  assert.ok(document.getElementById(panelId).hidden);
  await selectStation('QA Estación B');
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.match(button.textContent, /Ocultar impresoras/);
  const detail = document.getElementById(panelId);
  assert.equal(detail.hidden, false);
  assert.match(detail.textContent, /QA Impresora local/);
  assert.doesNotMatch(detail.textContent, /QA Impresora histórica/);
  assert.match(detail.textContent, /Disponible/);
  assert.doesNotMatch(detail.textContent, /No disponible/);
  assert.doesNotMatch(detail.textContent, /históricas en total/);
  assert.match(detail.textContent, /1 impresora disponible/);
  assert.match(detail.textContent, /La estación no está conectada normalmente/);
  assert.equal(detail.querySelectorAll('.print-management-printer').length, 1);
  assert.equal(detail.querySelectorAll('input, select, textarea').length, 0);
  assert.match(detail.querySelector('details').textContent, /00000000-0000-0000-0000-000000000002/);
  await selectStation('QA Estación B');
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  assert.equal(detail.hidden, true);
  assert.match(button.textContent, /Ver impresoras/);
  assert.deepEqual(calls.map((call) => call.method), ['get']);
});

test('empty stations, no printers, and unavailable-only inventory have distinct messages', async () => {
  await mount();
  await selectStation('QA Estación A');
  assert.match(document.querySelector('.print-management-station-panel:not([hidden])').textContent, /todavía no ha sincronizado impresoras/);
  data.agents[0].printers = [data.agents[1].printers[1]];
  await refresh();
  assert.match(document.querySelector('.print-management-station-panel:not([hidden])').textContent, /No hay impresoras disponibles/);
  assert.doesNotMatch(document.querySelector('.print-management-station-panel:not([hidden])').textContent, /QA Impresora histórica/);
  data.agents = [];
  await refresh();
  assert.match(document.body.textContent, /Sin estaciones/);
});

test('operational counts show station B 6 and station A 10 without exposing retired printers', async () => {
  data.agents = [
    { ...data.agents[0], station_name: 'Estación A', printers: Array.from({ length: 10 }, (_, index) => ({ ...inventory.agents[1].printers[0], id: index + 1, display_name: `QA disponible ${index + 1}` })) },
    { ...data.agents[1], station_name: 'Estación B', printers: [
      ...Array.from({ length: 6 }, (_, index) => ({ ...inventory.agents[1].printers[0], id: index + 20, display_name: index === 0 ? 'Impresora QA' : `QA local ${index}` })),
      { ...inventory.agents[1].printers[1], display_name: '\\QA-HOST\Impresora QA' },
    ] },
  ];
  await mount();
  assert.match(document.body.textContent, /10 impresoras disponibles/);
  assert.match(document.body.textContent, /6 impresoras disponibles/);
  assert.match(document.body.textContent, /16 impresoras disponibles/);
  assert.equal(document.querySelectorAll('.print-management-printer').length, 0);
  assert.equal(stationToggle('Estación B').getAttribute('aria-expanded'), 'false');
  assert.equal(stationToggle('Estación A').getAttribute('aria-expanded'), 'false');
  await selectStation('Estación B');
  let detail = document.querySelector('.print-management-station-panel:not([hidden])');
  assert.equal(detail.querySelectorAll('.print-management-printer').length, 6);
  assert.match(detail.textContent, /Impresora QA/);
  assert.doesNotMatch(detail.textContent, /QA-HOST/);
  assert.doesNotMatch(document.body.textContent, /7 históricas/);
  assert.equal(stationToggle('Estación B').getAttribute('aria-expanded'), 'true');
  assert.equal(stationToggle('Estación A').getAttribute('aria-expanded'), 'false');
  await selectStation('Estación A');
  assert.equal(stationToggle('Estación B').getAttribute('aria-expanded'), 'false');
  assert.equal(stationToggle('Estación A').getAttribute('aria-expanded'), 'true');
  detail = document.querySelector('.print-management-station-panel:not([hidden])');
  assert.equal(detail.querySelectorAll('.print-management-printer').length, 10);
  assert.match(detail.textContent, /10 impresoras disponibles/);
  assert.match(document.body.textContent, /6 impresoras disponibles/);
  assert.match(document.body.textContent, /10 impresoras disponibles/);
  assert.equal(calls.length, 1, 'opening and switching stations must not reload the registry');
  await selectStation('Estación A');
  assert.equal(stationToggle('Estación A').getAttribute('aria-expanded'), 'false');
  assert.equal(document.querySelectorAll('.print-management-station-panel:not([hidden])').length, 0);
});

test('history entry opens a clean placeholder without revealing printer registry history', async () => {
  await mount();
  await selectStation('QA Estación B');
  const button = [...document.querySelectorAll('button')].find((item) => item.textContent === 'Historial de impresión');
  assert.ok(button);
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  await act(async () => button.click());
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.match(document.querySelector('.print-management-history').textContent, /estará disponible en esta sección/);
  assert.doesNotMatch(document.querySelector('.print-management-station-panel:not([hidden])').textContent, /QA Impresora histórica/);
  assert.ok(calls.every((call) => call.method === 'get'));
});

test('loading error is friendly and refresh retains last inventory with stale-data notice', async () => {
  fail = true;
  await mount();
  assert.match(document.querySelector('[role="alert"]').textContent, /No pudimos cargar el inventario/);
  assert.doesNotMatch(document.body.textContent, /QA backend error/);
  fail = false;
  await refresh();
  assert.match(document.body.textContent, /QA Estación A/);
  fail = true;
  await refresh();
  assert.match(document.querySelector('[role="alert"]').textContent, /últimos datos cargados/);
});

test('permission gate makes no request and responsive layout has narrow breakpoints', async () => {
  assert.equal(getNavigationItems({ roles: ['admin'], permissions: [] }).some((item) => item.view === 'print-management'), false);
  await mount({ roles: ['admin'], permissions: [] });
  assert.equal(calls.length, 0);
  assert.match(document.body.textContent, /No tiene permiso/);
  const css = await readFile(new URL('../src/pages/printManagement.css', import.meta.url), 'utf8');
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /minmax\(0,1fr\)/);
  assert.match(css, /overflow-wrap:anywhere/);
});
