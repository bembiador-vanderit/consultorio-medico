import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: ReauthenticationDialog } = await server.ssrLoadModule("/src/components/ReauthenticationDialog.tsx");
const { default: AdministrationSecurity } = await server.ssrLoadModule("/src/pages/AdministrationSecurity.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const { getNavigationItems } = await server.ssrLoadModule("/src/navigation/navigation.ts");
const original = api.defaults.adapter;
let root, calls;
beforeEach(() => { root = createRoot(document.getElementById("root")); calls = []; });
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = original; });
after(async () => { await server.close(); dom.window.close(); });
const button = text => [...document.querySelectorAll("button")].find(item => item.textContent === text);
function reject(config, status) { const error = new Error("HTTP error"); error.config = config; error.response = { status }; throw error; }
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
async function password(value) {
  const input = document.querySelector('input[type="password"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}

test("sensitive mutation waits for password, then retries once with the matching proof", async () => {
  api.defaults.adapter = async config => {
    calls.push({ url: config.url, method: config.method, data: config.data, proof: config.headers.get("X-Reauthentication") });
    if (config.url === "/administration/reauthenticate") return response(config, { proof: "synthetic-proof" });
    if (!config.headers.get("X-Reauthentication")) reject(config, 428);
    return response(config, { is_active: false });
  };
  await act(async () => root.render(h(ReauthenticationDialog)));
  let pending;
  await act(async () => { pending = api.put("/users/12/status", { is_active: false }); await new Promise(resolve => setTimeout(resolve, 0)); });
  assert.equal(calls.length, 1);
  assert.ok(document.querySelector("dialog[open]"));
  await password("SyntheticPassword123");
  await act(async () => { button("Confirmar").click(); await pending; });
  assert.equal(calls.length, 3);
  assert.deepEqual(JSON.parse(calls[1].data), { password: "SyntheticPassword123", method: "PUT", path: "/api/v1/users/12/status" });
  assert.equal(calls[2].proof, "synthetic-proof");
  assert.equal(document.querySelector('input[type="password"]'), null);
  assert.equal(window.localStorage.length, 0);
});

test("cancelling confirmation never repeats the mutation", async () => {
  api.defaults.adapter = async config => { calls.push(config.url); reject(config, 428); };
  await act(async () => root.render(h(ReauthenticationDialog)));
  let pending;
  await act(async () => { pending = api.put("/users/12/status", { is_active: false }).catch(error => error); await new Promise(resolve => setTimeout(resolve, 0)); });
  await act(async () => { button("Cancelar").click(); });
  assert.match((await pending).message, /cancelada/);
  assert.equal(calls.length, 1);
});

test("recipient can see pending acceptance without administrative controls", async () => {
  api.defaults.adapter = async config => response(config, [{ id: 9, initiator_id: 1, target_id: 2, replace_initiator: true, expires_at: "2026-09-23T10:00:00" }]);
  await act(async () => root.render(h(AdministrationSecurity, { user: { id: 2, roles: ["doctor"] } })));
  assert.ok(button("Aceptar administración"));
  assert.ok(button("Cancelar solicitud"));
  assert.equal(button("Solicitar confirmación"), undefined);
  assert.doesNotMatch(document.body.textContent, /Auditoría de seguridad/);
});

test("capability restrictions remove operational navigation without removing security", () => {
  const visible = getNavigationItems({ roles: ["doctor"], permissions: ["centers:access"] }).map(item => item.view);
  assert.deepEqual(visible, ["dashboard", "security"]);
});
