import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
globalThis.CustomEvent = dom.window.CustomEvent;
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { AxiosError } = await import("axios");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: AccessSchedules } = await server.ssrLoadModule("/src/components/AccessSchedules.tsx");
const { default: ReauthenticationDialog } = await server.ssrLoadModule("/src/components/ReauthenticationDialog.tsx");
const { default: Login } = await server.ssrLoadModule("/src/pages/Login.tsx");
const { api, setAccessToken } = await server.ssrLoadModule("/src/services/api.ts");
const { loginErrorMessage } = await server.ssrLoadModule("/src/services/login.ts");
const original = api.defaults.adapter;
const initial = { timezone: "America/Santo_Domingo", restrict_outside_schedule: false, weekly_schedule: [], allowed: true,
  current_until: null, next_window: { starts_at: "2030-01-07T12:00:00Z", ends_at: "2030-01-07T21:00:00Z" }, exceptions: [], blocked_dates: [] };
let root, calls;
beforeEach(() => { root = createRoot(document.getElementById("root")); calls = []; });
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = original; setAccessToken(null); });
after(async () => { await server.close(); dom.window.close(); });
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = text => [...document.querySelectorAll("button")].find(item => item.textContent === text);
async function change(element, value) {
  await act(async () => {
    const prototype = element.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(element, value);
    element.dispatchEvent(new dom.window.Event(element.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
}
async function mount(data = initial) {
  api.defaults.adapter = async config => { calls.push(config); return response(config, data); };
  await act(async () => root.render(h(AccessSchedules, { users: [{ id: 12, full_name: "Secretaria de prueba" }] })));
  await change(document.querySelector("select"), "12");
}

test("schedule selection stays opt-in and displays tenant timezone and next window", async () => {
  await mount();
  assert.equal(calls[0].url, "/administration/access-schedules/12");
  assert.equal(document.querySelector('input[type="checkbox"]').checked, false);
  assert.match(document.body.textContent, /Acceso sin restricción/);
  assert.match(document.body.textContent, /America\/Santo_Domingo/);
  assert.match(document.body.textContent, /Próxima ventana/);
  assert.match(document.body.textContent, /8:00/);
  assert.equal(document.querySelectorAll('input[type="time"]').length, 0);
});

test("weekly windows and opt-in policy are sent only for the selected user", async () => {
  await mount();
  await act(async () => button("Añadir ventana Lunes").click());
  await act(async () => document.querySelector('input[type="checkbox"]').click());
  await act(async () => button("Guardar horario").click());
  const saved = calls.find(config => config.method === "put");
  assert.equal(saved.url, "/administration/access-schedules/12");
  assert.deepEqual(JSON.parse(saved.data), { restrict_outside_schedule: true, weekly_schedule: [{ day: 0, start: "08:00", end: "17:00" }] });
  assert.match(document.body.textContent, /Cambio guardado/);
});

test("exceptions use tenant wall times and require a reason without changing the week", async () => {
  await mount();
  const inputs = document.querySelectorAll('input[type="datetime-local"]');
  await change(inputs[0], "2030-01-07T18:00");
  await change(inputs[1], "2030-01-07T20:00");
  const reason = [...document.querySelectorAll("label")].find(label => label.textContent.includes("Motivo de horas extra")).querySelector("input");
  assert.equal(reason.required, true);
  await change(reason, "Cierre administrativo");
  await act(async () => button("Autorizar excepción").click());
  const saved = calls.find(config => config.method === "post");
  assert.equal(saved.url, "/administration/access-schedules/12/exceptions");
  assert.deepEqual(JSON.parse(saved.data), { starts_at: "2030-01-07T18:00", ends_at: "2030-01-07T20:00", reason: "Cierre administrativo" });
});

test("blocked dates show author and can be removed through the protected endpoint", async () => {
  await mount({ ...initial, blocked_dates: [{ id: 4, day: "2030-01-07", reason: "Licencia", authorized_by: 12 }] });
  assert.match(document.body.textContent, /Licencia · Autorizó: Secretaria de prueba/);
  await act(async () => button("Retirar bloqueo 4").click());
  assert.equal(calls.at(-1).method, "delete");
  assert.equal(calls.at(-1).url, "/administration/access-schedules/12/blocked-dates/4");
});

test("schedule mutations reuse the one-operation reauthentication challenge", async () => {
  await mount();
  await act(async () => root.render(h("div", null, h(ReauthenticationDialog), h(AccessSchedules, { users: [{ id: 12, full_name: "Secretaria" }] }))));
  await change(document.querySelector("select"), "12");
  api.defaults.adapter = async config => {
    calls.push(config);
    if (config.url === "/administration/reauthenticate") return response(config, { proof: "test-proof" });
    if (!config.headers.get("X-Reauthentication")) throw new AxiosError("Confirmar", "ERR_BAD_RESPONSE", config, undefined, { status: 428 });
    return response(config, initial);
  };
  await act(async () => { button("Guardar horario").click(); await new Promise(resolve => setTimeout(resolve, 0)); });
  await change(document.querySelector('input[type="password"]'), "SyntheticPassword123");
  await act(async () => { button("Confirmar").click(); await new Promise(resolve => setTimeout(resolve, 0)); });
  const proof = calls.find(config => config.url === "/administration/reauthenticate");
  assert.equal(JSON.parse(proof.data).path, "/api/v1/administration/access-schedules/12");
  assert.equal(calls.at(-1).headers.get("X-Reauthentication"), "test-proof");
});

test("out-of-hours login preserves the human message and next access time", async () => {
  const message = "No tiene acceso fuera de su horario autorizado. Próximo acceso: 08:00 (America/Santo_Domingo).";
  const error = new AxiosError("denied", "ERR_BAD_RESPONSE", undefined, undefined,
    { status: 403, data: { detail: message }, headers: { "x-access-schedule": "denied" } });
  assert.equal(loginErrorMessage(error), message);
  await act(async () => root.render(h(Login, { onSignIn: async () => {}, sessionMessage: message })));
  assert.match(document.querySelector('[role="alert"]').textContent, /Próximo acceso: 08:00/);
});

test("an active session is cleared when a protected request is denied by schedule", async () => {
  let detail;
  const handler = event => { detail = event.detail; };
  window.addEventListener("atlas-session-expired", handler);
  setAccessToken("synthetic");
  api.defaults.adapter = async config => { throw new AxiosError("denied", "ERR_BAD_RESPONSE", config, undefined,
    { status: 403, data: { detail: "Su jornada terminó" }, headers: { "x-access-schedule": "denied" } }); };
  await assert.rejects(api.get("/auth/me"));
  assert.equal(api.defaults.headers.common.Authorization, undefined);
  assert.equal(detail, "Su jornada terminó");
  window.removeEventListener("atlas-session-expired", handler);
});

test("browser closes the session at its shift lease without waiting for a request", async () => {
  let count = 0;
  const handler = () => count++;
  window.addEventListener("atlas-session-expired", handler);
  const payload = btoa(JSON.stringify({ schedule_until: (Date.now() + 40) / 1000 }));
  setAccessToken(`header.${payload}.signature`);
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(count, 1);
  assert.equal(api.defaults.headers.common.Authorization, undefined);
  window.removeEventListener("atlas-session-expired", handler);
});
