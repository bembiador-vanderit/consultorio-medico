import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

import { createBrowser } from "./browser.mjs";
import { activeDoctor, appointmentScheduled, medicalStudyFixture } from "./fixtures/clinical.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Consultation } = await server.ssrLoadModule("/src/pages/Consultation.tsx");
const { default: ConsultationWorkspace } = await server.ssrLoadModule("/src/components/consultation/ConsultationWorkspace.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const { clearClinicalCatalogCacheForTests } = await server.ssrLoadModule("/src/services/clinicalApi.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
const appointment = structuredClone(appointmentScheduled);
let root;

function ok(config, data) { return { data, status: 200, statusText: "OK", headers: {}, config }; }
async function settle() { for (let index = 0; index < 4; index += 1) await act(async () => { await Promise.resolve(); }); }

beforeEach(() => {
  root = createRoot(host);
  clearClinicalCatalogCacheForTests();
  api.defaults.adapter = async (config) => {
    if (config.url === "/auth/me") return ok(config, activeDoctor);
    if (config.url === `/clinical-history/appointments/${appointment.id}/context`) return ok(config, {
      appointment_id: appointment.id, patient_id: appointment.patient_id, doctor_id: appointment.doctor_id, center_id: appointment.center_id,
      specialty_id: appointment.specialty_id, specialty_name: appointment.specialty_name, appointment_date: appointment.appointment_date,
      appointment_time: appointment.appointment_time, appointment_reason: appointment.reason, appointment_status: appointment.status, previous_consultations: [],
    });
    if (config.url === "/clinical-catalog/studies") return ok(config, [medicalStudyFixture]);
    throw new Error(`Unexpected request ${config.method} ${config.url}`);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; clearClinicalCatalogCacheForTests(); });
after(async () => { await server.close(); dom.window.close(); });

test("Consultation delega el episodio al workspace", async () => {
  await act(async () => root.render(h(Consultation, { appointment, onBack() {} })));
  await settle();
  assert.equal(host.querySelector("h2")?.textContent, "Consulta médica");
  assert.match(host.textContent, /Primero guarda la consulta para registrar signos vitales/);
});

test("workspace renderiza el contexto bootstrap sin persistir datos clínicos", async () => {
  await act(async () => root.render(h(ConsultationWorkspace, { appointment, onBack() {} })));
  await settle();
  assert.match(host.textContent, new RegExp(`Cita #${appointment.id}`));
  assert.match(host.textContent, new RegExp(appointment.patient_name));
  assert.equal(window.localStorage.length, 0);
  assert.equal(window.sessionStorage.length, 0);
});

test("workspace mantiene módulos y contexto en una estructura adaptativa sin ancho mínimo rígido", async () => {
  await act(async () => root.render(h(ConsultationWorkspace, { appointment, onBack() {} })));
  await settle();
  const layout = host.querySelector('[data-consultation-layout="adaptive"]');
  assert.ok(layout);
  assert.ok(layout.querySelector("[data-consultation-modules]"));
  assert.ok(layout.querySelector("aside[data-consultation-context]"));
  assert.match(layout.className, /min-w-0/);
  assert.match(layout.className, /xl:grid-cols/);
  assert.doesNotMatch(host.textContent, /appointment_id:|doctor_id:|center_id:/);
});
