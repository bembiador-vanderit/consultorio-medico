import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { ProviderPauseCard } = await server.ssrLoadModule("/src/components/agenda/ProviderPauseCard.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = (text) => [...document.querySelectorAll("button")].find((item) => item.textContent === text);
let root;
let calls;
let current;

beforeEach(() => {
  root = createRoot(document.getElementById("root"));
  calls = [];
  current = null;
  api.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/provider-pauses/current") return response(config, current);
    if (config.method === "get" && config.url === "/provider-pauses") return response(config, current ? [current] : []);
    if (config.method === "post" && config.url === "/provider-pauses/start") {
      const payload = JSON.parse(config.data);
      current = { id: 7, organization_id: 1, doctor_id: 2, ...payload, actual_started_at: "2030-10-15T11:31:00", actual_finished_at: null, duration_seconds: null };
      return response(config, current);
    }
    if (config.method === "post" && config.url === "/provider-pauses/7/finish") {
      current = { ...current, actual_finished_at: "2030-10-15T11:45:00", duration_seconds: 840 };
      return response(config, current);
    }
    throw new Error(`Unexpected request: ${config.method} ${config.url}`);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });

test("el médico inicia pausa con motivo obligatorio y la finaliza sin enviar horas ni actor", async () => {
  await act(async () => root.render(h(ProviderPauseCard, { centerId: 1, doctorId: 2, doctorName: "Dr. Osiris", canManage: true, isAdmin: false })));
  assert.match(document.body.textContent, /DISPONIBLE/);
  await act(async () => button("Iniciar pausa").click());
  assert.equal(button("Guardar inicio").disabled, true);
  const select = document.querySelector("select");
  await act(async () => { select.value = "lunch"; select.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  assert.equal(button("Guardar inicio").disabled, false);
  await act(async () => button("Guardar inicio").click());
  const payload = JSON.parse(calls.find((call) => call.url === "/provider-pauses/start").data);
  assert.deepEqual(payload, { center_id: 1, reason: "lunch", notes: null });
  assert.equal(document.querySelector(".agenda-pause-status")?.textContent, "En pausa");
  assert.equal(document.querySelector(".agenda-pause-reason")?.textContent, "Almuerzo");
  assert.ok(button("Finalizar pausa"));
  await act(async () => button("Finalizar pausa").click());
  assert.ok(calls.some((call) => call.url === "/provider-pauses/7/finish"));
  assert.match(document.body.textContent, /DISPONIBLE/);
  assert.equal(button("Finalizar pausa"), undefined);
});

test("secretaría ve pausa e historial, pero no acciones de inicio o cierre", async () => {
  current = { id: 7, organization_id: 1, center_id: 1, doctor_id: 2, reason: "emergency", notes: "Detalle", actual_started_at: "2030-10-15T11:31:00", actual_finished_at: null, duration_seconds: null };
  await act(async () => root.render(h(ProviderPauseCard, { centerId: 1, doctorId: 2, doctorName: "Dr. Osiris", canManage: false, isAdmin: false })));
  assert.equal(document.querySelector(".agenda-pause-status")?.textContent, "En pausa");
  assert.equal(document.querySelector(".agenda-pause-reason")?.textContent, "Emergencia");
  assert.equal(button("Finalizar pausa"), undefined);
  assert.equal(button("Iniciar pausa"), undefined);
  await act(async () => button("Ver historial de pausas").click());
  assert.match(document.body.textContent, /Emergencia/);
  assert.equal(calls.filter((call) => call.method === "post").length, 0);
});
