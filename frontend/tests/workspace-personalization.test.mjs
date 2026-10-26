import { after, afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { createBrowser } from './browser.mjs';

const { dom } = createBrowser();
const { createElement: h, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { default: WorkspacePersonalization } = await server.ssrLoadModule('/src/pages/WorkspacePersonalization.tsx');
const { getDefaultGestionOrder, getNavigationItems, normalizeGestionOrder } = await server.ssrLoadModule('/src/navigation/navigation.ts');
const { getDashboardWidgets, getDefaultDashboardWidgetOrder, normalizeDashboardWidgetOrder } = await server.ssrLoadModule('/src/components/dashboard/dashboardModel.ts');
const rootHost = document.getElementById('root');
const user = { roles: ['secretary'], permissions: ['patients:access', 'patients:view', 'finance:read', 'finance:collect'] };
let root;
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; });
after(async () => { await server.close(); dom.window.close(); });

function navigationItems(forUser = user) { return getNavigationItems(forUser).filter(item => item.group === 'general'); }
function button(label) { return [...rootHost.querySelectorAll('button')].find(item => item.getAttribute('aria-label') === label || item.textContent.trim() === label); }
async function mount(props = {}) {
  root = createRoot(rootHost);
  await act(async () => root.render(h(WorkspacePersonalization, {
    modules: navigationItems(), gestionOrder: getDefaultGestionOrder(), onGestionOrderChange() {}, onResetGestionOrder() {},
    dashboardWidgets: getDashboardWidgets(user), dashboardOrder: getDefaultDashboardWidgetOrder(), onDashboardOrderChange() {}, onResetDashboard() {},
    accentTheme: 'classic', onAccentThemeChange() {}, onResetAll() {}, onSave() {}, loading: false, saving: false, error: '', saved: false, ...props,
  })));
}

test('personalization exposes only authorized Gestão modules and normalizes old/new preferences', () => {
  const visible = navigationItems();
  assert.deepEqual(visible.map(item => item.id), ['dashboard', 'appointments', 'reports', 'patients', 'finance']);
  assert.deepEqual(normalizeGestionOrder(visible, ['patients', 'finance', 'removed-module', 'patients']), ['patients', 'finance', 'dashboard', 'appointments', 'reports']);
  const futureModule = { ...visible[0], id: 'future-module', label: 'Módulo futuro', order: 45 };
  assert.deepEqual(normalizeGestionOrder([...visible, futureModule], ['patients']), ['patients', 'dashboard', 'appointments', 'reports', 'future-module', 'finance']);
  const noFinance = navigationItems({ roles: ['secretary'], permissions: ['patients:access', 'patients:view'] });
  assert.ok(!noFinance.some(item => item.id === 'finance'));
  assert.ok(!normalizeGestionOrder(noFinance, ['finance']).includes('finance'));
});

test('accessible move/reset controls change only the Gestión order by stable IDs', async () => {
  let changed;
  let reset = false;
  await mount({
    onGestionOrderChange(order) { changed = order; },
    onResetGestionOrder() { reset = true; },
  });
  assert.equal(rootHost.querySelector('[aria-label="Orden actual de módulos de Gestión"]').children.length, 5);
  const raisePatients = button('Subir Pacientes');
  assert.equal(raisePatients.type, 'button');
  await act(async () => raisePatients.click());
  assert.equal(changed[2], 'patients');
  await act(async () => button('Restablecer orden predeterminado').click());
  assert.equal(reset, true);
  assert.deepEqual(getDefaultGestionOrder(), ['dashboard', 'appointments', 'reports', 'patients', 'finance']);
  assert.equal(button('Subir Dashboard').disabled, true);
});

