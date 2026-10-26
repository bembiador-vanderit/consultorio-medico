import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { AppointmentArrivalAction } = await server.ssrLoadModule("/src/components/agenda/AppointmentArrivalAction.tsx");
const { AgendaAppointmentCard } = await server.ssrLoadModule("/src/components/agenda/AgendaAppointmentCard.tsx");
const { appointmentRules, isoDate } = await server.ssrLoadModule("/src/components/agenda/agenda.ts");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const user = { id: 5, is_active: true, roles: ["secretary"], permissions: ["patients:access"] };
const fixture = { id: 19, patient_id: 19, patient_name: "QA Piloto A", doctor_id: 3, center_id: 1,
  appointment_date: isoDate(new Date()), appointment_time: "08:30:00", schedule_mode: "timed", status: "scheduled",
  arrival_enabled: true, arrived_at: null, has_clinical_history: false, clinical_history_status: null };
const button = () => [...document.querySelectorAll("button")].find(b => b.textContent === "Registrar llegada");
let root, calls, changed;
beforeEach(() => {
  root = createRoot(document.getElementById("root")); calls = []; changed = 0;
  api.defaults.adapter = async config => {
    calls.push(config);
    assert.equal(config.url, "/appointments/19/arrival");
    return { config, status: 200, statusText: "OK", headers: {}, data: { ...fixture, arrived_at: "2030-10-15T12:30:00", arrival_registered_by: 5 } };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });
async function mount(changes = {}, actor = user) {
  await act(async () => root.render(h(AppointmentArrivalAction, { appointment: { ...fixture, ...changes }, user: actor,
    canAccessPair: true, onChanged: () => changed++, presentation: "row" })));
}
for (const status of ["scheduled", "confirmed"]) test(`Por hora ${status}: llegada sin ticket ni cambio de hora y doble clic protegido`, async () => {
  await mount({ status });
  assert.ok(button());
  await act(async () => { const b = button(); b.click(); b.click(); });
  assert.equal(calls.length, 1); assert.equal(calls[0].method, "post");
  assert.deepEqual(JSON.parse(calls[0].data), {}); assert.equal(changed, 1);
  assert.equal(button(), undefined); assert.match(document.body.textContent, /Llegó · En espera/);
  assert.doesNotMatch(document.body.textContent, /Turno [A-Z]-/);
  assert.equal(fixture.schedule_mode, "timed"); assert.equal(fixture.appointment_time, "08:30:00");
});
for (const status of ["completed", "cancelled", "no_show"]) test(`sin llegada para ${status}`, async () => {
  await mount({ status }); assert.equal(button(), undefined); assert.equal(calls.length, 0);
});
test("permiso, alcance y rol no amplían clínica", async () => {
  await mount({}, { ...user, denied_permissions: ["patients:access"] }); assert.equal(button(), undefined);
  await mount({}, { ...user, roles: ["doctor"] }); assert.equal(button(), undefined);
  assert.equal(calls.length, 0);
});
test("esquema pendiente muestra razón y no envía petición", async () => {
  await mount({ arrival_enabled: false }); assert.equal(button(), undefined);
  assert.match(document.body.textContent, /pendiente de activación/); assert.equal(calls.length, 0);
});
test("error controlado no marca llegada y permite reintento", async () => {
  api.defaults.adapter = async () => { throw { response: { status: 409, data: { detail: "La cita cambió de estado" } } }; };
  await mount(); await act(async () => button().click());
  assert.match(document.body.textContent, /La cita cambió de estado/); assert.ok(button()); assert.equal(changed, 0);
});
test("médico distingue espera y atención; horario sigue bloqueado", async () => {
  const appointment = { ...fixture, arrived_at: "2030-10-15T12:30:00" };
  const doctor = { ...user, id: 3, roles: ["doctor"] };
  await mount(appointment, doctor); assert.match(document.body.textContent, /En espera/);
  const rules = appointmentRules(appointment, doctor);
  assert.equal(rules.canAttend, true); assert.equal(rules.scheduleLocked, true); assert.equal(rules.canDelete, false);
  await mount({ ...appointment, has_clinical_history: true, clinical_history_status: "in_progress" }, doctor);
  assert.match(document.body.textContent, /En atención/);
});
test("tarjeta de Agenda muestra presencia sin reemplazar hora por turno", async () => {
  await act(async () => root.render(h(AgendaAppointmentCard, { appointment: { ...fixture, arrived_at: "2030-10-15T12:30:00" }, variant: "day", onSelect: () => {} })));
  assert.match(document.body.textContent, /08:30/); assert.match(document.body.textContent, /Llegó · En espera/);
});
test("tarjeta Por turno conserva etiqueta administrativa; su estado operativo pertenece al ticket", async () => {
  await act(async () => root.render(h(AgendaAppointmentCard, { appointment: { ...fixture, schedule_mode: "queue", arrived_at: "2030-10-15T12:30:00" }, variant: "day", onSelect: () => {} })));
  assert.match(document.body.textContent, /Programada/); assert.match(document.body.textContent, /Cita por turno/);
});
