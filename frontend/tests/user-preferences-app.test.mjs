import { after, afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';

const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: App } = await server.ssrLoadModule('/src/App.tsx');
const { api, setAccessToken } = await server.ssrLoadModule('/src/services/api.ts');
const { defaultUserPreferences } = await server.ssrLoadModule('/src/services/userPreferences.ts');
const originalAdapter = api.defaults.adapter;
const host = document.getElementById('root');
const users = [
  { id: 101, full_name: 'QA A', email: 'a@example.test', roles: ['secretary'], permissions: ['patients:access', 'patients:view', 'finance:read', 'finance:collect'], is_active: true },
  { id: 102, full_name: 'QA B', email: 'b@example.test', roles: ['secretary'], permissions: ['patients:access', 'patients:view'], is_active: true },
];
let root, activeUser, saved, requests, failSave;

beforeEach(() => {
  activeUser = users[0]; saved = new Map(); requests = []; failSave = false;
  setAccessToken(null);
  api.defaults.adapter = async config => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    let data;
    if (config.url === '/auth/refresh') data = { access_token: 'synthetic-token' };
    else if (config.url === '/auth/me') data = activeUser;
    else if (config.url === '/me/preferences' && config.method === 'get') data = saved.get(activeUser.id) ?? defaultUserPreferences();
    else if (config.url === '/me/preferences' && config.method === 'put') {
      if (failSave) throw new Error('No se pudo guardar');
      data = JSON.parse(config.data); saved.set(activeUser.id, data);
    } else if (config.url === '/patients/count') data = { count: 2 };
    else if (config.url === '/appointments') data = [];
    else if (config.url === '/follow-ups/notifications/sync') data = {};
    else if (config.url === '/follow-ups/notifications') data = [];
    else if (config.url === '/auth/logout') data = null;
    else data = [];
    return { data, status: 200, statusText: 'OK', headers: {}, config };
  };
});
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; api.defaults.adapter = originalAdapter; setAccessToken(null); });
after(async () => { await server.close(); dom.window.close(); });

async function mount() {
  root = createRoot(host);
  await act(async () => { root.render(h(App)); await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
}
function button(text, scope = host) { return [...scope.querySelectorAll('button')].find(item => item.textContent.trim() === text || item.getAttribute('aria-label') === text); }
async function click(target) { assert.ok(target); await act(async () => target.click()); }
function actionIds() { return [...host.querySelectorAll('.dashboard-actions-grid [data-dashboard-action]')].map(item => item.dataset.dashboardAction); }
function navIds() { return [...host.querySelectorAll('.atlas-sidebar .atlas-navigation [aria-current], .atlas-sidebar .atlas-navigation button')].filter(item => item.closest('.atlas-navigation-finance-panel') === null).map(item => item.textContent.trim()); }

test('GET applies saved menu, Dashboard and accent; PUT survives a fresh session', async () => {
  saved.set(101, { gestion_menu_order: ['patients', 'appointments', 'dashboard', 'reports', 'finance'],
    dashboard_widget_order: ['patients', 'agenda', 'reports', 'new-appointment'], accent_theme: 'turquoise' });
  await mount();
  assert.equal(requests.filter(item => item.url === '/me/preferences' && item.method === 'get').length, 1);
  assert.equal(host.querySelector('.atlas-shell').getAttribute('data-atlas-accent'), 'turquoise');
  assert.deepEqual(actionIds().slice(0, 3), ['patients', 'agenda', 'reports']);
  assert.ok(navIds().indexOf('Pacientes') < navIds().indexOf('Agenda'));
  await click(button('Personalización', host.querySelector('.atlas-sidebar')));
  const menu = host.querySelector('[aria-label="Orden actual de módulos de Gestión"]');
  await click(menu.querySelector('[aria-label="Subir Agenda"]'));
  await click(host.querySelector('[data-accent-option="indigo"]'));
  assert.equal(host.querySelector('.atlas-shell').getAttribute('data-atlas-accent'), 'indigo');
  await click(button('Guardar preferencias'));
  assert.equal(requests.filter(item => item.url === '/me/preferences' && item.method === 'put').length, 1);
  assert.equal(saved.get(101).accent_theme, 'indigo');
  assert.deepEqual(saved.get(101).gestion_menu_order.slice(0, 2), ['appointments', 'patients']);
  await act(async () => root.unmount()); root = null;
  await mount();
  assert.equal(host.querySelector('.atlas-shell').getAttribute('data-atlas-accent'), 'indigo');
  assert.ok(navIds().indexOf('Agenda') < navIds().indexOf('Pacientes'));
});

test('independent user starts with defaults and cannot inherit another user preferences', async () => {
  saved.set(101, { gestion_menu_order: ['patients'], dashboard_widget_order: ['patients'], accent_theme: 'violet' });
  await mount();
  assert.equal(host.querySelector('.atlas-shell').getAttribute('data-atlas-accent'), 'violet');
  await act(async () => root.unmount()); root = null;
  activeUser = users[1];
  await mount();
  assert.equal(host.querySelector('.atlas-shell').getAttribute('data-atlas-accent'), 'classic');
  assert.deepEqual(actionIds().slice(0, 2), ['new-appointment', 'patients']);
  assert.equal(saved.has(102), false);
  assert.ok(!host.textContent.includes('Usuarios activos'));
});

test('save error is visible and does not claim persistence', async () => {
  await mount();
  await click(button('Personalización', host.querySelector('.atlas-sidebar')));
  failSave = true;
  await click(button('Guardar preferencias'));
  assert.match(host.querySelector('[role="alert"]').textContent, /No fue posible guardar/);
  assert.equal(saved.has(activeUser.id), false);
});
