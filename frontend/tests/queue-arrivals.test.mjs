import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { QueueArrivalPanel } = await server.ssrLoadModule("/src/components/agenda/QueueArrivalPanel.tsx");
const { QueueLineSettings } = await server.ssrLoadModule("/src/components/agenda/QueueLineSettings.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const originalConfirm = dom.window.confirm;
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
const button = (text) => [...document.querySelectorAll("button")].find((item) => item.textContent === text);
let root;
let calls;
let tickets;
let lines;
let nextCallState;
let callPolicy;

beforeEach(() => {
  root = createRoot(document.getElementById("root"));
  calls = [];
  tickets = [];
  lines = [{ id: 3, center_id: 1, doctor_id: 2, specialty_id: null, name: "Dr. Osiris", prefix: "C", is_active: true, call_on_consultation_start: false, doctor_name: "Dr. Osiris", center_name: "Centro Uno" }];
  nextCallState = { queue_line_id: 3, call_mode: "manual", preparation_seconds: 60,
    provider_paused: false, current_in_service_ticket_id: null, next_waiting_ticket_id: 11,
    next_waiting_public_code: "C-001", last_service_completed_at: null, ready_at: null,
    server_now: "2030-10-15T11:30:00", ready: true, can_call: true, block_reason: null };
  callPolicy = { queue_line_id: 3, center_id: 1, call_mode: "manual", preparation_seconds: 60, start_consultation_can_call: false };
  api.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/appointments") return response(config, [
      { id: 7, patient_name: "Ana Prueba", patient_phone: "809-000-0001", doctor_name: "Dr. Osiris", center_name: "Centro Uno", center_id: 1, doctor_id: 2, specialty_id: null, appointment_date: "2030-10-15", schedule_mode: "queue", status: "scheduled" },
      { id: 8, patient_name: "Paciente por hora", center_id: 1, doctor_id: 2, appointment_date: "2030-10-15", schedule_mode: "timed", status: "scheduled" },
    ]);
    if (config.method === "get" && config.url === "/queue-lines") return response(config, lines.filter((line) => !config.params?.active_only || line.is_active));
    if (config.method === "get" && config.url === "/queue-tickets") return response(config, tickets);
    if (config.method === "get" && config.url === "/provider-pauses/current") return response(config, null);
    if (config.method === "get" && config.url === "/queue-lines/3/next-call-state") return response(config, nextCallState);
    if (config.method === "get" && config.url === "/queue-lines/3/call-policy") return response(config, callPolicy);
    if (config.method === "put" && config.url === "/queue-lines/3/call-policy") {
      Object.assign(callPolicy, JSON.parse(config.data)); return response(config, callPolicy);
    }
    if (config.method === "post" && config.url === "/queue-lines/3/call-next") {
      nextCallState = { ...nextCallState, can_call: false, block_reason: "already_called" };
      return response(config, { id: 11, status: "called" });
    }
    if (config.method === "post" && config.url === "/queue-tickets/arrivals/7") {
      tickets.push({ id: 11, appointment_id: 7, public_code: "C-001", status: "waiting", arrived_at: "2030-10-15T11:31:00", sequence_number: 1, call_count: 0 });
      return response(config, tickets.at(-1));
    }
    if (config.method === "post" && config.url === "/queue-tickets/11/call") {
      Object.assign(tickets[0], { status: "called", call_count: 1 });
      return response(config, tickets[0]);
    }
    if (config.method === "post" && config.url === "/queue-tickets/11/recall") {
      Object.assign(tickets[0], { status: "called", call_count: 2 });
      return response(config, tickets[0]);
    }
    if (config.method === "post" && config.url === "/queue-tickets/11/start") {
      Object.assign(tickets[0], { status: "in_service", consultation_started_at: "2030-10-15T11:33:00", consultation_started_by_user_id: 2, doctor_id: 2 });
      return response(config, tickets[0]);
    }
    if (config.method === "post" && config.url === "/queue-tickets/11/complete") {
      Object.assign(tickets[0], { status: "completed", consultation_finished_at: "2030-10-15T11:40:00", consultation_finished_by_user_id: 2 });
      return response(config, tickets[0]);
    }
    if (config.method === "get" && config.url === "/queue-tickets/11/events") return response(config, [{ id: 1, queue_ticket_id: 11, event_type: "CALLED", occurred_at: "2030-10-15T11:32:00", actor_user_id: 2, created_at: "2030-10-15T11:32:00" }]);
    if (config.method === "post" && config.url === "/queue-lines") {
      const payload = JSON.parse(config.data);
      lines.push({ ...payload, id: 4, is_active: true, doctor_name: "Dr. Osiris", center_name: "Centro Uno" });
      return response(config, lines.at(-1));
    }
    if (config.method === "put" && config.url === "/queue-lines/3") {
      Object.assign(lines[0], JSON.parse(config.data));
      return response(config, lines[0]);
    }
    throw new Error(`Unexpected request: ${config.method} ${config.url}`);
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; dom.window.confirm = originalConfirm; });
after(async () => { await server.close(); dom.window.close(); });

