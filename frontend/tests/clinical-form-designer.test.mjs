import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Designer } = await server.ssrLoadModule("/src/pages/ClinicalFormDesigner.tsx");
const { default: Runner } = await server.ssrLoadModule("/src/components/clinicalDocuments/ClinicalFormRunner.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
let root, calls, template;
const definition = { appearance: { show_logo: false, logo_data: null, doctor_heading: "Dr. QA", specialty_heading: "", center_heading: "QA", header: "Evaluación QA", subtitle: "", footer: "", primary_color: "#24415c", font: "Helvetica", font_size: 9, density: "normal" }, pages: [
  { page_number: 1, sort_order: 1, title: "General", orientation: "portrait", page_size: "Letter", margins: { top: 12, bottom: 12, left: 12, right: 12 }, sections: [
    { key: "s1", title: "Síntomas", sort_order: 1, printable: true, fields: [
      { key: "dolor", label: "Dolor torácico", type: "yes_no", required: false, label_uppercase: true, placeholder: "", help_text: "", default_value: null, unit: "", options: [], width: 12, row: 1, column: 1, colspan: 6, sort_order: 1, visible: true, printable: true, read_only: false, editable_by: "clinical", data_binding: null, validation: {} },
      { key: "peso", label: "Peso", type: "decimal", required: false, label_uppercase: true, placeholder: "", help_text: "", default_value: null, unit: "kg", options: [], width: 12, row: 2, column: 1, colspan: 6, sort_order: 2, visible: true, printable: true, read_only: false, editable_by: "clinical", data_binding: null, validation: {} },
    ] },
  ] },
  { page_number: 2, sort_order: 2, title: "Conclusión", orientation: "portrait", page_size: "Letter", margins: { top: 12, bottom: 12, left: 12, right: 12 }, sections: [
    { key: "s2", title: "Cierre", sort_order: 1, printable: true, fields: [] },
  ] },
] };
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
beforeEach(() => {
  root = createRoot(host); calls = []; template = { id: 1, name: "Evaluación QA", code: "qa_preop", description: "", document_type: "preoperative", status: "draft", current_version_id: null, current_version: null, draft_version_id: 2, editable_version_id: 2, definition, created_at: "2026-01-01", updated_at: "2026-01-01" };
  api.defaults.adapter = async (config) => {
    calls.push(config);
    if (config.url === "/clinical-forms/templates" && config.method === "get") return response(config, [template]);
    if (config.url === "/clinical-forms/assignments") return response(config, []);
    if (config.url === "/centers") return response(config, [{ id: 4, name: "CEMER" }]);
    if (config.url === "/clinical-catalog/specialties") return response(config, [{ id: 5, name: "Cardiología" }]);
    if (config.url === "/users") return response(config, [{ id: 3, full_name: "Secretaria QA", roles: ["secretary"] }]);
    if (config.url === "/clinical-forms/templates/1" && config.method === "get") return response(config, template);
    if (config.url === "/clinical-forms/templates/1/versions/2" && config.method === "put") { template = { ...template, definition: JSON.parse(config.data) }; return response(config, template); }
    if (config.url === "/clinical-forms/templates/1/versions/2/publish") { template = { ...template, status: "published", current_version: 1, current_version_id: 2, draft_version_id: null }; return response(config, template); }
    if (config.url === "/clinical-forms/capabilities/secretaries/3") return response(config, { start_preoperative: false, start_physical_exam: false, prepare_administrative: false });
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });
async function settle() { for (let i = 0; i < 5; i++) await act(async () => { await Promise.resolve(); }); }
async function click(label) { const button = [...host.querySelectorAll("button")].find((item) => item.textContent.includes(label)); assert.ok(button, label); await act(async () => button.click()); await settle(); }

test("proforma usa páginas numeradas y controles compactos con orden de teclado estable", async () => {
  const values = {};
  await act(async () => root.render(h(Runner, { definition, values, profile: { patient_name: "Paciente ficticio" }, documentDate: "2026-01-01", onChange(key, value) { values[key] = value; }, readOnly: false })));
  assert.match(host.textContent, /Página 1/);
  assert.match(host.textContent, /DOLOR TORÁCICO/);
  assert.equal(host.querySelectorAll('button[aria-pressed]').length, 2);
  assert.equal(host.querySelector('input[type="number"]').closest("label").textContent.includes("kg"), true);
  const controls = [...host.querySelectorAll('fieldset button, input[type="number"]')];
  assert.match(controls[0].textContent, /Sí/);
  assert.equal(controls.at(-1).type, "number");
  await click("Página 2");
  assert.match(host.textContent, /Conclusión/);
  assert.doesNotMatch(host.textContent, /DOLOR TORÁCICO/);
});

test("campos predeterminados compactan números y sí/no sin estrechar narrativas", async () => {
  const makeField = (key, type, sort_order) => ({ ...definition.pages[0].sections[0].fields[0], key, label: key,
    type, row: sort_order, sort_order, column: 1, colspan: 12, width: 12 });
  const compact = structuredClone(definition);
  compact.pages[0].sections[0].fields = [
    makeField("g", "integer", 1), makeField("p", "integer", 2), makeField("c", "integer", 3), makeField("a", "integer", 4),
    makeField("dolor", "yes_no", 5), makeField("reposo", "yes_no", 6), makeField("corazon", "text_long", 7),
  ];
  await act(async () => root.render(h(Runner, { definition: compact, values: {}, documentDate: "2026-01-01", onChange() {}, readOnly: false })));
  const grid = host.querySelector('[data-layout="default"]');
  assert.ok(grid);
  assert.deepEqual([...grid.querySelectorAll("[data-field-key]")].map((item) => item.dataset.fieldKey),
    ["g", "p", "c", "a", "dolor", "reposo", "corazon"]);
  assert.equal(grid.querySelector('[data-field-key="g"]').style.getPropertyValue("--desktop-span"), "3");
  assert.equal(grid.querySelector('[data-field-key="dolor"]').style.getPropertyValue("--mobile-span"), "1");
  assert.equal(grid.querySelector('[data-field-key="corazon"]').style.getPropertyValue("--desktop-span"), "12");
  assert.equal(grid.querySelector('[data-field-key="corazon"]').style.getPropertyValue("--mobile-span"), "2");
  assert.equal(grid.querySelector('fieldset button').classList.contains("clinical-binary-option"), true);
  const css = await readFile(new URL("../src/components/clinicalDocuments/clinicalFormRunner.css", import.meta.url), "utf8");
  assert.match(css, /\.clinical-binary-option\s*\{[^}]*min-height:\s*2\.75rem/s);
  assert.match(css, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(css, /@container clinical-fields \(max-width: 15rem\)/);
  assert.match(css, /@container clinical-fields \(min-width: 32rem\)[\s\S]*repeat\(12, minmax\(0, 1fr\)\)/);
  assert.match(css, /@container clinical-fields \(min-width: 44rem\)/);
});

test("diseñador conserva fila, columna y orden de tab; metadata incompleta usa ancho seguro", async () => {
  const designed = structuredClone(definition);
  const fields = designed.pages[0].sections[0].fields;
  fields[0] = { ...fields[0], row: 1, column: 1, colspan: 6 };
  fields[1] = { ...fields[1], row: 1, column: 7, colspan: 6 };
  await act(async () => root.render(h(Runner, { definition: designed, values: {}, documentDate: "2026-01-01", onChange() {}, readOnly: false })));
  const row = host.querySelector('[data-layout="designed"] [data-row="1"]');
  assert.ok(row);
  assert.equal(row.querySelector('[data-field-key="peso"]').style.getPropertyValue("--desktop-column"), "7");
  assert.equal(row.querySelector('[data-field-key="peso"]').style.getPropertyValue("--desktop-span"), "6");
  assert.deepEqual([...row.querySelectorAll("[data-field-key]")].map((item) => item.dataset.fieldKey), ["dolor", "peso"]);
  assert.equal([...row.querySelectorAll('button, input')].at(-1).type, "number");
  designed.pages[0].sections[0].fields[1].width = 4;
  await act(async () => root.render(h(Runner, { definition: designed, values: {}, documentDate: "2026-01-01", onChange() {}, readOnly: false })));
  assert.equal(host.querySelector('[data-field-key="peso"]').style.getPropertyValue("--desktop-span"), "4");
  designed.pages[0].sections[0].fields[1].column = undefined;
  await act(async () => root.render(h(Runner, { definition: designed, values: {}, documentDate: "2026-01-01", onChange() {}, readOnly: false })));
  assert.ok(host.querySelector('[data-layout="legacy"]'));
  assert.equal(host.querySelector('[data-field-key="peso"]').style.getPropertyValue("--desktop-span"), "12");
});

test("composición genérica empareja bloques binarios predeterminados sin reordenar campos ni datos", async () => {
  const compact = structuredClone(definition);
  const base = definition.pages[0].sections[0].fields[0];
  const field = (key, type, order) => ({ ...base, key, label: key, type,
    row: order, sort_order: order, column: 1, colspan: 12, width: 12 });
  const section = (key, order, fields) => ({ key, title: key, sort_order: order, printable: true, fields });
  compact.pages[0].sections = [
    section("general", 1, [field("diagnostico", "text_long", 1), field("procedimiento", "text_long", 2),
      ...["g", "p", "c", "a"].map((key, index) => field(key, "integer", index + 3))]),
    section("bloque_a", 2, [field("a1", "yes_no", 1), field("a2", "yes_no", 2)]),
    section("bloque_b", 3, [field("b1", "yes_no", 1), field("b2", "checkbox", 2), field("b3", "text_long", 3)]),
    section("bloque_c", 4, [field("c1", "yes_no", 1), { ...field("c2", "yes_no", 2), label: "Electrocardiográficamente" }, field("c3", "text_long", 3)]),
  ];
  const original = structuredClone(compact);
  const changes = [];
  await act(async () => root.render(h(Runner, { definition: compact, values: { a1: "yes", b1: "no" }, documentDate: "2026-01-01", onChange: (...args) => changes.push(args), readOnly: false })));
  assert.equal(host.querySelectorAll(".clinical-form-section--paired").length, 2);
  assert.ok(host.querySelector('[data-section-key="bloque_c"].clinical-form-section--split'));
  const narrative = host.querySelector('[data-field-key="diagnostico"]');
  assert.equal(narrative.style.getPropertyValue("--desktop-span"), "6");
  assert.equal(narrative.style.getPropertyValue("--mobile-span"), "2");
  assert.equal(narrative.style.getPropertyValue("--tablet-span"), "6");
  assert.equal(host.querySelector('[data-field-key="g"]').style.getPropertyValue("--tablet-span"), "4");
  assert.equal(host.querySelector('[data-field-key="c2"]').dataset.longLabel, "true");
  assert.equal(host.querySelector('[data-field-key="c1"]').dataset.longLabel, undefined);
  assert.deepEqual([...host.querySelectorAll("[data-field-key]")].map((item) => item.dataset.fieldKey),
    compact.pages[0].sections.flatMap((item) => item.fields.map((entry) => entry.key)));
  assert.equal(host.querySelector('[data-field-key="a1"] button').getAttribute("aria-pressed"), "true");
  assert.equal(host.querySelector('[data-field-key="b1"] button:last-child').getAttribute("aria-pressed"), "true");
  await act(async () => host.querySelector('[data-field-key="a2"] button').click());
  assert.deepEqual(changes, [["a2", "yes"]]);
  assert.deepEqual(compact, original);
});

test("coordenadas explícitas gobiernan narrativas y no se compactan como bloques predeterminados", async () => {
  const designed = structuredClone(definition);
  const base = definition.pages[0].sections[0].fields[0];
  designed.pages[0].sections[0].fields = [
    { ...base, key: "narrativa_a", type: "text_long", row: 1, column: 1, width: 6, colspan: 6 },
    { ...base, key: "narrativa_b", type: "text_long", row: 1, column: 7, width: 6, colspan: 6 },
    { ...base, key: "narrativa_completa", type: "text_long", row: 2, column: 1, width: 12, colspan: 12 },
  ];
  await act(async () => root.render(h(Runner, { definition: designed, values: {}, documentDate: "2026-01-01", onChange() {}, readOnly: false })));
  const a = host.querySelector('[data-field-key="narrativa_a"]');
  assert.equal(a.style.getPropertyValue("--desktop-span"), "6");
  assert.equal(a.style.getPropertyValue("--mobile-span"), "2");
  assert.equal(host.querySelector('[data-field-key="narrativa_b"]').style.getPropertyValue("--desktop-column"), "7");
  assert.equal(host.querySelector('[data-field-key="narrativa_completa"]').style.getPropertyValue("--desktop-span"), "12");
  assert.equal(host.querySelectorAll(".clinical-form-section--paired").length, 0);
});

test("administración lista, edita borrador y publica sin edición directa de versión publicada", async () => {
  await act(async () => root.render(h(Designer)));
  await settle();
  assert.match(host.textContent, /Plantillas clínicas/);
  await click("Editar / Ver");
  assert.match(host.textContent, /Página 1/);
  assert.match(host.textContent, /Paleta de campos/);
  await click("+ Texto corto");
  await click("Guardar borrador");
  assert.equal(calls.some((item) => item.url === "/clinical-forms/templates/1/versions/2" && item.method === "put"), true);
  await click("Publicar versión");
  assert.equal(calls.some((item) => item.url.endsWith("/publish")), true);
});

test("vista previa usa paciente ficticio y no carga datos clínicos reales", async () => {
  await act(async () => root.render(h(Designer)));
  await settle(); await click("Editar / Ver"); await click("Vista previa");
  assert.match(host.textContent, /Paciente de ejemplo/);
  assert.equal(calls.some((item) => item.url?.startsWith("/patients/")), false);
});
