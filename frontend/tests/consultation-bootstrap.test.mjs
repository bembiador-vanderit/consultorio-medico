import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { useConsultationBootstrap } = await server.ssrLoadModule("/src/hooks/useConsultationBootstrap.ts");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const { clearClinicalCatalogCacheForTests } = await server.ssrLoadModule("/src/services/clinicalApi.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
let root; let deferredA; let signalA; let mode;
const context = (id) => ({ appointment_id: id, patient_id: id, doctor_id: 12, center_id: 7, specialty_id: 3, specialty_name: "Cardiología", appointment_date: "2026-09-16", appointment_time: "09:00", appointment_reason: null, appointment_status: "scheduled", previous_consultations: [] });
function Probe({ appointmentId }) { const state = useConsultationBootstrap(appointmentId); return h("output", { "data-error": state.error, "data-loading": String(state.loading) }, state.context?.appointment_id ?? "none"); }
function settle() { return act(async () => { await Promise.resolve(); await Promise.resolve(); }); }

beforeEach(() => { root = createRoot(host); deferredA = {}; mode = "deferred"; api.defaults.adapter = async (config) => { if (config.url === "/clinical-history/appointments/81/context") { signalA = config.signal; if (mode === "active-error") { const error = new Error("fallo activo"); error.response = { data: { detail: "Error activo" } }; throw error; } if (mode === "abort-error") { const error = new Error("lectura cancelada"); error.__CANCEL__ = true; throw error; } return new Promise((resolve, reject) => { deferredA.resolve = () => resolve({ data: context(81), status: 200, statusText: "OK", headers: {}, config }); deferredA.reject = reject; }); } if (config.url === "/clinical-history/appointments/82/context") return { data: context(82), status: 200, statusText: "OK", headers: {}, config }; if (config.url === "/clinical-catalog/studies") return { data: [], status: 200, statusText: "OK", headers: {}, config }; throw new Error(`Unexpected ${config.url}`); }; });
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; clearClinicalCatalogCacheForTests(); });
after(async () => { await server.close(); dom.window.close(); });

test("la generación activa ignora una respuesta tardía y aborta la lectura anterior", async () => {
  await act(async () => root.render(h(Probe, { appointmentId: 81 })));
  await act(async () => root.render(h(Probe, { appointmentId: 82 })));
  await settle();
  assert.equal(signalA.aborted, true);
  assert.equal(host.textContent, "82");
  await act(async () => deferredA.resolve());
  await settle();
  assert.equal(host.textContent, "82");
});

test("unmount aborta el bootstrap pendiente", async () => {
  await act(async () => root.render(h(Probe, { appointmentId: 81 })));
  await act(async () => root.unmount());
  assert.equal(signalA.aborted, true);
});

test("un error activo se publica, pero un error stale no reemplaza el contexto actual", async () => {
  mode = "active-error";
  await act(async () => root.render(h(Probe, { appointmentId: 81 })));
  await settle();
  assert.equal(host.querySelector("output").dataset.error, "Error activo");
  assert.equal(host.querySelector("output").dataset.loading, "false");

  await act(async () => root.unmount());
  root = createRoot(host);
  mode = "deferred";
  await act(async () => root.render(h(Probe, { appointmentId: 81 })));
  await act(async () => root.render(h(Probe, { appointmentId: 82 })));
  await settle();
  const staleError = new Error("fallo stale"); staleError.response = { data: { detail: "Error stale" } };
  await act(async () => deferredA.reject(staleError));
  await settle();
  assert.equal(host.textContent, "82");
  assert.equal(host.querySelector("output").dataset.error, "");
});

test("AbortError esperado no se publica como error clínico", async () => {
  mode = "abort-error";
  await act(async () => root.render(h(Probe, { appointmentId: 81 })));
  await settle();
  assert.equal(host.querySelector("output").dataset.error, "");
});
