import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom, setDesktop } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Patients, patientAge } = await server.ssrLoadModule("/src/pages/Patients.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const adapter = api.defaults.adapter;
const host = document.getElementById("root");
const a = { id: 1, first_name: "Ana", last_name: "Ficticia", date_of_birth: "1990-09-15", phone: "8095550001", email: "ana@example.test", created_at: "2026-01-01T00:00:00", selection_token: "fixture-selection-proof" };
const b = { id: 2, first_name: "Bruno", last_name: "Ficticio", date_of_birth: "2000-01-01", phone: null, email: null, created_at: "2026-01-01T00:00:00" };
let root, requests, records, scheduled, changed, response;
beforeEach(() => {
  root = createRoot(host); setDesktop(true);
  requests = []; records = [a, b]; scheduled = null; changed = 0; response = null;
  api.defaults.adapter = async (config) => {
    requests.push(config);
    let data;
    if (response) { const result = await response(config); if (result !== undefined) return { data: result, status: 200, statusText: "OK", headers: {}, config }; }
    if (config.url === "/patients" && config.method === "get") data = records;
    else if (config.url === "/insurance/companies") data = [{ id: 3, name: "ARS ficticia", is_active: true }];
    else if (config.url.startsWith("/insurance/patients/")) data = [{ id: 4, insurance_company_id: 3, insurance_company_name: "ARS ficticia", member_number: "FICTIONAL", plan_name: null, is_primary: true, is_active: true }];
    else if (config.url.startsWith("/clinical-history/patients/")) data = [];
    else if (config.url === "/patients/identity-search") data = [];
    else if (config.method === "put") { data = { ...a, ...JSON.parse(config.data) }; records = [data, b]; }
    else if (config.url === "/patients" && config.method === "post") data = { ...b, id: 8, ...JSON.parse(config.data), selection_token: "fixture-new-proof" };
    else throw new Error(`Unexpected endpoint ${config.url}`);
    return { data, status: 200, statusText: "OK", headers: {}, config };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = adapter; });
after(async () => { await server.close(); dom.window.close(); });

async function mount(roles = ["doctor"]) { await act(async () => root.render(h(Patients, { user: { id: 9, full_name: "Personal ficticio", roles, is_active: true }, onBack() {}, onPatientChanged() { changed++; }, onScheduleAppointment(value) { scheduled = value; } }))); }
async function click(element) { assert.ok(element); await act(async () => { element.focus(); element.click(); }); }
const button = (label, scope = document) => [...scope.querySelectorAll("button")].find((item) => item.textContent.trim() === label);
const field = (label, scope = document) => { const labels = [...scope.querySelectorAll("label")]; const node = labels.find((item) => item.textContent.trim() === label) ?? labels.find((item) => item.textContent.startsWith(label)); assert.ok(node, label); return document.getElementById(node.htmlFor); };
const panel = () => [...document.querySelectorAll("dialog[open]")].at(-1);
async function value(control, next) { await act(async () => { Object.getOwnPropertyDescriptor(control.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype, "value").set.call(control, next); control.dispatchEvent(new dom.window.Event(control.tagName === "SELECT" ? "change" : "input", { bubbles: true })); }); }
async function submit(form) { await act(async () => form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }))); }
async function select() { await click(host.querySelector(".patients-row")); }
const mainRequests = () => requests.filter((item) => item.url === "/patients" && item.method === "get");
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }

