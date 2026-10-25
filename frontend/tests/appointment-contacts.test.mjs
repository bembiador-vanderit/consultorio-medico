import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { AppointmentContactPanel } = await server.ssrLoadModule("/src/components/agenda/AppointmentContactPanel.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
let root;
let calls;
let attempts;

const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = (text) => [...document.querySelectorAll("button")].find((item) => item.textContent === text);

beforeEach(() => {
  root = createRoot(document.getElementById("root"));
  calls = [];
  attempts = [];
  api.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, params: config.params, data: config.data });
    if (config.method === "get" && config.url === "/appointment-contacts") {
      const latest = attempts.at(-1) ?? null;
      const items = config.params?.result && config.params.result !== (latest?.result ?? "pending") ? [] : [{
        appointment_id: 7, patient_name: "Ana Prueba", patient_phone: "809-000-0001",
        appointment_date: "2030-10-15", appointment_time: "09:00:00", doctor_name: "Doctora Prueba",
        center_name: "Centro", latest_contact: latest,
      }];
      return response(config, { date: "2030-10-15", totals: {
        total_expected: 1, contacted: latest ? 1 : 0, not_contacted: latest ? 0 : 1,
        will_attend: latest?.result === "will_attend" ? 1 : 0,
        will_not_attend: 0, no_answer: 0, retry: latest?.result === "retry" ? 1 : 0,
      }, items });
    }
    if (config.method === "get") return response(config, attempts);
    if (config.method === "post") {
      const body = JSON.parse(config.data);
      attempts.push({ id: attempts.length + 1, appointment_id: 7, contacted_by_name: "Tania",
        contacted_at: "2030-10-14T15:00:00", result: body.result,
        contact_value: body.contact_value, notes: body.notes });
      return response(config, attempts.at(-1));
    }
    throw new Error("Unexpected request");
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });

test("muestra pendiente, conserva historial y filtra el último resultado", async () => {
  await act(async () => root.render(h(AppointmentContactPanel, { initialDate: "2030-10-15", canRecord: true })));
  assert.match(document.body.textContent, /Ana Prueba/);
  assert.match(document.body.textContent, /809-000-0001/);
  assert.match(document.body.textContent, /Pendiente de contactar/);
  await act(async () => button("Registrar contacto / Ver historial").click());
  assert.match(document.body.textContent, /Sin intentos registrados/);
  const result = document.querySelector('div[aria-label="Historial de contacto"] select');
  await act(async () => { result.value = "retry"; result.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  await act(async () => button("Guardar intento").click());
  assert.match(document.body.textContent, /Reintentar/);
  await act(async () => button("Registrar contacto / Ver historial").click());
  assert.match(document.body.textContent, /Tania/);
  await act(async () => button("Guardar intento").click());
  assert.equal(attempts.length, 2);
  await act(async () => button("Registrar contacto / Ver historial").click());
  assert.equal(document.querySelectorAll('div[aria-label="Historial de contacto"] li').length, 2);
  assert.match(document.body.textContent, /Indicó que asistirá/);
  const filter = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Resultado") && !item.closest('div[aria-label="Historial de contacto"]')).querySelector("select");
  await act(async () => { filter.value = "pending"; filter.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  assert.match(document.body.textContent, /No hay citas previstas con este filtro/);
  assert.equal(calls.filter((call) => call.method === "post").length, 2);
});