test("registra llegada solo para cita queue y muestra turno y hora del servidor", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true })));
  assert.match(document.body.textContent, /Ana Prueba/);
  assert.match(document.body.textContent, /809-000-0001/);
  assert.doesNotMatch(document.body.textContent, /Paciente por hora/);
  await act(async () => button("Registrar llegada").click());
  assert.deepEqual(JSON.parse(calls.find((call) => call.method === "post").data), { queue_line_id: 3 });
  assert.match(document.body.textContent, /Turno: C-001/);
  assert.match(document.body.textContent, /Estado: Esperando/);
  assert.equal(button("Registrar llegada"), undefined);
});

test("administración crea y desactiva líneas sin cambiar el médico ni centro", async () => {
  await act(async () => root.render(h(QueueLineSettings, {
    doctors: [{ id: 2, full_name: "Dr. Osiris", centerIds: [1] }], centers: [{ id: 1, name: "Centro Uno" }],
  })));
  const fields = [...document.querySelectorAll("label")];
  async function change(label, value) {
    const input = fields.find((item) => item.textContent.startsWith(label)).querySelector("input, select");
    await act(async () => {
      if (input.tagName === "SELECT") { input.value = value; input.dispatchEvent(new dom.window.Event("change", { bubbles: true })); }
      else { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, value); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); }
    });
  }
  await change("Centro", "1");
  await change("Médico", "2");
  await change("Nombre", "Dra. Prueba");
  await change("Prefijo", "T");
  assert.equal(button("Crear línea").disabled, false);
  await act(async () => button("Crear línea").click());
  assert.equal(lines.length, 2);
  assert.equal(lines[1].prefix, "T");
  const checkbox = document.querySelector('section[aria-label="Líneas de turnos"] input[type="checkbox"]');
  await act(async () => checkbox.click());
  await act(async () => button("Guardar").click());
  assert.equal(lines[0].is_active, false);
  assert.equal(lines[0].doctor_id, 2);
  assert.equal(lines[0].center_id, 1);
});

test("llama un turno y permite consultar su historial sin cambiar la cita", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true })));
  await act(async () => button("Registrar llegada").click());
  await act(async () => button("Llamar").click());
  assert.ok(calls.some((call) => call.method === "post" && call.url === "/queue-tickets/11/call"));
  assert.match(document.body.textContent, /Estado: Llamado/);
  await act(async () => button("Ver historial").click());
  assert.match(document.body.textContent, /CALLED/);
});

test("Llamar y Volver a llamar envían intenciones distintas", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true })));
  await act(async () => button("Registrar llegada").click());
  await act(async () => button("Llamar").click());
  assert.equal(button("Llamar"), undefined);
  await act(async () => button("Volver a llamar").click());
  const actions = calls.filter((call) => call.method === "post" && call.url?.startsWith("/queue-tickets/11/"));
  assert.deepEqual(actions.map((call) => call.url), ["/queue-tickets/11/call", "/queue-tickets/11/recall"]);
});

test("acciones operativas disponibles tienen color y las bloqueadas se distinguen", async () => {
  tickets = [{ id: 11, appointment_id: 7, doctor_id: 2, public_code: "C-001", status: "called", arrived_at: "2030-10-15T11:31:00", sequence_number: 1, call_count: 1 }];
  nextCallState = { ...nextCallState, can_call: false, block_reason: "already_called" };
  await act(async () => root.render(h(QueueArrivalPanel, {
    initialDate: "2030-10-15", canRecord: true, canOperate: true, canStart: true, showCallPolicy: true,
  })));
  assert.equal(button("Volver a llamar").disabled, false);
  assert.match(button("Volver a llamar").className, /bg-teal-700/);
  assert.match(button("Sin respuesta").className, /bg-amber-700/);
  assert.match(button("Iniciar consulta").className, /bg-indigo-700/);
  assert.match(button("Se retiró").className, /bg-rose-700/);
  assert.match(button("Ver historial").className, /bg-sky-700/);
  assert.equal(button("Llamar ahora").disabled, true);
  assert.match(button("Llamar ahora").className, /disabled:bg-slate-200/);
});

