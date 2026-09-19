import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

import { createBrowser } from "./browser.mjs";
import {
  activeDoctor,
  appointmentConfirmed,
  appointmentScheduled,
  clinicalHistory,
  clinicalHistoryCompleted,
  clinicalHistoryInProgress,
  diagnosisFixture,
  laboratoryTestFixture,
  legacyClinicalHistory,
  medicalStudyFixture,
  prescriptionFixture,
  requestedTestFixture,
  vitalSignsFixture,
} from "./fixtures/clinical.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({
  server: { middlewareMode: true, ws: false },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
const { default: Consultation } = await server.ssrLoadModule("/src/pages/Consultation.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const NativeDate = globalThis.Date;
const nativeAnchorClick = dom.window.HTMLAnchorElement.prototype.click;
const host = document.getElementById("root");

let root;
let calls;
let currentAppointment;
let contextHistories;
let currentHistory;
let vitals;
let diagnoses;
let prescriptions;
let requestedTests;
let laboratoryOrders;
let studyOrders;
let intercept;
let backCount;
let confirmCount;

function clone(value) {
  return structuredClone(value);
}

function ok(config, data) {
  return { data: clone(data), status: 200, statusText: "OK", headers: {}, config };
}

function failure(detail, status = 409) {
  const error = new Error(detail);
  error.response = { status, data: { detail } };
  throw error;
}

function payload(config) {
  return typeof config.data === "string" ? JSON.parse(config.data) : config.data;
}

function context() {
  return {
    appointment_id: currentAppointment.id,
    patient_id: currentAppointment.patient_id,
    doctor_id: currentAppointment.doctor_id,
    center_id: currentAppointment.center_id,
    specialty_id: currentAppointment.specialty_id,
    specialty_name: currentAppointment.specialty_name,
    appointment_date: currentAppointment.appointment_date,
    appointment_time: currentAppointment.appointment_time,
    appointment_reason: currentAppointment.reason,
    appointment_status: currentAppointment.status,
    previous_consultations: contextHistories,
  };
}

async function responseAdapter(config) {
  calls.push(config);
  if (intercept) {
    const result = intercept(config);
    if (result !== undefined) return result;
  }

  if (config.url === "/auth/me" && config.method === "get") return ok(config, activeDoctor);
  if (config.url === `/clinical-history/appointments/${currentAppointment.id}/context` && config.method === "get") return ok(config, context());
  if (config.url === "/clinical-catalog/studies" && config.method === "get") return ok(config, [medicalStudyFixture]);
  if (config.url === "/laboratory-tests" && config.method === "get") return ok(config, [laboratoryTestFixture]);
  if (config.url === `/clinical-history/${currentHistory?.id}/prescriptions/pdf` && config.method === "get") return ok(config, new Blob(["fixture"]));
  if (config.url === `/clinical-history/${currentHistory?.id}/requested-tests/pdf` && config.method === "get") return ok(config, new Blob(["fixture"]));
  if (config.url === `/clinical-history/${currentHistory?.id}/summary/pdf` && config.method === "get") return ok(config, new Blob(["fixture"]));
  if (config.url === `/clinical-history/${currentHistory?.id}/prescriptions` && config.method === "get") return ok(config, prescriptions);
  if (config.url === `/clinical-history/${currentHistory?.id}/diagnoses` && config.method === "get") return ok(config, diagnoses);
  if (config.url === `/clinical-history/${currentHistory?.id}/requested-tests` && config.method === "get") return ok(config, requestedTests);
  if (config.url === `/clinical-history/${currentHistory?.id}/vital-signs` && config.method === "get") return ok(config, vitals);
  if (config.url === `/clinical-history/${currentHistory?.id}/laboratory-orders` && config.method === "get") return ok(config, laboratoryOrders);
  if (config.url === `/clinical-history/${currentHistory?.id}/study-orders` && config.method === "get") return ok(config, studyOrders);

  if (config.url === `/clinical-history/patients/${currentAppointment.patient_id}` && config.method === "post") {
    currentHistory = clinicalHistory({ id: 61, appointment_id: currentAppointment.id, ...payload(config) });
    contextHistories = [currentHistory, ...contextHistories];
    return ok(config, currentHistory);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}` && config.method === "put") {
    const { expected_revision, ...changes } = payload(config);
    currentHistory = { ...currentHistory, ...changes, revision: expected_revision + 1, updated_at: "2026-09-16T10:01:00" };
    return ok(config, currentHistory);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/complete` && config.method === "post") {
    currentHistory = {
      ...currentHistory,
      status: "completed",
      revision: currentHistory.revision + 1,
      completed_at: "2026-09-16T10:05:00",
      completed_by_id: activeDoctor.id,
    };
    currentAppointment = { ...currentAppointment, status: "completed" };
    return ok(config, currentHistory);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/vital-signs` && config.method === "put") {
    vitals = { ...vitalSignsFixture, ...payload(config), clinical_history_id: currentHistory.id };
    return ok(config, vitals);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/diagnoses` && config.method === "post") {
    const next = { ...diagnosisFixture, id: diagnoses.length + 100, ...payload(config), clinical_history_id: currentHistory.id };
    diagnoses = next.is_primary ? [next, ...diagnoses.map((item) => ({ ...item, is_primary: false }))] : [...diagnoses, next];
    return ok(config, next);
  }
  if (new RegExp(`^/clinical-history/${currentHistory?.id}/diagnoses/\\d+$`).test(config.url) && config.method === "delete") {
    diagnoses = diagnoses.filter((item) => item.id !== Number(config.url.split("/").at(-1)));
    return ok(config, null);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/prescriptions` && config.method === "post") {
    const next = { ...prescriptionFixture, id: prescriptions.length + 200, ...payload(config), clinical_history_id: currentHistory.id };
    prescriptions = [...prescriptions, next];
    return ok(config, next);
  }
  if (new RegExp(`^/clinical-history/${currentHistory?.id}/prescriptions/\\d+$`).test(config.url) && config.method === "put") {
    const id = Number(config.url.split("/").at(-1));
    const next = { ...prescriptions.find((item) => item.id === id), ...payload(config), id, clinical_history_id: currentHistory.id };
    prescriptions = prescriptions.map((item) => item.id === id ? next : item);
    return ok(config, next);
  }
  if (new RegExp(`^/clinical-history/${currentHistory?.id}/prescriptions/\\d+$`).test(config.url) && config.method === "delete") {
    prescriptions = prescriptions.filter((item) => item.id !== Number(config.url.split("/").at(-1)));
    return ok(config, null);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/requested-tests` && config.method === "post") {
    const next = { id: requestedTests.length + 300, clinical_history_id: currentHistory.id, ...payload(config) };
    requestedTests = [...requestedTests, next];
    return ok(config, next);
  }
  if (/^\/clinical-history\/requested-tests\/\d+$/.test(config.url) && config.method === "delete") {
    requestedTests = requestedTests.filter((item) => item.id !== Number(config.url.split("/").at(-1)));
    return ok(config, null);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/laboratory-orders` && config.method === "post") {
    const next = { id: 401, clinical_history_id: currentHistory.id, patient_name: currentAppointment.patient_name, doctor_name: currentAppointment.doctor_name, center_name: currentAppointment.center_name, specialty_name: currentAppointment.specialty_name, status: "ordered", is_additional: false, notes: payload(config).notes, created_at: "2026-09-16T09:50:00", items: payload(config).items.map((item, index) => ({ id: index + 1, laboratory_test_id: item.laboratory_test_id, test_code: laboratoryTestFixture.code, test_name: laboratoryTestFixture.name, test_category: laboratoryTestFixture.category, custom_note: null })) };
    laboratoryOrders = [next];
    return ok(config, next);
  }
  if (config.url === `/clinical-history/${currentHistory?.id}/study-orders` && config.method === "post") return ok(config, {});

  throw new Error(`Unexpected request ${config.method} ${config.url}`);
}

async function settle() {
  for (let index = 0; index < 4; index += 1) {
    await act(async () => { await Promise.resolve(); });
  }
}

async function mount(appointment = appointmentScheduled) {
  await act(async () => {
    root.render(h(Consultation, { appointment, onBack() { backCount += 1; } }));
  });
  await settle();
}

function button(label, scope = host) {
  return [...scope.querySelectorAll("button")].find((item) => item.textContent.trim() === label);
}

function control(label, scope = host) {
  const wrapper = [...scope.querySelectorAll("label")].find((item) => item.textContent.trim().startsWith(label));
  assert.ok(wrapper, label);
  const target = wrapper.querySelector("input, textarea, select");
  assert.ok(target, label);
  return target;
}

async function click(target) {
  assert.ok(target);
  await act(async () => { target.click(); });
  await settle();
}

async function change(target, value) {
  await act(async () => {
    const prototype = target.tagName === "TEXTAREA"
      ? dom.window.HTMLTextAreaElement.prototype
      : target.tagName === "SELECT"
        ? dom.window.HTMLSelectElement.prototype
        : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(target, value);
    target.dispatchEvent(new dom.window.Event(target.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
  await settle();
}

function urls() {
  return calls.map((item) => `${item.method} ${item.url}`);
}

beforeEach(() => {
  globalThis.Date = class extends NativeDate {
    constructor(...args) { super(...(args.length ? args : ["2026-09-16T12:00:00"])); }
    static now() { return new NativeDate("2026-09-16T12:00:00").getTime(); }
  };
  root = createRoot(host);
  calls = [];
  currentAppointment = clone(appointmentScheduled);
  contextHistories = [];
  currentHistory = null;
  vitals = null;
  diagnoses = [];
  prescriptions = [];
  requestedTests = [];
  laboratoryOrders = [];
  studyOrders = [];
  intercept = null;
  backCount = 0;
  confirmCount = 0;
  dom.window.confirm = () => { confirmCount += 1; return true; };
  dom.window.HTMLAnchorElement.prototype.click = function clickDownloadFixture() {};
  api.defaults.adapter = responseAdapter;
});

afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter;
  dom.window.HTMLAnchorElement.prototype.click = nativeAnchorClick;
  globalThis.Date = NativeDate;
});

after(async () => {
  await server.close();
  dom.window.close();
});

test("consulta nueva conserva el contexto de la cita y bloquea módulos sin historyId", async () => {
  await mount();
  assert.match(host.textContent, /Paciente de prueba/);
  assert.match(host.textContent, /Dra\. Prueba/);
  assert.match(host.textContent, /Centro de prueba/);
  assert.match(host.textContent, /Cardiología ficticia/);
  assert.equal(button("Guardar consulta").disabled, false);
  assert.equal(control("Medicamento *").disabled, true);
  assert.match(host.textContent, /Guarda primero la consulta para crear órdenes estructuradas/);
  assert.deepEqual([...urls()].sort(), [
    "get /auth/me",
    "get /clinical-history/appointments/81/context",
  ].sort());
  await click(button("← Volver a la agenda"));
  assert.equal(backCount, 1);
});

test("primer guardado envía solo contenido clínico y appointment_id al servidor", async () => {
  await mount();
  await change(control("Motivo de consulta"), "Motivo caracterizado");
  await click(button("Guardar consulta"));
  const created = calls.find((item) => item.method === "post" && item.url === "/clinical-history/patients/34");
  assert.ok(created);
  const body = payload(created);
  assert.deepEqual(Object.keys(body).sort(), [
    "allergies", "appointment_id", "chronic_conditions", "clinical_notes", "consultation_date", "current_illness", "current_medications", "family_history", "habits", "personal_history", "previous_surgeries", "reason_for_visit",
  ].sort());
  assert.equal(body.appointment_id, 81);
  assert.equal(body.reason_for_visit, "Motivo caracterizado");
  assert.equal("doctor_id" in body, false);
  assert.equal("center_id" in body, false);
  assert.equal("specialty_id" in body, false);
  assert.equal("patient_id" in body, false);
  assert.ok(!urls().includes("get /clinical-history/61/vital-signs"));
  assert.ok(urls().includes("get /clinical-history/61/laboratory-orders"));
});

test("consulta existente carga solo los recursos activos de la consulta", async () => {
  currentAppointment = clone(appointmentConfirmed);
  currentHistory = clinicalHistory({ appointment_id: 82, status: "in_progress" });
  contextHistories = [currentHistory];
  vitals = clone(vitalSignsFixture);
  diagnoses = [clone(diagnosisFixture)];
  prescriptions = [clone(prescriptionFixture)];
  requestedTests = [clone(requestedTestFixture)];
  await mount(currentAppointment);
  assert.equal(calls.filter((item) => item.method === "get").length, 10);
  assert.equal(calls.filter((item) => item.method === "get" && item.url === "/clinical-catalog/studies").length, 1);
  assert.match(host.textContent, /Diagnóstico ficticio/);
  assert.match(host.textContent, /Medicamento ficticio/);
  assert.match(host.textContent, /Estudio ficticio/);
  assert.equal(control("Presión sistólica").value, "120");
  for (const expected of [
    "/auth/me",
    "/clinical-history/appointments/82/context",
    "/clinical-history/42/prescriptions",
    "/clinical-history/42/diagnoses",
    "/clinical-history/42/requested-tests",
    "/clinical-history/42/vital-signs",
    "/laboratory-tests",
    "/clinical-history/42/laboratory-orders",
    "/clinical-history/42/study-orders",
  ]) assert.ok(calls.some((item) => item.url === expected), expected);
});

test("signos vitales preservan el payload actual y muestran el error del API", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  vitals = clone(vitalSignsFixture);
  await mount();
  await change(control("Frecuencia cardíaca"), "88");
  await click(button("Guardar signos vitales"));
  const update = calls.find((item) => item.method === "put" && item.url === "/clinical-history/42/vital-signs");
  assert.deepEqual(payload(update), {
    systolic_pressure: 120,
    diastolic_pressure: 80,
    heart_rate: 88,
    respiratory_rate: null,
    temperature_c: null,
    oxygen_saturation: null,
    weight_kg: 68.5,
    height_cm: 167,
  });

  intercept = (config) => config.url === "/clinical-history/42/vital-signs" && config.method === "put" ? failure("Rango rechazado", 422) : undefined;
  await change(control("Frecuencia cardíaca"), "10");
  await click(button("Guardar signos vitales"));
  assert.match(host.textContent, /Rango rechazado/);
});

test("actualización envía expected_revision y adopta la revisión devuelta", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  await mount();
  await change(control("Motivo de consulta"), "Versión actualizada");
  await click(button("Actualizar consulta"));
  const firstUpdate = calls.find((item) => item.method === "put" && item.url === "/clinical-history/42");
  assert.equal(payload(firstUpdate).expected_revision, 1);
  assert.equal(currentHistory.revision, 2);

  await change(control("Motivo de consulta"), "Segunda versión");
  await click(button("Actualizar consulta"));
  const updates = calls.filter((item) => item.method === "put" && item.url === "/clinical-history/42");
  assert.equal(payload(updates.at(-1)).expected_revision, 2);
  assert.equal(currentHistory.revision, 3);
});

test("409 por revisión obsoleta conserva cambios locales y muestra el conflicto", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  await mount();
  await change(control("Motivo de consulta"), "Cambio local pendiente");
  const detail = "La consulta fue modificada en otra sesión o pestaña. Recarga la información antes de continuar.";
  intercept = (config) => config.url === "/clinical-history/42" && config.method === "put" ? failure(detail, 409) : undefined;
  await click(button("Actualizar consulta"));
  assert.match(host.textContent, /modificada en otra sesión o pestaña/);
  assert.equal(control("Motivo de consulta").value, "Cambio local pendiente");
  assert.equal(currentHistory.revision, 1);
});

test("diagnósticos conservan creación principal/CIE-10 y eliminación", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  await mount();
  await change(host.querySelector('input[placeholder="Descripción del diagnóstico"]'), "Hallazgo ficticio");
  await change(host.querySelector('input[placeholder="Código CIE-10"]'), "Z99.9");
  await click(button("Agregar"));
  const created = calls.find((item) => item.method === "post" && item.url === "/clinical-history/42/diagnoses");
  assert.deepEqual(payload(created), { description: "Hallazgo ficticio", icd10_code: "Z99.9", is_primary: true });
  assert.match(host.textContent, /Hallazgo ficticio/);
  await click(button("Eliminar"));
  assert.ok(calls.some((item) => item.method === "delete" && /\/clinical-history\/42\/diagnoses\//.test(item.url)));
});

test("receta conserva CRUD y PDF sobre la historia activa", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  prescriptions = [clone(prescriptionFixture)];
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  URL.createObjectURL = () => "blob:fixture";
  URL.revokeObjectURL = () => {};
  try {
    await mount();
    await click(button("Editar"));
    await change(control("Dosis"), "20 mg");
    await click(button("Guardar cambios"));
    const updated = calls.find((item) => item.method === "put" && item.url === "/clinical-history/42/prescriptions/11");
    assert.equal(payload(updated).dose, "20 mg");
    await click(button("Descargar receta PDF"));
    assert.ok(calls.some((item) => item.method === "get" && item.url === "/clinical-history/42/prescriptions/pdf"));
    await click(button("Eliminar"));
    assert.ok(calls.some((item) => item.method === "delete" && item.url === "/clinical-history/42/prescriptions/11"));
  } finally {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  }
});

test("nuevas órdenes usan ClinicalOrdersSection y no exponen creación RequestedTest", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  await mount();
  assert.equal(host.querySelector('input[placeholder^="Ej. Hemograma"]'), null);
  assert.equal(button("Agregar estudio"), undefined);
  await click(button("+ Nueva orden"));
  await click([...host.querySelectorAll("button")].find((item) => item.textContent.trim().startsWith("Laboratorio")));
  await click(host.querySelector('button[aria-expanded="false"]'));
  const laboratoryChoice = [...host.querySelectorAll("label")].find((item) => item.textContent.includes("Hemograma ficticio"));
  await click(laboratoryChoice.querySelector('input[type="checkbox"]'));
  await click(button("Guardar orden"));
  const order = calls.find((item) => item.method === "post" && item.url === "/clinical-history/42/laboratory-orders");
  assert.deepEqual(payload(order), { items: [{ laboratory_test_id: 31 }], notes: null });
  assert.equal(calls.some((item) => item.method === "post" && item.url === "/clinical-history/42/requested-tests"), false);
});

test("RequestedTest legado sigue visible como historial y conserva PDF", async () => {
  currentAppointment = { ...clone(appointmentScheduled), status: "completed" };
  currentHistory = clone(clinicalHistoryCompleted);
  contextHistories = [currentHistory];
  requestedTests = [clone(requestedTestFixture)];
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  URL.createObjectURL = () => "blob:fixture";
  URL.revokeObjectURL = () => {};
  try {
    await mount(currentAppointment);
    assert.match(host.textContent, /Solicitudes heredadas/);
    assert.match(host.textContent, /Estudio ficticio/);
    assert.equal(button("Agregar estudio"), undefined);
    await click(button("Descargar orden PDF"));
    assert.ok(calls.some((item) => item.method === "get" && item.url === "/clinical-history/42/requested-tests/pdf"));
  } finally {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  }
});

test("el panel RequestedTest heredado no se muestra cuando no hay registros", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  await mount();
  assert.doesNotMatch(host.textContent, /Solicitudes heredadas/);
});

test("finalizar consulta confirma una vez, bloquea edición y conserva lectura", async () => {
  currentHistory = clone(clinicalHistoryInProgress);
  contextHistories = [currentHistory];
  prescriptions = [clone(prescriptionFixture)];
  await mount();
  await click(button("Finalizar consulta"));
  assert.equal(confirmCount, 1);
  assert.equal(calls.filter((item) => item.method === "post" && item.url === "/clinical-history/42/complete").length, 1);
  assert.match(host.textContent, /Consulta finalizada y bloqueada en modo de solo lectura/);
  assert.equal(button("Finalizar consulta"), undefined);
  assert.equal(button("Guardar consulta"), undefined);
  assert.ok(button("Descargar resumen PDF"));
});

for (const [status, detail] of [[409, "La consulta finalizada es de solo lectura"], [403, "No tiene acceso a esta historia clínica"]]) {
  test(`finalizar conserva el error ${status} del servidor sin representar un cierre local`, async () => {
    currentHistory = clone(clinicalHistoryInProgress);
    contextHistories = [currentHistory];
    intercept = (config) => config.url === "/clinical-history/42/complete" && config.method === "post" ? failure(detail, status) : undefined;
    await mount();
    await click(button("Finalizar consulta"));
    assert.equal(confirmCount, 1);
    assert.match(host.textContent, new RegExp(detail));
    assert.ok(button("Finalizar consulta"));
  });
}

test("consulta completed se mantiene legible y el historial previo se abre/cierra solo con su control actual", async () => {
  currentAppointment = { ...clone(appointmentScheduled), status: "completed" };
  currentHistory = clone(clinicalHistoryCompleted);
  contextHistories = [currentHistory, clone(legacyClinicalHistory)];
  await mount(currentAppointment);
  assert.match(host.textContent, /Consulta finalizada y bloqueada en modo de solo lectura/);
  assert.equal(button("Guardar consulta"), undefined);
  assert.ok(button("Descargar resumen PDF"));
  intercept = (config) => {
    if (config.method === "get" && config.url === "/clinical-history/18/vital-signs") return ok(config, null);
    if (config.method === "get" && config.url === "/clinical-history/18/diagnoses") return ok(config, []);
    if (config.method === "get" && config.url === "/clinical-history/18/prescriptions") return ok(config, []);
    if (config.method === "get" && config.url === "/clinical-history/18/requested-tests") return ok(config, []);
    return undefined;
  };
  await click(button("Ver historial completo"));
  const dialog = host.querySelector('[role="dialog"]');
  assert.ok(dialog);
  assert.match(dialog.textContent, /Consulta del 2025-06-02/);
  await act(async () => dialog.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
  assert.ok(host.querySelector('[role="dialog"]'));
  await click(button("Cerrar", dialog));
  assert.equal(host.querySelector('[role="dialog"]'), null);
});
