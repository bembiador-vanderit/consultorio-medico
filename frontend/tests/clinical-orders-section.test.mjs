import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: ClinicalOrdersSection } = await server.ssrLoadModule("/src/components/clinical/ClinicalOrdersSection.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
let root, calls, props, phase, deferred, fail;

const laboratoryTests = [
  { id: 31, code: "CBC", name: "Hemograma ficticio", category: "Hematología", is_active: true, sort_order: 1 },
  { id: 32, code: "GLU", name: "Glucosa ficticia", category: "Química", is_active: true, sort_order: 2 },
];
const studies = [
  { id: 41, specialty_id: 3, anatomical_region_id: null, name: "Ecografía ficticia", category: "ultrasound", is_active: true, recommended_specialty_ids: [3] },
  { id: 42, specialty_id: 8, anatomical_region_id: null, name: "Tomografía ficticia", category: "tomography", is_active: true, recommended_specialty_ids: [] },
];
const labOrder = (historyId, id = 501, additional = false) => ({ id, clinical_history_id: historyId, patient_name: `Paciente ${historyId}`, doctor_name: "Dra. Prueba", center_name: "Centro ficticio", specialty_name: "Cardiología ficticia", status: "ordered", is_additional: additional, notes: "Nota laboratorio", created_at: "2026-09-16T09:00:00", items: [{ id: id * 10, laboratory_test_id: 31, test_code: "CBC", test_name: "Hemograma ficticio", test_category: "Hematología", custom_note: null }] });
const studyOrder = (historyId, id = 601, additional = false) => ({ id, clinical_history_id: historyId, patient_name: `Paciente ${historyId}`, doctor_name: "Dra. Prueba", center_name: "Centro ficticio", specialty_name: "Cardiología ficticia", status: "ordered", is_additional: additional, notes: "Nota estudios", created_at: "2026-09-16T09:00:00", items: [{ id: id * 10, medical_study_id: 41, modality: "ultrasound", study_name: "Ecografía ficticia", region_description: "Abdomen", contrast: "not_applicable", clinical_notes: "Detalle clínico" }] });
let laboratoryOrders, studyOrders;

function ok(config, data) { return { data: structuredClone(data), status: 200, statusText: "OK", headers: {}, config }; }
function rejected(detail) { const error = new Error(detail); error.response = { status: 409, data: { detail } }; return error; }
function payload(config) { return JSON.parse(config.data); }
function historyId(url, kind) { return Number(new RegExp(`/clinical-history/(\\d+)/${kind}`).exec(url)?.[1]); }
function dataForA(config) {
  if (config.url === "/laboratory-tests") return laboratoryTests;
  if (config.url === "/clinical-catalog/studies") return studies;
  if (config.url.includes("laboratory-orders")) return [labOrder(42, 701)];
  return [studyOrder(42, 801)];
}

async function adapter(config) {
  calls.push(config);
  if (phase === "defer-a" && config.method === "get") return new Promise((resolve, reject) => deferred.push({ config, resolve, reject }));
  if (fail?.(config)) throw rejected("Error de servidor visible");
  if (config.method === "get") {
    if (config.url === "/laboratory-tests") return ok(config, laboratoryTests);
    if (config.url === "/clinical-catalog/studies") return ok(config, studies);
    if (config.url.includes("/laboratory-orders")) return ok(config, laboratoryOrders[historyId(config.url, "laboratory-orders")] || []);
    if (config.url.includes("/study-orders")) return ok(config, studyOrders[historyId(config.url, "study-orders")] || []);
    if (/^\/(laboratory-orders|study-orders)\/\d+\/pdf$/.test(config.url)) return ok(config, new Blob(["fixture"]));
  }
  if (config.method === "post" || config.method === "put") {
    const laboratory = config.url.includes("laboratory-orders");
    const id = historyId(config.url, laboratory ? "laboratory-orders" : "study-orders");
    const collection = laboratory ? laboratoryOrders : studyOrders;
    const input = payload(config);
    const created = laboratory
      ? { ...labOrder(id, config.method === "put" ? Number(config.url.split("/").at(-1)) : 900, config.url.endsWith("/additional")), notes: input.notes, items: input.items.map((item, index) => ({ id: 9000 + index, laboratory_test_id: item.laboratory_test_id, test_code: null, test_name: laboratoryTests.find((test) => test.id === item.laboratory_test_id).name, test_category: laboratoryTests.find((test) => test.id === item.laboratory_test_id).category, custom_note: item.custom_note ?? null })) }
      : { ...studyOrder(id, config.method === "put" ? Number(config.url.split("/").at(-1)) : 901, config.url.endsWith("/additional")), notes: input.notes, items: input.items.map((item, index) => ({ id: 9100 + index, medical_study_id: item.medical_study_id, modality: studies.find((study) => study.id === item.medical_study_id).category, study_name: studies.find((study) => study.id === item.medical_study_id).name, region_description: item.region_description, contrast: item.contrast, clinical_notes: item.clinical_notes })) };
    collection[id] = config.method === "put" ? collection[id].map((order) => order.id === created.id ? created : order) : [...collection[id], created];
    return ok(config, created);
  }
  throw new Error(`Unexpected ${config.method} ${config.url}`);
}

async function settle() { for (let index = 0; index < 4; index += 1) await act(async () => { await Promise.resolve(); }); }
async function render(next = props) { props = next; await act(async () => root.render(h(ClinicalOrdersSection, props))); await settle(); }
const button = (label, scope = host) => [...scope.querySelectorAll("button")].find((item) => item.textContent.trim() === label);
const byPlaceholder = (value) => host.querySelector(`[placeholder="${value}"]`);
const labels = (text) => [...host.querySelectorAll("label")].filter((item) => item.textContent.includes(text));
const section = (title) => [...host.querySelectorAll("section")].find((item) => item.querySelector("h3")?.textContent === title);
async function click(target) { assert.ok(target); await act(async () => target.click()); await settle(); }
async function change(target, value) {
  assert.ok(target);
  await act(async () => {
    const prototype = target.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : target.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(target, value);
    target.dispatchEvent(new dom.window.Event(target.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
  await settle();
}

beforeEach(() => {
  root = createRoot(host); calls = []; phase = "ready"; deferred = []; fail = null;
  laboratoryOrders = { 42: [labOrder(42)], 77: [labOrder(77, 702)] };
  studyOrders = { 42: [studyOrder(42)], 77: [studyOrder(77, 802)] };
  props = { historyId: 42, specialtyId: 3, completed: false, allowAdditional: false };
  api.defaults.adapter = adapter;
  dom.window.HTMLAnchorElement.prototype.click = () => {};
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });

test("loads canonical orders and catalogs; laboratory search, multiple selection and payload remain exact", async () => {
  await render();
  assert.match(host.textContent, /Orden de laboratorio #501/); assert.match(host.textContent, /Orden de estudios #601/);
  assert.match(host.textContent, /Hemograma ficticio/); assert.match(host.textContent, /Ecografía ficticia/);
  await change(byPlaceholder("Buscar prueba o categoría..."), "hemat");
  assert.equal(labels("Glucosa ficticia").length, 0);
  await click(labels("Hemograma ficticio")[0].querySelector("input"));
  await change(byPlaceholder("Buscar prueba o categoría..."), "");
  await click(labels("Glucosa ficticia")[0].querySelector("input"));
  await change(byPlaceholder("Observaciones generales de la orden (opcional)"), " Nota nueva ");
  await click(button("Guardar orden"));
  const created = calls.find((item) => item.method === "post" && item.url === "/clinical-history/42/laboratory-orders");
  assert.deepEqual(payload(created), { items: [{ laboratory_test_id: 31 }, { laboratory_test_id: 32 }], notes: "Nota nueva" });
  assert.match(host.textContent, /Orden de laboratorio #900/);
});

test("laboratory edit, update, PDF and backend error preserve the existing contract", async () => {
  await render(); await click(button("Editar"));
  assert.ok(button("Actualizar orden"));
  await change(byPlaceholder("Observaciones generales de la orden (opcional)"), " Editada ");
  await click(button("Actualizar orden"));
  const updated = calls.find((item) => item.method === "put" && item.url === "/clinical-history/42/laboratory-orders/501");
  assert.deepEqual(payload(updated), { items: [{ laboratory_test_id: 31 }], notes: "Editada" });
  await click(button("Descargar PDF"));
  assert.ok(calls.some((item) => item.url === "/laboratory-orders/501/pdf"));
  fail = (config) => config.url === "/laboratory-orders/501/pdf";
  await click(button("Descargar PDF"));
  assert.match(host.querySelector('[role="alert"]').textContent, /Error de servidor visible/);
});

test("study catalog recommendations, multi-item detail fields and update/PDF contracts remain exact", async () => {
  await render();
  assert.match(host.textContent, /Recomendado/); assert.equal(labels("Tomografía ficticia").length, 1);
  await click(labels("Ecografía ficticia")[0].querySelector("input")); await click(labels("Tomografía ficticia")[0].querySelector("input"));
  const regions = [...host.querySelectorAll('input[placeholder="Región o descripción"]')];
  await change(regions[0], " Abdomen "); await change(regions[1], " Tórax ");
  const contrasts = [...host.querySelectorAll("select")]; await change(contrasts[0], "yes"); await change(contrasts[1], "no");
  const details = [...host.querySelectorAll('textarea[placeholder="Observaciones clínicas (opcional)"]')];
  await change(details[0], " Nota A "); await change(details[1], " Nota B ");
  const notes = [...host.querySelectorAll('textarea[placeholder="Observaciones generales de la orden (opcional)"]')].at(-1);
  await change(notes, " General "); await click(button("Guardar orden", section("Estudios y procedimientos")));
  const created = calls.find((item) => item.method === "post" && item.url === "/clinical-history/42/study-orders");
  assert.deepEqual(payload(created), { items: [{ medical_study_id: 41, region_description: "Abdomen", contrast: "yes", clinical_notes: "Nota A" }, { medical_study_id: 42, region_description: "Tórax", contrast: "no", clinical_notes: "Nota B" }], notes: "General" });
  await click(button("Editar", section("Estudios y procedimientos"))); await click(button("Actualizar orden", section("Estudios y procedimientos")));
  assert.ok(calls.some((item) => item.method === "put" && item.url === "/clinical-history/42/study-orders/601"));
  const studyPdf = [...host.querySelectorAll("button")].find((item) => item.textContent.trim() === "Descargar PDF" && item.closest("section")?.textContent.includes("Estudios y procedimientos"));
  await click(studyPdf); assert.ok(calls.some((item) => item.url === "/study-orders/601/pdf"));
});

test("completed mode retains readable/PDF orders, hides normal edits, and gates additional creation", async () => {
  await render({ ...props, completed: true, allowAdditional: false });
  assert.match(host.textContent, /Orden de laboratorio #501/); assert.equal(button("Editar"), undefined); assert.equal(button("Guardar orden"), undefined);
  assert.equal(button("Nueva orden adicional"), undefined); assert.ok(button("Descargar PDF"));
  await render({ ...props, completed: true, allowAdditional: true });
  assert.ok(button("Laboratorio")); assert.ok(button("Estudio / procedimiento"));
  await click(button("Laboratorio")); await click(labels("Hemograma ficticio")[0].querySelector("input")); await click(button("Guardar orden"));
  assert.ok(calls.some((item) => item.method === "post" && item.url === "/clinical-history/42/laboratory-orders/additional"));
  assert.match(host.textContent, /Orden adicional/);
  await click(button("Estudio / procedimiento")); await click(labels("Ecografía ficticia")[0].querySelector("input")); await click(button("Guardar orden"));
  assert.ok(calls.some((item) => item.method === "post" && item.url === "/clinical-history/42/study-orders/additional"));
});

test("history switch clears selections, edit mode, notes and queries before loading B", async () => {
  await render(); await click(button("Editar")); await change(byPlaceholder("Observaciones generales de la orden (opcional)"), "Edición A");
  await change(byPlaceholder("Buscar prueba o categoría..."), "hema");
  await render({ ...props, historyId: 77, specialtyId: 8 });
  assert.equal(button("Actualizar orden"), undefined); assert.equal(byPlaceholder("Observaciones generales de la orden (opcional)").value, "");
  assert.equal(byPlaceholder("Buscar prueba o categoría...").value, ""); assert.match(host.textContent, /Orden de laboratorio #702/);
});

for (const outcome of ["success", "error"]) test(`stale A ${outcome} cannot publish into B`, async () => {
  phase = "defer-a"; await render(); assert.equal(deferred.length, 4);
  phase = "ready"; await render({ ...props, historyId: 77, specialtyId: 8 });
  assert.match(host.textContent, /Orden de laboratorio #702/);
  await act(async () => { for (const request of deferred) outcome === "success" ? request.resolve(ok(request.config, dataForA(request.config))) : request.reject(rejected("Error tardío de A")); });
  await settle(); assert.match(host.textContent, /Orden de laboratorio #702/); assert.doesNotMatch(host.textContent, /Orden de laboratorio #701|Error tardío de A/);
});

test("unmount ignores a pending orders load", async () => {
  phase = "defer-a"; await render(); assert.equal(deferred.length, 4);
  await act(async () => root.unmount());
  await act(async () => { for (const request of deferred) request.resolve(ok(request.config, dataForA(request.config))); });
  assert.equal(host.textContent, "");
});