test("médico asignado finaliza solo tras confirmación y ve horas de inicio y cierre", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true, canStart: true, canComplete: true, currentUserId: 2 })));
  await act(async () => button("Registrar llegada").click());
  await act(async () => button("Llamar").click());
  await act(async () => button("Iniciar consulta").click());
  assert.ok(button("Finalizar consulta"));
  const confirmations = [];
  dom.window.confirm = (prompt) => { confirmations.push(prompt); return confirmations.length > 1; };
  await act(async () => button("Finalizar consulta").click());
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/11/complete").length, 0);
  await act(async () => button("Finalizar consulta").click());
  assert.deepEqual(confirmations, ["¿Finalizar la consulta de este paciente?", "¿Finalizar la consulta de este paciente?"]);
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/11/complete").length, 1);
  assert.match(document.body.textContent, /Estado: Completado/);
  assert.match(document.body.textContent, /Inicio de consulta:/);
  assert.match(document.body.textContent, /Finalización:/);
  assert.equal(button("Iniciar consulta"), undefined);
  assert.equal(button("Finalizar consulta"), undefined);
});

test("secretaría y médico no asignado ven el estado pero no pueden finalizar desde UI", async () => {
  tickets = [{ id: 11, appointment_id: 7, doctor_id: 2, public_code: "C-001", status: "in_service", arrived_at: "2030-10-15T11:31:00", consultation_started_at: "2030-10-15T11:33:00", sequence_number: 1, call_count: 1 }];
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true })));
  assert.match(document.body.textContent, /Estado: En consulta/);
  assert.equal(button("Finalizar consulta"), undefined);
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: false, canOperate: true, canComplete: true, currentUserId: 3 })));
  assert.equal(button("Finalizar consulta"), undefined);
  tickets[0] = { ...tickets[0], status: "completed", consultation_finished_at: "2030-10-15T11:40:00" };
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-16", canRecord: false, canOperate: true, canComplete: true, currentUserId: 3 })));
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: false, canOperate: true, canComplete: true, currentUserId: 3 })));
  assert.match(document.body.textContent, /Estado: Completado/);
  assert.match(document.body.textContent, /Finalización:/);
  assert.equal(calls.some((call) => call.url === "/queue-tickets/11/complete"), false);
});

test("mostrar pausas no cambia los controles del turno", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, {
    initialDate: "2030-10-15", canRecord: true, canOperate: true,
    currentUserId: 2, showPauses: true, canManagePauses: true,
  })));
  assert.match(document.body.textContent, /DISPONIBLE · Sin pausa operativa/);
  await act(async () => button("Registrar llegada").click());
  assert.ok(button("Llamar"));
  await act(async () => button("Llamar").click());
  assert.match(document.body.textContent, /Estado: Llamado/);
  assert.ok(button("Volver a llamar"));
});

test("la pausa del médico se muestra aunque todavía no exista una línea de turnos", async () => {
  lines = [];
  await act(async () => root.render(h(QueueArrivalPanel, {
    initialDate: "2030-10-15", canRecord: false, currentUserId: 2,
    showPauses: true, canManagePauses: true,
    pausePairs: [{ centerId: 1, doctorId: 2, doctorName: "Dr. Osiris" }],
  })));
  assert.match(document.body.textContent, /Pausas operativas/);
  assert.match(document.body.textContent, /Dr. Osiris/);
  assert.ok(button("Iniciar pausa"));
  assert.equal(calls.some((call) => call.method === "post"), false);
});

