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
const user = { id: 2, full_name: "Doctor ficticio", roles: ["doctor"], is_active: true };
const identity = { id: 8, first_name: "Paciente", last_name: "Ficticio", date_of_birth: "1990-01-01", phone_masked: "***0001", email_masked: null, selection_token: "fixture-server-selection-proof" };
let root, requests, saved, selected;

beforeEach(() => {
  root = createRoot(host);
  requests = [];
  saved = selected = null;
  api.defaults.adapter = async (config) => {
    requests.push(config);
    let data;
    if (config.url === "/insurance/companies") data = [];
    else if (config.url === "/patients/identity-search") data = [identity];
    else if (config.url === "/appointments/doctors") data = [{ id: 2, full_name: user.full_name, center_ids: [1], specialties: [{ id: 3, name: "Especialidad ficticia" }] }];
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
  await act(async () => host.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true })));
  const result = [...host.querySelectorAll("button")].find((item) => item.textContent.includes("Usar Paciente Ficticio"));
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
