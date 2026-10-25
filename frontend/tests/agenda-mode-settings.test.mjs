import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { AgendaModeSettings } = await server.ssrLoadModule("/src/components/agenda/AgendaModeSettings.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
let root;
let calls;
let current;

const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = text => [...document.querySelectorAll("button")].find(item => item.textContent === text);
async function select(label, value) {
  const field = [...document.querySelectorAll("label")].find(item => item.textContent.includes(label)).querySelector("select");
  await act(async () => { field.value = value; field.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
}

beforeEach(() => {
  root = createRoot(document.getElementById("root"));
  calls = [];
  current = { base_mode: "queue", exception_mode: "timed", effective_mode: "timed" };
  api.defaults.adapter = async config => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get") return response(config, current);
    if (config.method === "put" && config.url.endsWith("/base")) {
      const sent = JSON.parse(config.data);
      if (sent.allowed_timed !== undefined) current = {
        ...current, base_mode: sent.default_mode, effective_mode: sent.default_mode,
        base_policy: sent, effective_policy: sent,
      };
    }
    if (config.method === "delete") current = { ...current, exception_mode: null, effective_mode: current.base_mode };
    return response(config, current);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });

test("muestra la modalidad efectiva y quita solo la excepción elegida", async () => {
  await act(async () => root.render(h(AgendaModeSettings, {
    doctors: [{ id: 7, full_name: "Médico sintético", centerIds: [3] }],
    centers: [{ id: 3, name: "Centro sintético" }],
  })));
  await select("Médico", "7");
  await select("Centro", "3");
  assert.match(document.body.textContent, /Predeterminada para esta fecha: Por hora · excepción/);
  await act(async () => button("Quitar excepción").click());
  assert.equal(calls.filter(call => call.method === "delete").length, 1);
  assert.match(document.body.textContent, /Predeterminada para esta fecha: Por turno/);
  assert.match(document.body.textContent, /Las citas por turno se agendan sin hora/);
});

test("permite ambas modalidades, cambia predeterminada y advierte QueueLine faltante", async () => {
  current = {
    base_mode: "timed", exception_mode: null, effective_mode: "timed",
    base_policy: { allowed_timed: true, allowed_queue: false, default_mode: "timed" },
    effective_policy: { allowed_timed: true, allowed_queue: false, default_mode: "timed" },
    queue_line_available: false, multimode_enabled: true,
  };
  await act(async () => root.render(h(AgendaModeSettings, {
    doctors: [{ id: 7, full_name: "Médico sintético", centerIds: [3] }],
    centers: [{ id: 3, name: "Centro sintético" }],
  })));
  await select("Médico", "7");
  await select("Centro", "3");
  const habitual = [...document.querySelectorAll("fieldset")].find(item => item.querySelector("legend")?.textContent === "Modo habitual");
  const queue = habitual.querySelectorAll('input[type="checkbox"]')[1];
  await act(async () => { queue.click(); });
  assert.equal(habitual.querySelectorAll('input[type="checkbox"]')[0].checked, true);
  assert.equal(habitual.querySelectorAll('input[type="checkbox"]')[1].checked, true);
  await act(async () => habitual.querySelectorAll('input[type="radio"]')[1].click());
  await act(async () => button("Guardar modo habitual").click());
  const sent = JSON.parse(calls.find(call => call.method === "put").data);
  assert.deepEqual(sent, { allowed_timed: true, allowed_queue: true, default_mode: "queue" });
  assert.match(document.body.textContent, /Configure una línea de turnos/);
});