test("0046 muestra modo manual y llama siguiente solo tras pulsar el control", async () => {
  tickets = [{ id: 11, appointment_id: 7, doctor_id: 2, public_code: "C-001", status: "waiting", arrived_at: "2030-10-15T11:31:00", sequence_number: 1, call_count: 0 }];
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true, showCallPolicy: true })));
  assert.match(document.body.textContent, /Modo: Manual/);
  assert.match(document.body.textContent, /Siguiente turno: C-001/);
  assert.equal(button("Llamar"), undefined);
  assert.equal(calls.some((call) => call.method === "post"), false);
  await act(async () => button("Llamar ahora").click());
  assert.equal(calls.filter((call) => call.url === "/queue-lines/3/call-next" && call.method === "post").length, 1);
});

test("0046 asistido muestra preparación y pausa bloquea llamada; automático no muestra botón", async () => {
  nextCallState = { ...nextCallState, call_mode: "assisted", ready: false, can_call: false,
    ready_at: "2030-10-15T11:30:37", block_reason: "preparing" };
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true, showCallPolicy: true })));
  assert.match(document.body.textContent, /Preparación: 00:3[67]/);
  assert.equal(button("Llamar ahora").disabled, true);
  nextCallState = { ...nextCallState, provider_paused: true, block_reason: "provider_paused" };
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-16", canRecord: true, canOperate: true, showCallPolicy: true })));
  assert.match(document.body.textContent, /Médico en pausa/);
  nextCallState = { ...nextCallState, call_mode: "automatic", block_reason: "no_waiting", next_waiting_ticket_id: null, next_waiting_public_code: null };
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true, showCallPolicy: true })));
  assert.match(document.body.textContent, /No hay pacientes en espera/);
  assert.equal(button("Llamar ahora"), undefined);
  assert.equal(calls.some((call) => call.method === "post"), false);
});

test("0046 administración edita modo, preparación y permiso de inicio combinado", async () => {
  await act(async () => root.render(h(QueueLineSettings, {
    doctors: [{ id: 2, full_name: "Dr. Osiris", centerIds: [1] }], centers: [{ id: 1, name: "Centro Uno" }], showCallPolicy: true,
  })));
  const section = document.querySelector('[aria-label="Política de llamadas Dr. Osiris"]');
  assert.ok(section);
  const select = section.querySelector("select");
  await act(async () => { select.value = "automatic"; select.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  const number = section.querySelector('input[type="number"]');
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(number, "90"); number.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  const checkbox = section.querySelector('input[type="checkbox"]');
  await act(async () => { checkbox.click(); });
  await act(async () => button("Guardar política").click());
  const saved = calls.find((call) => call.url === "/queue-lines/3/call-policy" && call.method === "put");
  assert.ok(saved);
  assert.deepEqual(JSON.parse(saved.data), { call_mode: "automatic", preparation_seconds: 90, start_consultation_can_call: true });
});

test("0046 historial distingue llamada automática de actor humano", async () => {
  tickets = [{ id: 11, appointment_id: 7, doctor_id: 2, public_code: "C-001", status: "called", arrived_at: "2030-10-15T11:31:00", sequence_number: 1, call_count: 1 }];
  const adapter = api.defaults.adapter;
  api.defaults.adapter = (config) => config.url === "/queue-tickets/11/events"
    ? Promise.resolve(response(config, [{ id: 1, queue_ticket_id: 11, event_type: "CALLED", occurred_at: "2030-10-15T11:32:00", actor_user_id: null, call_source: "automatic", created_at: "2030-10-15T11:32:00" }]))
    : adapter(config);
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, canOperate: true, showCallPolicy: true })));
  await act(async () => button("Ver historial").click());
  assert.match(document.body.textContent, /llamada automática/);
});

test("una llegada registrada desde detalle refresca el panel sin perder la fecha", async () => {
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, refreshKey: 0 })));
  assert.ok(button("Registrar llegada"));
  const before = calls.filter((call) => call.method === "get" && call.url === "/queue-tickets").length;
  tickets.push({ id: 11, appointment_id: 7, public_code: "C-021", status: "waiting", arrived_at: "2030-10-15T11:31:00", sequence_number: 21 });
  await act(async () => root.render(h(QueueArrivalPanel, { initialDate: "2030-10-15", canRecord: true, refreshKey: 1 })));
  assert.ok(calls.filter((call) => call.method === "get" && call.url === "/queue-tickets").length > before);
  assert.match(document.body.textContent, /Turno: C-021/);
  assert.equal(button("Registrar llegada"), undefined);
  assert.equal(document.querySelector('input[type="date"]').value, "2030-10-15");
});
