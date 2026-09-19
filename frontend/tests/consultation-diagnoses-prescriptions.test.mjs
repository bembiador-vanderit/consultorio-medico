import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";
import { diagnosisFixture, prescriptionFixture } from "./fixtures/clinical.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: DiagnosesModule } = await server.ssrLoadModule("/src/components/consultation/DiagnosesModule.tsx");
const { default: PrescriptionsModule } = await server.ssrLoadModule("/src/components/consultation/PrescriptionsModule.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
let root, props, Component, calls, list, errors, deliveries, respond, pdfCount;
const ok = (config, data) => ({ data, status: 200, statusText: "OK", headers: {}, config });
const failure = () => Object.assign(new Error("conflict"), { response: { status: 409, data: { detail: "Conflicto visible" } } });
const button = text => [...host.querySelectorAll("button")].find(item => item.textContent === text);
const control = label => [...host.querySelectorAll("label")].find(item => item.textContent === label)?.querySelector("input,textarea");
const description = () => host.querySelector('[placeholder="Descripción del diagnóstico"]');
const code = () => host.querySelector('[placeholder="Código CIE-10"]');
const primary = () => host.querySelector('[type="checkbox"]');
async function render() { await act(async () => root.render(h("div", {}, h(Component, props), errors.at(-1) && h("div", { role: "alert" }, errors.at(-1))))); }
async function change(input, value) {
  assert.ok(input);
  await act(async () => {
    const prototype = input.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(input, value);
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}
async function click(target) { assert.ok(target); await act(async () => target.click()); await render(); }
async function mount(kind, initial = [], extra = {}) {
  Component = kind === "diagnoses" ? DiagnosesModule : PrescriptionsModule;
  list = structuredClone(initial);
  props = { episodeId: 81, historyId: 42, completed: false, [kind]: list,
    onChange(update) { deliveries++; list = typeof update === "function" ? update(list) : update; props = { ...props, [kind]: list }; },
    onError(message) { errors.push(message); }, downloadingPrescriptionPdf: false, downloadPrescriptionPdf() { pdfCount++; }, ...extra };
  await render();
}
beforeEach(() => {
  root = createRoot(host); calls = []; errors = []; deliveries = 0; pdfCount = 0;
  respond = config => ok(config, { ...(config.url.includes("diagnoses") ? diagnosisFixture : prescriptionFixture), ...JSON.parse(config.data || "{}"), id: 90 });
  api.defaults.adapter = async config => { calls.push(config); return respond(config); };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });

test("diagnoses: canonical render, primary replacement, exact POST and canonical response", async () => {
  await mount("diagnoses", [diagnosisFixture]);
  assert.match(host.textContent, /Diagnóstico ficticio/); assert.equal(primary().checked, false); assert.equal(calls.length, 0);
  await change(description(), "  Hallazgo ficticio  "); await change(code(), " Z99.9 "); await click(primary());
  respond = config => ok(config, { ...diagnosisFixture, id: 90, description: "Canónico", is_primary: true });
  await click(button("Agregar"));
  assert.equal(calls.length, 1); assert.equal(calls[0].method, "post"); assert.equal(calls[0].url, "/clinical-history/42/diagnoses");
  assert.deepEqual(JSON.parse(calls[0].data), { description: "Hallazgo ficticio", icd10_code: "Z99.9", is_primary: true });
  assert.deepEqual(list.map(item => [item.id, item.is_primary]), [[90, true], [diagnosisFixture.id, false]]);
  assert.match(host.textContent, /Canónico/); assert.equal(description().value, ""); assert.equal(code().value, ""); assert.equal(primary().checked, false);
});
test("diagnoses: blank ICD is null, secondary appends, delete does not promote", async () => {
  await mount("diagnoses", [diagnosisFixture]); await change(description(), "Secundario"); await click(button("Agregar"));
  assert.deepEqual(JSON.parse(calls[0].data), { description: "Secundario", icd10_code: null, is_primary: false });
  assert.equal(list.at(-1).id, 90);
  await click(button("Eliminar")); assert.equal(calls.at(-1).method, "delete"); assert.equal(calls.at(-1).url, `/clinical-history/42/diagnoses/${diagnosisFixture.id}`);
  assert.equal(list.length, 1); assert.equal(list[0].is_primary, false);
});
test("diagnoses: rerender preserves all input; episode and history changes reset", async () => {
  await mount("diagnoses"); await change(description(), "Edición A"); await change(code(), "Z00"); await click(primary());
  props = { ...props, diagnoses: [] }; await render();
  assert.equal(description().value, "Edición A"); assert.equal(code().value, "Z00"); assert.equal(primary().checked, false);
  props = { ...props, episodeId: 82, historyId: 77, diagnoses: [diagnosisFixture] }; await render();
  assert.equal(description().value, ""); assert.equal(code().value, ""); assert.equal(primary().checked, false);
  await change(description(), "Edición B"); props = { ...props, historyId: 78, diagnoses: [] }; await render();
  assert.equal(description().value, ""); assert.equal(primary().checked, true);
});
test("prescriptions: canonical render and exact create payload with all eight fields", async () => {
  await mount("prescriptions", [prescriptionFixture]); assert.match(host.textContent, /Medicamento ficticio/); assert.equal(calls.length, 0);
  for (const [label, value] of [["Medicamento *", " Nuevo "], ["Presentación", " Tableta "], ["Dosis", " 1 "], ["Vía", " Oral "], ["Frecuencia", " Diaria "], ["Duración", " 2 días "], ["Cantidad", "2"], ["Indicaciones", " Con comida "]]) await change(control(label), value);
  respond = config => ok(config, { ...prescriptionFixture, id: 90, medication: "Canónico" });
  await click(button("Agregar medicamento"));
  assert.equal(calls[0].method, "post"); assert.equal(calls[0].url, "/clinical-history/42/prescriptions");
  assert.deepEqual(JSON.parse(calls[0].data), { medication: "Nuevo", presentation: "Tableta", dose: "1", route: "Oral", frequency: "Diaria", duration: "2 días", quantity: 2, instructions: "Con comida" });
  assert.equal(list.length, 2); assert.match(host.textContent, /Canónico/); assert.equal(control("Medicamento *").value, "");
});
test("prescriptions: edit, rerender, exact PUT, canonical adoption and cancel", async () => {
  await mount("prescriptions", [prescriptionFixture]); await click(button("Editar"));
  assert.equal(control("Medicamento *").value, prescriptionFixture.medication);
  await change(control("Dosis"), " 20 mg "); props = { ...props, prescriptions: list.map(item => ({ ...item })) }; await render();
  assert.equal(control("Dosis").value, " 20 mg "); assert.ok(button("Guardar cambios"));
  respond = config => ok(config, { ...prescriptionFixture, dose: "Dosis canónica" });
  await click(button("Guardar cambios"));
  assert.equal(calls[0].method, "put"); assert.equal(calls[0].url, `/clinical-history/42/prescriptions/${prescriptionFixture.id}`);
  const { id, clinical_history_id, created_at, updated_at, ...expected } = prescriptionFixture;
  assert.deepEqual(JSON.parse(calls[0].data), { ...expected, dose: "20 mg" });
  assert.equal(list.length, 1); assert.match(host.textContent, /Dosis canónica/); assert.ok(button("Agregar medicamento"));
  await click(button("Editar")); await change(control("Medicamento *"), "Temporal"); await click(button("Cancelar"));
  assert.equal(control("Medicamento *").value, ""); assert.equal(calls.length, 1);
});
for (const quantity of [null, 0, 3]) test(`prescriptions: empty/null semantics and quantity ${quantity}`, async () => {
  await mount("prescriptions"); await change(control("Medicamento *"), " Prueba "); await change(control("Presentación"), "   ");
  await change(control("Cantidad"), "9"); await change(control("Cantidad"), quantity === null ? "" : String(quantity));
  await click(button("Agregar medicamento"));
  assert.deepEqual(JSON.parse(calls[0].data), { medication: "Prueba", presentation: null, dose: null, route: null, frequency: null, duration: null, quantity, instructions: null });
});
test("prescriptions: episode change drops edit ID and previous form; canonical B renders", async () => {
  await mount("prescriptions", [prescriptionFixture]); await click(button("Editar")); await change(control("Dosis"), "Edición A");
  props = { ...props, episodeId: 82, historyId: 77, prescriptions: [{ ...prescriptionFixture, id: 88, medication: "Receta B" }] }; await render();
  assert.equal(control("Dosis").value, ""); assert.equal(button("Guardar cambios"), undefined); assert.match(host.textContent, /Receta B/);
  await change(control("Medicamento *"), "Nueva B"); await click(button("Agregar medicamento"));
  assert.equal(calls[0].method, "post"); assert.equal(calls[0].url, "/clinical-history/77/prescriptions");
});
test("prescriptions: delete retains existing in-progress edit semantics", async () => {
  await mount("prescriptions", [prescriptionFixture]); await click(button("Editar")); await click(button("Eliminar"));
  assert.equal(calls[0].method, "delete"); assert.equal(calls[0].url, `/clinical-history/42/prescriptions/${prescriptionFixture.id}`);
  assert.equal(list.length, 0); assert.equal(control("Medicamento *").value, prescriptionFixture.medication); assert.ok(button("Guardar cambios"));
});
for (const kind of ["diagnoses", "prescriptions"]) {
  const fixture = kind === "diagnoses" ? diagnosisFixture : prescriptionFixture;
  const input = () => kind === "diagnoses" ? description() : control("Medicamento *");
  const save = () => button(kind === "diagnoses" ? "Agregar" : "Agregar medicamento");
  test(`${kind}: missing history disables creation; completed retains reading only`, async () => {
    await mount(kind, [], { historyId: null }); assert.equal(input().disabled, true); assert.equal(save().disabled, true);
    props = { ...props, historyId: 42, completed: true, [kind]: [fixture] }; await render();
    assert.equal(host.querySelector("input,textarea"), null); assert.equal(button("Eliminar"), undefined); assert.equal(button("Editar"), undefined);
    assert.match(host.textContent, new RegExp(kind === "diagnoses" ? fixture.description : fixture.medication));
    if (kind === "prescriptions") { assert.equal(button("Descargar receta PDF").disabled, false); await click(button("Descargar receta PDF")); assert.equal(pdfCount, 1); }
    assert.equal(calls.length, 0);
  });
  for (const operation of ["create", "delete", ...(kind === "prescriptions" ? ["edit"] : [])]) test(`${kind}: ${operation} error visible, no retry or fake adoption`, async () => {
    await mount(kind, [fixture]);
    if (operation === "edit") await click(button("Editar"));
    if (operation !== "delete") await change(input(), "Edición pendiente");
    respond = () => { throw failure(); };
    await click(operation === "delete" ? button("Eliminar") : operation === "edit" ? button("Guardar cambios") : save());
    assert.match(host.querySelector('[role="alert"]').textContent, /Conflicto visible/); assert.equal(calls.length, 1); assert.equal(deliveries, 0); assert.deepEqual(list, [fixture]);
    if (operation !== "delete") assert.equal(input().value, "Edición pendiente");
  });
  for (const operation of ["create", "delete", ...(kind === "prescriptions" ? ["edit"] : [])]) {
    for (const outcome of ["success", "error"]) test(`${kind}: late ${operation} ${outcome} cannot reach B`, async () => {
      await mount(kind, [fixture]); let finish;
      respond = config => new Promise((resolve, reject) => { finish = () => outcome === "success" ? resolve(ok(config, fixture)) : reject(failure()); });
      if (operation === "edit") await click(button("Editar"));
      if (operation !== "delete") await change(input(), "Pendiente A");
      await click(operation === "delete" ? button("Eliminar") : operation === "edit" ? button("Guardar cambios") : save());
      props = { ...props, episodeId: 82, historyId: 77, [kind]: [] }; await render();
      const errorCount = errors.length;
      await act(async () => finish()); await render();
      assert.equal(deliveries, 0); assert.equal(errors.length, errorCount); assert.equal(input().value, ""); assert.equal(calls.length, 1);
    });
  }
  test(`${kind}: unmount ignores outstanding write`, async () => {
    await mount(kind); let finish;
    respond = config => new Promise(resolve => { finish = () => resolve(ok(config, fixture)); });
    await change(input(), "Pendiente"); await click(save()); await act(async () => root.unmount());
    await act(async () => finish()); assert.equal(deliveries, 0);
  });
}
