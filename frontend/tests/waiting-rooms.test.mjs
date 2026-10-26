import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { WaitingRoomSettings } = await server.ssrLoadModule("/src/components/agenda/WaitingRoomSettings.tsx");
const { QueueDisplaySettings } = await server.ssrLoadModule("/src/components/agenda/QueueDisplaySettings.tsx");
const { QueueArrivalPanel } = await server.ssrLoadModule("/src/components/agenda/QueueArrivalPanel.tsx");
const { default: QueueDisplayPage } = await server.ssrLoadModule("/src/pages/QueueDisplayPage.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const originalFetch = globalThis.fetch;
const originalInterval = window.setInterval;
const originalClear = window.clearInterval;
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = (label) => [...document.querySelectorAll("button")].find((item) => item.textContent === label);
let root;

beforeEach(() => { root = createRoot(document.getElementById("root")); });
afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter; globalThis.fetch = originalFetch;
  window.setInterval = originalInterval; window.clearInterval = originalClear;
  document.getElementById("root").innerHTML = "";
});
after(async () => { await server.close(); dom.window.close(); });

test("administración crea una sala propia y asigna líneas/secretarias", async () => {
  const calls = [];
  let rooms = [];
  const lines = [{ id: 4, center_id: 1, doctor_name: "Dr. Osiris", name: "Cardiología", prefix: "C", is_active: true }];
  api.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/waiting-rooms") return response(config, rooms);
    if (config.method === "get" && config.url === "/queue-lines") return response(config, lines);
    if (config.method === "post" && config.url === "/waiting-rooms") {
      rooms = [{ ...JSON.parse(config.data), id: 8, queue_lines: [], secretaries: [], displays: [] }];
      return response(config, rooms[0]);
    }
    if (config.method === "put" && config.url === "/waiting-rooms/8/queue-lines") {
      rooms[0].queue_lines = JSON.parse(config.data).queue_line_ids.map((id) => ({ id, name: "Cardiología", prefix: "C", provider_name: "Dr. Osiris" }));
      return response(config, rooms[0]);
    }
    if (config.method === "put" && config.url === "/waiting-rooms/8/secretaries") {
      rooms[0].secretaries = JSON.parse(config.data).secretary_user_ids.map((id) => ({ user_id: id, full_name: "Secretaria" }));
      return response(config, rooms[0]);
    }
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
  await act(async () => root.render(h(WaitingRoomSettings, { centers: [{ id: 1, name: "Centro Uno" }],
    people: [{ id: 7, full_name: "Secretaria", roles: ["secretary"], is_active: true, centerIds: [1] }] })));
  assert.doesNotMatch(document.body.textContent, /QA Audio|Sala A.*Sala B/);
  const name = [...document.querySelectorAll("input")].find((item) => item.maxLength === 120);
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(name, "Sala Principal"); name.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  await act(async () => button("Crear sala").click());
  assert.equal(JSON.parse(calls.find((item) => item.method === "post").data).name, "Sala Principal");
  const line = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Dr. Osiris"))?.querySelector("input");
  await act(async () => line.click());
  await act(async () => button("Guardar líneas").click());
  const secretary = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Secretaria"))?.querySelector("input");
  await act(async () => secretary.click());
  await act(async () => button("Guardar secretarias").click());
  assert.deepEqual(JSON.parse(calls.find((item) => item.url === "/waiting-rooms/8/queue-lines").data).queue_line_ids, [4]);
  assert.deepEqual(JSON.parse(calls.find((item) => item.url === "/waiting-rooms/8/secretaries").data).secretary_user_ids, [7]);
});

test("pantalla pública muestra sala y médicos derivados sin información clínica", async () => {
  window.setInterval = () => 1; window.clearInterval = () => {};
  globalThis.fetch = async () => ({ ok: true, json: async () => ({
    display_name: "TV Principal", center_name: "Centro Uno", waiting_room_name: "Sala Principal",
    provider_names: ["Dr. Osiris", "Dra. Tania"], service_names: ["Cardiología"],
    current_calls: [], recent_calls: [], updated_at: "2030-10-15T11:31:00", audio: { audio_enabled: false },
  }) });
  await act(async () => root.render(h(QueueDisplayPage, { token: "synthetic-token" })));
  assert.match(document.body.textContent, /Sala Principal/);
  assert.match(document.body.textContent, /Dr. Osiris · Dra. Tania/);
  assert.doesNotMatch(document.body.textContent, /paciente|teléfono|diagnóstico/i);
});

test("pantalla administrativa se vincula a la sala sin perder líneas explícitas", async () => {
  const calls = [];
  api.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/queue-displays") return response(config, []);
    if (config.method === "get" && config.url === "/queue-lines") return response(config, []);
    if (config.method === "get" && config.url === "/waiting-rooms") return response(config, [{ id: 8, center_id: 1, name: "Sala Principal", is_active: true }]);
    if (config.method === "post" && config.url === "/queue-displays") return response(config, { ...JSON.parse(config.data), id: 2, center_name: "Centro Uno", access_token: "synthetic-token" });
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
  await act(async () => root.render(h(QueueDisplaySettings, { centers: [{ id: 1, name: "Centro Uno" }], showWaitingRooms: true })));
  const selector = [...document.querySelectorAll("select")].find((item) => item.parentElement.textContent.includes("Sala de espera"));
  await act(async () => { selector.value = "8"; selector.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  const name = [...document.querySelectorAll("input")].find((item) => item.maxLength === 120);
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(name, "TV Principal"); name.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  await act(async () => button("Crear pantalla").click());
  const payload = JSON.parse(calls.find((item) => item.method === "post").data);
  assert.equal(payload.waiting_room_id, 8);
  assert.deepEqual(payload.lines, []);
});

test("secretaría puede elegir una de varias salas autorizadas", async () => {
  api.defaults.adapter = async (config) => {
    if (config.url === "/appointments" || config.url === "/queue-lines" || config.url === "/queue-tickets") return response(config, []);
    if (config.url === "/waiting-rooms") return response(config, [
      { id: 8, center_id: 1, name: "Sala Principal", is_active: true, queue_lines: [] },
      { id: 9, center_id: 1, name: "Sala Pediatría", is_active: true, queue_lines: [] },
    ]);
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, showWaitingRooms: true })));
  const selector = [...document.querySelectorAll("select")].find((item) => item.parentElement.textContent.includes("Sala de espera"));
  assert.ok(selector);
  assert.deepEqual([...selector.options].map((item) => item.textContent), ["Todas las salas autorizadas", "Sala Principal", "Sala Pediatría"]);
  await act(async () => { selector.value = "9"; selector.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  assert.equal(selector.value, "9");
});
