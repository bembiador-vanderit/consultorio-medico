import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom, setDesktop } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: ClinicalHistoryPanel } = await server.ssrLoadModule("/src/components/patients/ClinicalHistoryPanel.tsx");
const { default: HistoricalConsultationProjection } = await server.ssrLoadModule("/src/components/consultation/HistoricalConsultationProjection.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const adapter = api.defaults.adapter;
const host = document.getElementById("root");

const user = { id: 7, full_name: "Doctora Ficticia", roles: ["doctor"], is_active: true };
const baseHistory = {
  id: 41, patient_id: 9, appointment_id: 51, doctor_id: 7, center_id: 2, specialty_id: 3,
  specialty_name: "Especialidad ficticia", doctor_name: "Doctora Ficticia", center_name: "Centro ficticio",
  consultation_date: "2026-09-01", reason_for_visit: "Motivo ficticio", current_illness: "Historia ficticia",
  personal_history: "Antecedente ficticio", family_history: "Familia ficticia", allergies: "Sin alergias",
  current_medications: "Ninguno", previous_surgeries: "Ninguna", chronic_conditions: "Ninguna",
  habits: "Ninguno", clinical_notes: "Nota ficticia", revision: 1, status: "in_progress",
  completed_at: null, completed_by_id: null, created_at: "2026-09-01T10:00:00", updated_at: "2026-09-01T10:00:00",
  requested_tests: [],
};
const details = {
  diagnoses: [], prescriptions: [], requestedTests: [], vitalSigns: null, addenda: [], laboratoryOrders: [], studyOrders: [],
};
let root;
let records;
let saveFailure;
let requests;

function history(overrides = {}) { return { ...baseHistory, ...overrides }; }
function detailResponse(config) {
  if (config.url.endsWith("/diagnoses")) return details.diagnoses;
  if (config.url.endsWith("/prescriptions")) return details.prescriptions;
  if (config.url.endsWith("/requested-tests")) return details.requestedTests;
  if (config.url.endsWith("/vital-signs")) return details.vitalSigns;
  if (config.url.endsWith("/addenda")) return details.addenda;
  if (config.url.endsWith("/laboratory-orders")) return details.laboratoryOrders;
  if (config.url.endsWith("/study-orders")) return details.studyOrders;
  return undefined;
}
beforeEach(() => {
  root = createRoot(host); setDesktop(true); requests = []; saveFailure = null;
  records = [history()];
  api.defaults.adapter = async (config) => {
    requests.push(config);
    if (config.url === "/clinical-history/patients/9" && config.method === "get") return { data: records, status: 200, statusText: "OK", headers: {}, config };
    if (config.method === "get" && config.url.startsWith("/clinical-history/")) {
      const data = detailResponse(config);
      if (data !== undefined) return { data, status: 200, statusText: "OK", headers: {}, config };
    }
    if (config.method === "put" && config.url === "/clinical-history/41") {
      if (saveFailure) throw saveFailure;
      const payload = JSON.parse(config.data);
      const saved = { ...records[0], ...payload, revision: records[0].revision + 1, updated_at: "2026-09-19T10:00:00" };
      records = [saved];
      return { data: saved, status: 200, statusText: "OK", headers: {}, config };
    }
    throw new Error(`Unexpected endpoint ${config.method} ${config.url}`);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = adapter; });
after(async () => { await server.close(); dom.window.close(); });

async function settle() { for (let index = 0; index < 6; index += 1) await act(async () => { await Promise.resolve(); }); }
async function mountPanel(nextRecords = [history()]) {
  records = nextRecords;
  await act(async () => root.render(h(ClinicalHistoryPanel, { patientId: 9, patientName: "Paciente ficticio", user, onClose() {}, embedded: true })));
  await settle();
}
async function click(element) { assert.ok(element); await act(async () => element.click()); await settle(); }
function button(label) { return [...host.querySelectorAll("button")].find((item) => item.textContent.trim() === label); }
function textareas() { return [...host.querySelectorAll("textarea")]; }
function alertText() { return host.querySelector('[role="alert"]')?.textContent || ""; }
async function setTextarea(field, next) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(field, next);
    field.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}

test("HistoricalConsultationProjection is always read-only", async () => {
  await act(async () => root.render(h(HistoricalConsultationProjection, { history: history({ status: "completed" }), details })));
  assert.equal(host.querySelectorAll("input, textarea, select").length, 0);
  assert.doesNotMatch(host.textContent, /Guardar cambios|Editar diagnóstico|Editar receta/);
});

test("completed history from Patients has no normal edit or save controls", async () => {
  await mountPanel([history({ status: "completed" })]);
  assert.equal(textareas().length, 0);
  assert.equal(button("Guardar cambios"), undefined);
  assert.match(host.textContent, /Motivo ficticio/);
});

test("open history retains editing and valid save sends only ClinicalHistoryUpdate fields", async () => {
  await mountPanel();
  assert.ok(textareas().length > 0);
  const field = textareas()[0];
  await setTextarea(field, "Cambio ficticio");
  await click(button("Guardar cambios"));
  const request = requests.find((item) => item.method === "put");
  const payload = JSON.parse(request.data);
  assert.deepEqual(Object.keys(payload).sort(), ["allergies", "chronic_conditions", "clinical_notes", "consultation_date", "current_illness", "current_medications", "expected_revision", "family_history", "habits", "personal_history", "previous_surgeries", "reason_for_visit"].sort());
  assert.match(host.textContent, /guardados correctamente/);
  assert.notEqual(host.textContent.trim(), "");
});

for (const status of [409, 403, 422]) {
  test(`rejected ${status} save preserves the rendered page and local text`, async () => {
    await mountPanel();
    const field = textareas()[0];
    await setTextarea(field, "Cambio local ficticio");
    saveFailure = { response: { status, data: { detail: `Error ficticio ${status}` } } };
    await click(button("Guardar cambios"));
    assert.match(alertText(), new RegExp(`Error ficticio ${status}`));
    assert.equal(textareas()[0].value, "Cambio local ficticio");
    assert.notEqual(host.textContent.trim(), "");
  });
}

test("switching episodes preserves the correct editability boundary", async () => {
  const completed = history({ id: 41, status: "completed" });
  const open = history({ id: 42, status: "in_progress", reason_for_visit: "Consulta abierta ficticia" });
  records = [completed, open];
  await mountPanel(records);
  assert.equal(textareas().length, 0);
  await click(button("← Anterior"));
  assert.ok(textareas().length > 0);
  assert.match(host.textContent, /Consulta abierta ficticia/);
});

test("completed wrapper keeps post-close controls separate from read-only projection", async () => {
  await mountPanel([history({ status: "completed" })]);
  assert.equal(textareas().length, 0);
  assert.ok(button("Agregar nota adicional"));
  assert.ok(button("Nueva orden adicional"));
  assert.equal(button("Guardar cambios"), undefined);
});
