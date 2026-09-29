import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Platform } = await server.ssrLoadModule("/src/pages/Platform.tsx");
const { Topbar } = await server.ssrLoadModule("/src/layouts/AtlasAppShell.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const original = api.defaults.adapter;
let root;

beforeEach(() => { root = createRoot(document.getElementById("root")); });
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = original; });
after(async () => { await server.close(); dom.window.close(); });

test("platform view reads only the platform organization endpoint", async () => {
  const calls = [];
  api.defaults.adapter = async config => {
    calls.push(config.url);
    return { config, data: [{ id: 1, name: "Pilot", is_active: true }], status: 200, statusText: "OK", headers: {} };
  };
  await act(async () => root.render(h(Platform, { user: { full_name: "Operator", roles: [], access_scope: "platform" }, onSignOut: () => {} })));
  assert.deepEqual(calls, ["/platform/organizations"]);
  assert.match(document.body.textContent, /Plataforma Atlas/);
  assert.match(document.body.textContent, /Pilot/);
  assert.doesNotMatch(document.body.textContent, /Pacientes|Agenda|Consulta/);
});

test("tenant topbar shows the organization context beside the current page", async () => {
  await act(async () => root.render(h(Topbar, {
    pageTitle: "Inicio", user: { full_name: "Doctor", roles: ["doctor"], organization: { id: 2, name: "Tenant Dos" } },
    onOpenMenu: () => {}, onSignOut: () => {}, menuOpen: false,
  })));
  assert.match(document.querySelector("header").textContent, /Tenant Dos/);
});
