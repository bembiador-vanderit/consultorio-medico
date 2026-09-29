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
let root, props, calls, laboratoryOrders, studyOrders, deferred, fail, deferredPdf, nativeAnchorClick, dirtyStates;

const tests = [
  { id: 31, code: "CBC", name: "Hemograma ficticio", category: "Hematología", is_active: true, sort_order: 1 },
  { id: 32, code: "GLU", name: "Glucosa ficticia", category: "Química", is_active: true, sort_order: 2 },
];
const studies = [
  { id: 41, specialty_id: 3, anatomical_region_id: null, name: "Ecografía ficticia", category: "ultrasound", is_active: true, recommended_specialty_ids: [3] },
  { id: 42, specialty_id: 8, anatomical_region_id: null, name: "Tomografía ficticia", category: "tomography", is_active: true, recommended_specialty_ids: [] },
];
const labOrder = (historyId, id = 501, additional = false) => ({ id, clinical_history_id: historyId, patient_name: "Paciente", doctor_name: "Dra. Prueba", center_name: "Centro", specialty_name: "Cardiología", status: "ordered", is_additional: additional, notes: "Nota laboratorio", created_at: "2026-09-16T09:00:00", items: [{ id: id * 10, laboratory_test_id: 31, test_code: "CBC", test_name: "Hemograma ficticio", test_category: "Hematología", custom_note: null }] });
const studyOrder = (historyId, id = 601, additional = false) => ({ id, clinical_history_id: historyId, patient_name: "Paciente", doctor_name: "Dra. Prueba", center_name: "Centro", specialty_name: "Cardiología", status: "ordered", is_additional: additional, notes: "Nota estudios", created_at: "2026-09-16T09:00:00", items: [{ id: id * 10, medical_study_id: 41, modality: "ultrasound", study_name: "Ecografía ficticia", region_description: "Abdomen", contrast: "not_applicable", clinical_notes: "Detalle clínico" }] });
const ok = (config, data) => ({ data: structuredClone(data), status: 200, statusText: "OK", headers: {}, config });
const failure = (detail = "Error de servidor visible") => Object.assign(new Error(detail), { response: { status: 409, data: { detail } } });
const payload = config => JSON.parse(config.data);
const historyId = (url, kind) => Number(new RegExp(`/clinical-history/(\\d+)/${kind}`).exec(url)?.[1]);
const button = (text, scope = host) => [...scope.querySelectorAll("button")].find(item => item.textContent.trim() === text || item.textContent.trim().startsWith(text));
const input = label => host.querySelector(`[aria-label="${label}"]`);
async function settle() { for (let index = 0; index < 5; index += 1) await act(async () => { await Promise.resolve(); }); }
async function click(target) { assert.ok(target); await act(async () => target.click()); await settle(); }
async function change(target, value) {
  assert.ok(target);
  await act(async () => {
    const proto = target.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : target.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(target, value);
    target.dispatchEvent(new dom.window.Event(target.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
  await settle();
}
async function render(next = props) { props = next; await act(async () => root.render(h(ClinicalOrdersSection, props))); await settle(); }

async function adapter(config) {
  calls.push(config);
  if (deferredPdf && /^\/(laboratory-orders|study-orders)\/\d+\/pdf$/.test(config.url)) return new Promise(resolve => { deferredPdf.resolve = () => resolve(ok(config, new Blob(["pdf"]))); });
  if (deferred && config.method === "get" && config.url.includes("/clinical-history/42/")) return new Promise((resolve, reject) => deferred.push({ config, resolve, reject }));
  if (fail?.(config)) throw failure();
  if (config.method === "get") {
    if (config.url === "/laboratory-tests") return ok(config, tests);
    if (config.url === "/clinical-catalog/studies") return ok(config, studies);
    if (/^\/(laboratory-orders|study-orders)\/\d+\/pdf$/.test(config.url)) return ok(config, new Blob(["pdf"]));
    if (config.url.includes("laboratory-orders")) return ok(config, laboratoryOrders[historyId(config.url, "laboratory-orders")] || []);
    if (config.url.includes("study-orders")) return ok(config, studyOrders[historyId(config.url, "study-orders")] || []);
  }
  if (config.method === "post" || config.method === "put") {
    const laboratory = config.url.includes("laboratory-orders"); const kind = laboratory ? "laboratory-orders" : "study-orders"; const id = historyId(config.url, kind); const body = payload(config);
    const created = laboratory ? { ...labOrder(id, config.method === "put" ? Number(config.url.split("/").at(-1)) : 900, config.url.endsWith("/additional")), notes: body.notes, items: body.items.map((item, index) => ({ id: 9000 + index, laboratory_test_id: item.laboratory_test_id, test_code: null, test_name: tests.find(test => test.id === item.laboratory_test_id).name, test_category: tests.find(test => test.id === item.laboratory_test_id).category, custom_note: null })) } : { ...studyOrder(id, config.method === "put" ? Number(config.url.split("/").at(-1)) : 901, config.url.endsWith("/additional")), notes: body.notes, items: body.items.map((item, index) => ({ id: 9100 + index, medical_study_id: item.medical_study_id, modality: studies.find(study => study.id === item.medical_study_id).category, study_name: studies.find(study => study.id === item.medical_study_id).name, region_description: item.region_description, contrast: item.contrast, clinical_notes: item.clinical_notes })) };
    const collection = laboratory ? laboratoryOrders : studyOrders;
    collection[id] = config.method === "put" ? collection[id].map(item => item.id === created.id ? created : item) : [...collection[id], created];
    return ok(config, created);
  }
  throw new Error(`Unexpected ${config.method} ${config.url}`);
}

beforeEach(() => {
  root = createRoot(host); calls = []; deferred = null; deferredPdf = null; fail = null; dirtyStates = [];
  nativeAnchorClick = dom.window.HTMLAnchorElement.prototype.click; dom.window.HTMLAnchorElement.prototype.click = () => {};
  laboratoryOrders = { 42: [labOrder(42)], 77: [labOrder(77, 777)] }; studyOrders = { 42: [studyOrder(42)], 77: [studyOrder(77, 877)] };
  props = { historyId: 42, specialtyId: 3, completed: false, allowAdditional: false, onDirtyChange(value) { dirtyStates.push(value); } };
  api.defaults.adapter = adapter;
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; dom.window.HTMLAnchorElement.prototype.click = nativeAnchorClick; });
after(async () => { await server.close(); dom.window.close(); });

test("compact default hides editors, counts structured orders and keeps summaries visible", async () => {
  await render();
  assert.match(host.textContent, /2 ordenes/); assert.match(host.textContent, /Orden de laboratorio #501/); assert.match(host.textContent, /Orden de estudios #601/);
  assert.equal(input("Buscar pruebas de laboratorio"), null); assert.equal(input("Buscar estudios o procedimientos"), null); assert.ok(button("+ Nueva orden"));
});

test("chooser opens, cancels, and laboratory create preserves grouping, multi-select and payload", async () => {
  await render(); await click(button("+ Nueva orden")); assert.match(host.textContent, /¿Qué desea solicitar/); await click(button("Cancelar")); assert.equal(input("Buscar pruebas de laboratorio"), null);
  await click(button("+ Nueva orden")); await click(button("Laboratorio")); assert.ok(input("Buscar pruebas de laboratorio")); assert.match(host.textContent, /Hematología/); assert.match(host.textContent, /Química/);
  await click(button("Hematología")); await click(button("Química")); const choices = [...host.querySelectorAll('input[type="checkbox"]')]; await click(choices[0]); await click(choices[1]); await change(input("Observaciones generales de laboratorio"), "  Nota nueva  "); await click(button("Guardar orden"));
  const created = calls.find(item => item.method === "post" && item.url === "/clinical-history/42/laboratory-orders");
  assert.deepEqual(payload(created), { items: [{ laboratory_test_id: 31 }, { laboratory_test_id: 32 }], notes: "Nota nueva" }); assert.equal(input("Buscar pruebas de laboratorio"), null); assert.match(host.textContent, /Orden de laboratorio #900/);
});

test("composer de órdenes informa dirty mientras está abierto y conserva dirty ante error", async () => {
  await render();
  assert.equal(dirtyStates.at(-1), false);
  await click(button("+ Nueva orden"));
  assert.equal(dirtyStates.at(-1), true);
  await click(button("Cancelar"));
  assert.equal(dirtyStates.at(-1), false);
  await click(button("+ Nueva orden"));
  await click(button("Laboratorio"));
  await click(button("Hematología"));
  await click(host.querySelector('input[type="checkbox"]'));
  fail = config => config.method === "post";
  await click(button("Guardar orden"));
  assert.equal(dirtyStates.at(-1), true);
  assert.ok(input("Buscar pruebas de laboratorio"));
  fail = null;
  await click(button("Guardar orden"));
  assert.equal(dirtyStates.at(-1), false);
});

test("laboratory categories use one viewport-independent accordion with synchronized counts, chips, and search", async () => {
  await render(); await click(button("+ Nueva orden")); await click(button("Laboratorio"));
  assert.equal(button("Hematología").getAttribute("aria-expanded"), "false"); assert.equal(host.querySelectorAll('input[type="checkbox"]').length, 0);
  await click(button("Hematología")); const hemogram = host.querySelector('input[type="checkbox"]'); await click(hemogram); await click(button("Química")); assert.equal(button("Hematología").getAttribute("aria-expanded"), "true"); assert.equal(button("Química").getAttribute("aria-expanded"), "true"); await click(button("Hematología")); assert.equal(button("Química").getAttribute("aria-expanded"), "true"); await click(button("Hematología"));
  assert.match(host.textContent, /1 prueba seleccionada/); assert.match(host.querySelector('[aria-label="Pruebas de laboratorio seleccionadas"]').textContent, /Hemograma ficticio/); assert.equal(button("Hematología").getAttribute("aria-controls"), "laboratory-category-0"); assert.equal(button("Hematología").querySelector('[aria-label^="1 pruebas seleccionadas"]').textContent, "1");
  await click(button("Hematología")); assert.equal(button("Hematología").getAttribute("aria-expanded"), "false"); assert.equal(host.querySelectorAll('input[type="checkbox"]').length, 1); await click(button("Hematología")); assert.equal(host.querySelector('input[type="checkbox"]').checked, true);
  await click(host.querySelector('[aria-label="Quitar Hemograma ficticio"]')); assert.match(host.textContent, /0 pruebas seleccionadas/); assert.equal(host.querySelector('[aria-label^="1 pruebas seleccionadas"]'), null); assert.equal(host.querySelector('input[type="checkbox"]').checked, false);
  await change(input("Buscar pruebas de laboratorio"), "Glucosa"); assert.equal(button("Química").getAttribute("aria-expanded"), "true"); assert.match(button("Química").closest("section").textContent, /Glucosa ficticia/); assert.doesNotMatch(button("Química").closest("section").textContent, /Hemograma ficticio/); await change(input("Buscar pruebas de laboratorio"), ""); assert.equal(button("Química").getAttribute("aria-expanded"), "true"); await click(button("Química")); await change(input("Buscar pruebas de laboratorio"), "Química"); assert.equal(button("Química").getAttribute("aria-expanded"), "true"); assert.match(button("Química").closest("section").textContent, /Glucosa ficticia/); await change(input("Buscar pruebas de laboratorio"), ""); assert.equal(button("Química").getAttribute("aria-expanded"), "false");
  const catalog = host.querySelector('[data-clinical-orders-editor="laboratory"] div.space-y-2.rounded-lg'); assert.match(host.querySelector('[data-clinical-orders-editor="laboratory"]').className, /safe-area-inset-bottom/); assert.doesNotMatch(catalog.className, /overflow-y-auto/);
});

test("laboratory edit preserves PUT, errors stay in the editor, and PDF remains available", async () => {
  await render(); await click(button("Editar")); assert.equal(input("Observaciones generales de laboratorio").value, "Nota laboratorio");
  fail = config => config.method === "put"; await click(button("Actualizar orden")); assert.match(host.querySelector('[role="alert"]').textContent, /Error de servidor visible/); assert.ok(input("Buscar pruebas de laboratorio"));
  fail = null; await change(input("Observaciones generales de laboratorio"), " Editada "); await click(button("Actualizar orden"));
  const updated = calls.filter(item => item.method === "put" && item.url === "/clinical-history/42/laboratory-orders/501").at(-1); assert.deepEqual(payload(updated), { items: [{ laboratory_test_id: 31 }], notes: "Editada" });
  await click(button("PDF")); assert.ok(calls.some(item => item.method === "get" && item.url === "/laboratory-orders/501/pdf"));
});

test("study editor preserves recommendations, detail fields, exact payload and update", async () => {
  await render(); await click(button("+ Nueva orden")); await click(button("Estudio / procedimiento")); assert.match(host.textContent, /Recomendado/); assert.match([...host.querySelectorAll("label")].find((item) => item.textContent.includes("Ecografía ficticia")).textContent, /Recomendado/); assert.doesNotMatch([...host.querySelectorAll("label")].find((item) => item.textContent.includes("Tomografía ficticia")).textContent, /Recomendado/);
  const choices = [...host.querySelectorAll('input[type="checkbox"]')]; await click(choices[0]); await click(choices[1]); assert.match(host.textContent, /Detalles por estudio seleccionado/); await change(input("Región o descripción para Ecografía ficticia"), " Abdomen "); await change(input("Contraste para Ecografía ficticia"), "yes"); await change(input("Observaciones clínicas para Ecografía ficticia"), " Nota A "); await change(input("Región o descripción para Tomografía ficticia"), " Tórax "); await change(input("Contraste para Tomografía ficticia"), "no"); await change(input("Observaciones clínicas para Tomografía ficticia"), " Nota B "); await change(input("Observaciones generales de estudios"), " General "); await click(button("Guardar orden"));
  const created = calls.find(item => item.method === "post" && item.url === "/clinical-history/42/study-orders"); assert.deepEqual(payload(created), { items: [{ medical_study_id: 41, region_description: "Abdomen", contrast: "yes", clinical_notes: "Nota A" }, { medical_study_id: 42, region_description: "Tórax", contrast: "no", clinical_notes: "Nota B" }], notes: "General" }); assert.equal(input("Buscar estudios o procedimientos"), null);
  const studyCard = [...host.querySelectorAll("article")].find((item) => item.textContent.includes("Orden de estudios #601")); await click(button("Editar", studyCard)); assert.equal(input("Región o descripción para Ecografía ficticia").value, "Abdomen"); await click(button("Actualizar orden")); assert.ok(calls.some(item => item.method === "put" && item.url === "/clinical-history/42/study-orders/601")); const updatedStudyCard = [...host.querySelectorAll("article")].find((item) => item.textContent.includes("Orden de estudios #601")); await click(button("PDF", updatedStudyCard)); assert.ok(calls.some(item => item.url === "/study-orders/601/pdf"));
});

test("completed mode is read-only and only exposes the existing additional endpoints when allowed", async () => {
  await render({ ...props, completed: true, allowAdditional: false }); assert.equal(button("+ Nueva orden adicional"), undefined); assert.equal(button("Editar"), undefined); assert.ok(button("PDF"));
  await render({ ...props, completed: true, allowAdditional: true }); await click(button("+ Nueva orden adicional")); assert.match(host.textContent, /¿Qué desea solicitar/); await click(button("Laboratorio")); await click(button("Hematología")); await click(host.querySelector('input[type="checkbox"]')); await click(button("Guardar orden")); assert.ok(calls.some(item => item.method === "post" && item.url === "/clinical-history/42/laboratory-orders/additional")); assert.match(host.textContent, /Orden adicional/);
  await click(button("+ Nueva orden adicional")); await click(button("Estudio / procedimiento")); await click(host.querySelector('input[type="checkbox"]')); await click(button("Guardar orden")); assert.ok(calls.some(item => item.method === "post" && item.url === "/clinical-history/42/study-orders/additional"));
});

test("history switches reset chooser and both editors, and stale A success or error cannot publish into B", async () => {
  await render(); await click(button("+ Nueva orden")); await render({ ...props, historyId: 77 }); assert.doesNotMatch(host.textContent, /¿Qué desea solicitar/);
  await click(button("+ Nueva orden")); await click(button("Laboratorio")); await render({ ...props, historyId: 42 }); assert.equal(input("Buscar pruebas de laboratorio"), null);
  deferred = []; await render({ ...props, historyId: 42 }); await render({ ...props, historyId: 77 }); assert.match(host.textContent, /#777/); for (const request of deferred) request.resolve(ok(request.config, request.config.url.includes("laboratory-orders") ? [labOrder(42)] : request.config.url.includes("study-orders") ? [studyOrder(42)] : request.config.url === "/laboratory-tests" ? tests : studies)); await settle(); assert.match(host.textContent, /#777/);
  deferred = []; await render({ ...props, historyId: 42 }); await render({ ...props, historyId: 77 }); for (const request of deferred) request.reject(failure("Error stale")); await settle(); assert.doesNotMatch(host.textContent, /Error stale/);
});

test("stale PDF and unmount cannot publish after the active resource is gone", async () => {
  let downloads = 0; const originalClick = dom.window.HTMLAnchorElement.prototype.click; dom.window.HTMLAnchorElement.prototype.click = () => { downloads += 1; };
  try {
    await render(); deferredPdf = {}; await click(button("PDF")); await render({ ...props, historyId: 77 }); await act(async () => deferredPdf.resolve()); await settle(); assert.equal(downloads, 0);
    deferred = []; await render({ ...props, historyId: 42 }); await act(async () => root.unmount()); for (const request of deferred) request.resolve(ok(request.config, [])); await settle();
  } finally { dom.window.HTMLAnchorElement.prototype.click = originalClick; }
});
