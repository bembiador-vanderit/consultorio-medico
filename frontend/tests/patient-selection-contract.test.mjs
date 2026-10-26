import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: PatientForm } = await server.ssrLoadModule("/src/components/patients/PatientForm.tsx");
const { AppointmentForm } = await server.ssrLoadModule("/src/components/agenda/AppointmentForm.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const adapter = api.defaults.adapter;
const host = document.getElementById("root");
const user = { id: 2, full_name: "Doctor ficticio", roles: ["doctor"], permissions: ["patients:access", "patients:view", "patients:edit"], is_active: true };
const identity = { id: 8, first_name: "Paciente", last_name: "Ficticio", date_of_birth: "1990-01-01", phone_masked: "***0001", email_masked: null, selection_token: "fixture-server-selection-proof" };
const visible = { id: 9, first_name: "Esther", last_name: "Álvarez", date_of_birth: "1991-02-03", phone: "8095504036", email: "esther@example.test", created_at: "2026-01-01" };
let root, requests, saved, selected;

beforeEach(() => {
  root = createRoot(host);
  requests = [];
  saved = selected = null;
  api.defaults.adapter = async (config) => {
    requests.push(config);
    let data;
    if (config.url === "/patients/localities") data = [];
    else if (config.url === "/insurance/companies") data = [];
    else if (config.url === "/patients" && config.method === "get") data = config.params.query === "No encontrado" ? [] : [visible];
    else if (config.url === "/patients" && config.method === "post") data = { ...visible, id: 10, first_name: "Nuevo", last_name: "Paciente", selection_token: "new-patient-proof" };
    else if (config.url === "/patients/identity-search") data = [identity];
    else if (config.url === "/appointments/doctors") data = [{ id: 2, full_name: user.full_name, center_ids: [1], specialties: [{ id: 3, name: "Especialidad ficticia" }] }];
    else if (config.url === "/appointments/effective-mode") data = { schedule_mode: "timed" };
    else if (config.url === "/appointments/queue-capabilities") data = { booking_order_enabled: true };
    else if (config.url === "/appointments" && config.method === "post") data = { id: 30, ...JSON.parse(config.data) };
    else throw new Error(`Unexpected request ${config.url}`);
    return { data, status: 200, statusText: "OK", headers: {}, config };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = adapter; });
after(async () => { await server.close(); dom.window.close(); });

async function setValue(input, value) {
  const prototype = input.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(input, value);
    input.dispatchEvent(new dom.window.Event(input.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
}
function control(label) {
  const field = [...document.querySelectorAll("label")].find((item) => item.textContent.startsWith(label));
  assert.ok(field, label);
  return field.htmlFor ? document.getElementById(field.htmlFor) : field.querySelector("input, select");
}

test("PatientForm preserves the server proof when choosing a restricted existing identity", async () => {
  await act(async () => root.render(h(PatientForm, { patient: null, user, onClose() {}, onSaved(value) { saved = value; }, onExistingSelected(value) { selected = value; } })));
  await setValue(control("Nombre"), "Paciente");
  await setValue(control("Apellido"), "Ficticio");
  await setValue(control("Fecha de nacimiento"), identity.date_of_birth);
  await setValue(control("Teléfono"), "8095550001");
  await act(async () => document.querySelector("dialog form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true })));
  const result = [...document.querySelectorAll("button")].find((item) => item.textContent.includes("Usar Paciente Ficticio"));
  assert.ok(result);
  await act(async () => result.click());
  assert.equal(selected.selection_token, identity.selection_token);
  assert.equal(saved, null);
  assert.equal(requests.some((item) => item.url === "/patients" && item.method === "post"), false);
});

test("AppointmentForm forwards the selected search proof with the appointment request", async () => {
  await act(async () => root.render(h(AppointmentForm, { appointment: null, date: "2026-09-15", centers: [{ id: 1, name: "Centro ficticio" }], user, onClose() {}, onSaved(value) { saved = value; } })));
  await setValue(control("Centro"), "1");
  await setValue(control("Médico"), "2");
  await act(async () => document.querySelector(".agenda-patient-verification summary").click());
  await setValue(control("Teléfono o correo exacto"), "8095550001");
  await setValue(control("Fecha de nacimiento"), identity.date_of_birth);
  await act(async () => new Promise((resolve) => setTimeout(resolve, 350)));
  const result = [...document.querySelectorAll("button")].find((item) => item.textContent.startsWith("Paciente Ficticio"));
  assert.ok(result);
  await act(async () => result.click());
  await act(async () => [...document.querySelectorAll("button")].find((item) => item.textContent === "Guardar cita").click());
  const request = requests.find((item) => item.url === "/appointments" && item.method === "post");
  assert.ok(request);
  assert.equal(JSON.parse(request.data).patient_selection_token, identity.selection_token);
  assert.equal(saved.id, 30);
});

async function openAppointment() {
  await act(async () => root.render(h(AppointmentForm, { appointment: null, date: "2026-09-15", centers: [{ id: 1, name: "Centro ficticio" }], user, onClose() {}, onSaved(value) { saved = value; } })));
  await setValue(control("Centro"), "1");
  await setValue(control("Médico"), "2");
}
async function search(value) {
  await setValue(control("Paciente"), value);
  await act(async () => new Promise((resolve) => setTimeout(resolve, 350)));
}
function clickButton(label) {
  const button = [...document.querySelectorAll("button")].find((item) => item.textContent.includes(label));
  assert.ok(button, label);
  return act(async () => button.click());
}

test("Nueva cita busca por nombre, teléfono, documento o correo y guarda el patient_id seleccionado", async () => {
  await openAppointment();
  assert.ok(control("Paciente"));
  for (const term of ["Esther", "8095504036", "00112345678", "esther@example.test"]) {
    await search(term);
    assert.ok(requests.some((item) => item.url === "/patients" && item.params.query === term));
    assert.match(document.querySelector(".agenda-patient-results").textContent, /Esther Álvarez/);
  }
  await clickButton("Esther Álvarez");
  assert.match(document.querySelector(".agenda-selected-patient").textContent, /8095504036/);
  await clickButton("Guardar cita");
  const payload = JSON.parse(requests.find((item) => item.url === "/appointments" && item.method === "post").data);
  assert.equal(payload.patient_id, visible.id);
  assert.equal(payload.patient_selection_token, undefined);
});

test("sin paciente muestra error específico y Cambiar vuelve a buscar", async () => {
  await openAppointment();
  assert.match(document.querySelector("dialog").textContent, /\* Campos obligatorios/);
  assert.doesNotMatch(document.querySelector("dialog").textContent, /\(obligatorio\)|Este campo es obligatorio/);
  assert.equal(control("Paciente").getAttribute("aria-invalid"), null);
  await clickButton("Guardar cita");
  assert.match(document.querySelector("dialog").textContent, /Seleccione un paciente/);
  assert.equal(control("Paciente").getAttribute("aria-invalid"), "true");
  assert.match(document.querySelector("dialog").textContent, /Este campo es obligatorio\./);
  assert.equal(requests.some((item) => item.url === "/appointments" && item.method === "post"), false);
  await search("Esther");
  await clickButton("Esther Álvarez");
  assert.doesNotMatch(document.querySelector("dialog").textContent, /Este campo es obligatorio\./);
  await clickButton("Cambiar");
  assert.ok(control("Paciente"));
  assert.equal(document.querySelector(".agenda-selected-patient"), null);
});

test("secretaría usa el paciente visible seleccionado sin exigir fecha de nacimiento", async () => {
  const secretary = { ...user, roles: ["secretary"] };
  await act(async () => root.render(h(AppointmentForm, { appointment: null, date: "2026-09-15", centers: [{ id: 1, name: "Centro ficticio" }], user: secretary, onClose() {}, onSaved(value) { saved = value; } })));
  await setValue(control("Centro"), "1");
  await setValue(control("Médico"), "2");
  await search("Esther");
  await clickButton("Esther Álvarez");
  await clickButton("Guardar cita");
  assert.equal(saved.patient_id, visible.id);
  assert.equal(requests.some((item) => item.url === "/patients/identity-search"), false);
});

test("crear paciente reutiliza PatientForm y conserva el borrador de cita", async () => {
  await openAppointment();
  await setValue(control("Motivo"), "Control pendiente");
  await search("No encontrado");
  assert.match(document.querySelector(".agenda-patient-results").textContent, /No se encontró el paciente/);
  await clickButton("Crear nuevo paciente");
  assert.equal(document.querySelectorAll("dialog").length, 2);
  const patientDialog = [...document.querySelectorAll("dialog")].at(-1);
  const input = (label) => {
    const field = [...patientDialog.querySelectorAll("label")].find((item) => item.textContent.startsWith(label));
    assert.ok(field, label);
    return field.htmlFor ? document.getElementById(field.htmlFor) : field.querySelector("input");
  };
  await setValue(input("Nombre"), "Nuevo");
  await setValue(input("Apellido"), "Paciente");
  await setValue(input("Fecha de nacimiento"), "2000-01-01");
  await act(async () => patientDialog.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true })));
  assert.equal(document.querySelectorAll("dialog").length, 1);
  assert.match(document.querySelector(".agenda-selected-patient").textContent, /Nuevo Paciente/);
  assert.equal(control("Motivo").value, "Control pendiente");
  await clickButton("Guardar cita");
  const payload = JSON.parse(requests.find((item) => item.url === "/appointments" && item.method === "post").data);
  assert.equal(payload.patient_id, 10);
  assert.equal(payload.patient_selection_token, "new-patient-proof");
});