test('accent selector names and announces selection; semantic colors stay independent', async () => {
  let selected;
  await mount({ onAccentThemeChange(theme) { selected = theme; } });
  const classic = [...rootHost.querySelectorAll('.workspace-accent-option')].find(item => item.textContent.includes('Atlas clásico'));
  assert.equal(classic.getAttribute('aria-pressed'), 'true');
  const violet = [...rootHost.querySelectorAll('.workspace-accent-option')].find(item => item.textContent.includes('Violeta'));
  assert.equal(violet.type, 'button');
  await act(async () => violet.click());
  assert.equal(selected, 'violet');
  assert.match(rootHost.querySelector('.workspace-theme-preview').getAttribute('aria-label'), /Atlas clásico/);
  const tokens = await readFile(new URL('../src/ui/tokens.css', import.meta.url), 'utf8');
  const themeRules = tokens.split('\n').filter(line => line.startsWith('.atlas-shell[data-atlas-accent='));
  assert.equal(themeRules.length, 5);
  assert.ok(themeRules.every(line => !/--atlas-(success|warning|danger|info):/.test(line)));
  assert.match(tokens, /--atlas-success: #285D49/);
  assert.match(tokens, /--atlas-warning: #725013/);
  assert.match(tokens, /--atlas-danger: #963D38/);
});

test('Dashboard order uses real IDs, filters permissions and appends future visible widgets', async () => {
  const widgets = getDashboardWidgets(user);
  const ids = widgets.map(widget => widget.id);
  assert.ok(ids.includes('patients') && ids.includes('metric-appointments') && ids.includes('agenda-today'));
  assert.ok(!ids.includes('users') && !ids.includes('metric-users'));
  assert.deepEqual(normalizeDashboardWidgetOrder(ids, ['patients', 'removed-widget', 'patients']).slice(0, 2), ['patients', ids[0]]);
  assert.equal(normalizeDashboardWidgetOrder([...ids, 'future-widget'], ids).at(-1), 'future-widget');
  let changed, reset = false;
  await mount({ dashboardWidgets: widgets, onDashboardOrderChange(order) { changed = order; }, onResetDashboard() { reset = true; } });
  const group = rootHost.querySelector('[aria-label="Orden de Acciones rápidas"]');
  assert.ok(group.querySelector('[data-dashboard-widget-id="patients"]'));
  await act(async () => group.querySelector('[aria-label="Subir Pacientes"]').click());
  assert.equal(changed.indexOf('patients'), changed.indexOf('new-appointment') - 1);
  await act(async () => button('Restablecer Dashboard').click());
  assert.equal(reset, true);
});

test('save, reset all, load and error states are explicit without session-only copy', async () => {
  let saved = 0, reset = 0, accent = '';
  await mount({ onSave() { saved++; }, onResetAll() { reset++; }, onAccentThemeChange(theme) { accent = theme; }, error: 'No fue posible guardar' });
  assert.equal(rootHost.querySelector('[role="alert"]').textContent, 'No fue posible guardar');
  assert.doesNotMatch(rootHost.textContent, /solo durante la sesión/);
  await act(async () => button('Guardar preferencias').click());
  assert.equal(saved, 1);
  await act(async () => button('Restablecer todo').click());
  assert.equal(reset, 1);
  await act(async () => button('Restablecer apariencia').click());
  assert.equal(accent, 'classic');
  await act(async () => root.render(h(WorkspacePersonalization, { modules: navigationItems(), gestionOrder: getDefaultGestionOrder(), onGestionOrderChange() {}, onResetGestionOrder() {}, dashboardWidgets: getDashboardWidgets(user), dashboardOrder: getDefaultDashboardWidgetOrder(), onDashboardOrderChange() {}, onResetDashboard() {}, accentTheme: 'classic', onAccentThemeChange() {}, onResetAll() {}, onSave() {}, loading: true, saving: false, error: '', saved: false })));
  assert.ok(rootHost.querySelector('[role="status"]'));
  assert.equal(button('Guardar preferencias').disabled, true);
});

test('active product surfaces use Atlas Pérgamo and omit the retired brand', async () => {
  const files = [
    '../index.html', '../src/layouts/LoginLayout.tsx', '../src/layouts/AtlasAppShell.tsx',
    '../src/pages/Login.tsx', '../src/pages/DocumentPersonalization.tsx', '../src/dev/FoundationPreview.tsx',
  ];
  const contents = await Promise.all(files.map(path => readFile(new URL(path, import.meta.url), 'utf8')));
  const activeSurfaces = contents.join('\n');
  assert.match(activeSurfaces, /Atlas Pérgamo/);
  assert.doesNotMatch(activeSurfaces, /Atlas Consultorio/);
  assert.match(contents[0], /<title>Atlas Pérgamo<\/title>/);
});