test("initial workspace uses one main request and only real identity fields", async () => {
  await mount();
  assert.equal(host.querySelector("h1").textContent, "Pacientes");
  assert.equal(host.querySelectorAll(".patients-row").length, 2);
  assert.match(host.textContent, /Selecciona un paciente/);
  assert.equal(mainRequests().length, 1); assert.equal(mainRequests()[0].params.limit, 100);
  assert.equal(requests.length, 1);
  assert.equal(host.querySelector("table"), null);
  assert.doesNotMatch(host.textContent, /Última visita|Cédula|Sexo|Próxima cita/);
});
test("loading replaces rows until the main request resolves", async () => {
  const pending = deferred(); response = (config) => config.url === "/patients" ? pending.promise : undefined;
  await mount(); assert.match(host.querySelector('[role="status"]').textContent, /Cargando pacientes/); assert.equal(host.querySelector(".patients-row"), null);
  await act(async () => pending.resolve([a])); assert.equal(host.querySelectorAll(".patients-row").length, 1);
});
test("empty registry invites authorized existing registration flow", async () => { records = []; await mount(); assert.match(host.textContent, /No hay pacientes registrados/); await click(button("+ Nuevo paciente", host.querySelector(".atlas-empty"))); assert.ok(panel()); });
test("server search and clear retain the existing query and limit contract", async () => {
  await mount(); await value(field("Buscar pacientes"), "  Ana  "); await submit(host.querySelector(".patients-search"));
  assert.equal(mainRequests().at(-1).params.query, "Ana"); assert.equal(mainRequests().at(-1).params.limit, 100);
  await click(button("Limpiar")); assert.equal(field("Buscar pacientes").value, ""); assert.equal(mainRequests().at(-1).params.query, undefined);
});
test("no results differs from empty registry", async () => { await mount(); records = []; await value(field("Buscar pacientes"), "No existe"); await submit(host.querySelector("form")); assert.match(host.textContent, /No hay resultados para esta búsqueda/); assert.doesNotMatch(host.textContent, /No hay pacientes registrados/); });
test("backend rejection shows error, hides stale patient and supports retry", async () => {
  await mount(); await select(); response = () => { throw { response: { status: 403, data: { detail: "No tiene autorización" } } }; };
  await click(button("Buscar")); assert.match(host.querySelector('[role="alert"]').textContent, /No tiene autorización/); assert.equal(host.querySelector(".patients-row"), null); assert.equal(button("Agendar cita"), undefined);
  response = null; await click(button("Reintentar")); assert.equal(host.querySelectorAll(".patients-row").length, 2);
});
test("stale search responses do not replace newer results", async () => {
  await mount(); const old = deferred(); const fresh = deferred();
  response = (config) => config.url === "/patients" ? config.params.query === "old" ? old.promise : fresh.promise : undefined;
  await value(field("Buscar pacientes"), "old"); await submit(host.querySelector("form")); await value(field("Buscar pacientes"), "fresh"); await submit(host.querySelector("form"));
  await act(async () => fresh.resolve([b])); await act(async () => old.resolve([a]));
  assert.match(host.querySelector(".patients-row").textContent, /Bruno/); assert.doesNotMatch(host.querySelector(".patients-list").textContent, /Ana/);
});
test("selection reveals correct details without a new request", async () => {
  await mount(); await select();
  assert.equal(host.querySelector(".patients-row").getAttribute("aria-pressed"), "true");
  assert.match(host.querySelector(".patients-detail").textContent, /Ana Ficticia/); assert.match(host.querySelector(".patients-detail").textContent, /ana@example.test/);
  assert.equal(requests.length, 1); await click(host.querySelectorAll(".patients-row")[1]);
  assert.match(host.querySelector(".patients-detail").textContent, /Sin teléfono registrado/); assert.doesNotMatch(host.querySelector(".patients-detail").textContent, /ana@example.test/);
});
test("age is calculated correctly before/on birthday, leap dates and invalid/future DOB", () => {
  assert.equal(patientAge("1990-09-15", new Date(2026, 8, 14)), 35); assert.equal(patientAge("1990-09-15", new Date(2026, 8, 15)), 36);
  assert.equal(patientAge("2000-02-29", new Date(2025, 1, 28)), 24); assert.equal(patientAge("2000-02-29", new Date(2025, 2, 1)), 25);
  assert.equal(patientAge("invalid"), null); assert.equal(patientAge("2999-01-01"), null);
});
for (const roles of [["doctor"], ["secretary"], ["admin"], ["doctor", "admin"], ["doctor", "secretary"]]) {
  test(`actions preserve real flows for ${roles.join("+")} and clinical guard`, async () => {
    await mount(roles); await select();
    for (const label of ["Agendar cita", "Editar", "Seguro"]) assert.ok(button(label));
    assert.equal(Boolean(button("Historia clínica")), roles.includes("doctor"));
    assert.equal(requests.length, 1);
  });
}
test("doctor history loads only selected patient when requested", async () => {
  await mount(); await select(); await click(button("Historia clínica"));
  assert.match(panel().textContent, /Historia clínica/);
  assert.equal(requests.filter((item) => item.url.startsWith("/clinical-history/")).length, 1);
  assert.equal(requests.at(-1).url, "/clinical-history/patients/1");
  await click(document.querySelector('[aria-label="Cerrar historia clínica"]')); assert.equal(panel(), undefined);
});
test("insurance loads selected patient only and preserves existing panel flow", async () => {
  await mount(["secretary"]); await select(); await click(button("Seguro"));
  assert.match(panel().textContent, /FICTIONAL/); assert.ok(button("Agregar seguro")); assert.ok(button("Desactivar"));
  assert.equal(requests.filter((item) => item.url.startsWith("/insurance/patients/")).length, 1);
  assert.equal(button("Nueva ARS"), undefined);
});
test("admin insurance retains company management and accessible fields", async () => {
  await mount(["admin"]); await select(); await click(button("Seguro")); assert.ok(button("Nueva ARS")); assert.ok(field("Nombre de la ARS"));
});
test("schedule callback preserves full patient and selection proof", async () => { await mount(); await select(); await click(button("Agendar cita")); assert.equal(scheduled.id, a.id); assert.equal(scheduled.selection_token, a.selection_token); });
test("new registration keeps first appointment proof and saving state", async () => {
  await mount(); await click(button("+ Nuevo paciente")); const form = panel().querySelector("form");
  for (const [label, next] of [["Nombre", "Nuevo"], ["Apellido", "Ficticio"], ["Fecha de nacimiento", "2000-01-01"]]) await value(field(label, panel()), next);
  const pending = deferred(); response = (config) => config.url === "/patients" && config.method === "post" ? pending.promise : undefined;
  await submit(form); assert.ok(button("Guardando...").disabled); assert.equal(scheduled, null);
  await act(async () => pending.resolve({ ...b, id: 8, selection_token: "fixture-new-proof" }));
  assert.equal(scheduled.selection_token, "fixture-new-proof"); assert.equal(changed, 1); assert.equal(panel(), undefined);
});
test("edit omits unchanged insurance and retains selected context after save", async () => {
  await mount(); await select(); await click(button("Editar")); await value(field("Teléfono", panel()), "8095550099"); await submit(panel().querySelector("form"));
  const payload = JSON.parse(requests.find((item) => item.method === "put").data);
  assert.equal(Object.hasOwn(payload, "insurance"), false); assert.equal(Object.hasOwn(payload, "has_insurance"), false);
  assert.match(host.querySelector(".patients-detail").textContent, /8095550099/); assert.equal(changed, 1);
  await click(button("Agendar cita")); assert.equal(scheduled.selection_token, a.selection_token);
});
test("insurance load failure allows identity edit with insurance omitted", async () => {
  await mount(); await select(); response = (config) => { if (config.url.startsWith("/insurance/")) throw { response: { data: { detail: "Carga de seguro fallida" } } }; };
  await click(button("Editar")); assert.match(panel().textContent, /Carga de seguro fallida/); assert.ok(field("No", panel()).disabled);
  await value(field("Teléfono", panel()), "8095550099"); await submit(panel().querySelector("form"));
  const payload = JSON.parse(requests.find((item) => item.method === "put").data); assert.equal(Object.hasOwn(payload, "has_insurance"), false);
});
test("explicit opt-out preserves false meaning", async () => {
  await mount(); await select(); await click(button("Editar")); await click(field("No", panel())); await submit(panel().querySelector("form"));
  assert.equal(JSON.parse(requests.find((item) => item.method === "put").data).has_insurance, false);
});
test("explicit insurance change sends a valid update object", async () => {
  await mount(); await select(); await click(button("Editar")); await value(field("Número de afiliado", panel()), "NEW-FICTIONAL"); await submit(panel().querySelector("form"));
  const payload = JSON.parse(requests.find((item) => item.method === "put").data);
  assert.equal(payload.has_insurance, true); assert.equal(payload.insurance.member_number, "NEW-FICTIONAL"); assert.equal(payload.insurance.insurance_company_id, 3);
});
test("closing edit keeps search, selected patient and main request count", async () => {
  await mount(); await value(field("Buscar pacientes"), "Ana"); await submit(host.querySelector("form")); await select();
  const count = mainRequests().length; await click(button("Editar")); await click(button("Cancelar"));
  assert.equal(field("Buscar pacientes").value, "Ana"); assert.equal(mainRequests().length, count); assert.match(host.querySelector(".patients-detail").textContent, /Ana Ficticia/);
});
test("API conflict remains visible in form without losing edits", async () => {
  await mount(); await select(); await click(button("Editar"));
  response = (config) => { if (config.method === "put") throw { response: { status: 409, data: { detail: "Ya existe un paciente con esa fecha de nacimiento e identificador" } } }; };
  await value(field("Teléfono", panel()), "8095550099"); await submit(panel().querySelector("form"));
  assert.match(panel().querySelector('[role="alert"]').textContent, /Ya existe un paciente/); assert.equal(field("Teléfono", panel()).value, "8095550099"); assert.equal(changed, 0);
});
test("existing identity reuse preserves server token without posting duplicate", async () => {
  await mount(); response = (config) => config.url === "/patients/identity-search" ? [{ ...a, phone_masked: "***0001", email_masked: null }] : undefined;
  await click(button("+ Nuevo paciente"));
  for (const [label, next] of [["Nombre", "Ana"], ["Apellido", "Ficticia"], ["Fecha de nacimiento", a.date_of_birth], ["Teléfono", a.phone]]) await value(field(label, panel()), next);
  await submit(panel().querySelector("form")); await click([...panel().querySelectorAll("button")].find((item) => item.textContent.startsWith("Usar Ana")));
  assert.equal(scheduled.selection_token, a.selection_token); assert.equal(requests.some((item) => item.url === "/patients" && item.method === "post"), false);
});
test("mobile detail and nested form close with Escape/cancel and restore focus", async () => {
  setDesktop(false); await mount(); const row = host.querySelector(".patients-row"); await click(row); const drawer = panel();
  assert.equal(drawer.classList.contains("atlas-dialog--drawer"), true); assert.equal(host.querySelector(".patients-detail"), null);
  const edit = button("Editar", drawer); await click(edit); const modal = panel(); assert.notEqual(modal, drawer);
  await act(async () => modal.dispatchEvent(new dom.window.Event("cancel", { cancelable: true })));
  assert.equal(document.activeElement === edit, true); assert.equal(panel() === drawer, true);
  await act(async () => drawer.dispatchEvent(new dom.window.Event("cancel", { cancelable: true })));
  assert.equal(document.activeElement === row, true); assert.equal(panel(), undefined);
  await click(row); await act(async () => setDesktop(true)); assert.equal(panel(), undefined); assert.ok(host.querySelector(".patients-detail"));
});
test("new form fields have unique labels and associated submit/cancel controls", async () => {
  await mount(); await click(button("+ Nuevo paciente")); const ids = [...document.querySelectorAll("[id]")].map((node) => node.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const label of panel().querySelectorAll("label")) assert.ok(document.getElementById(label.htmlFor));
  const submitButton = button("Guardar paciente"); assert.equal(submitButton.getAttribute("form"), panel().querySelector("form").id);
  await click(button("Cancelar")); assert.equal(panel(), undefined); assert.equal(document.body.style.overflow, "");
});
test("sorting stays local to fetched results and retains previous sortable fields", async () => {
  await mount(); await value(field("Ordenar listado"), "name:desc"); assert.match(host.querySelector(".patients-row").textContent, /Bruno/);
  for (const key of ["dateOfBirth", "phone", "email"]) await value(field("Ordenar listado"), `${key}:asc`);
  assert.equal(mainRequests().length, 1);
});
