import { after, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const agenda = await server.ssrLoadModule("/src/components/agenda/agenda.ts");
after(async () => { await server.close(); });
const items = [
 { id: 1, appointment_date: "2026-09-14", appointment_time: "10:00:00", center_id: 1, doctor_id: 2, specialty_id: 3, status: "scheduled", patient_name: "Ana" },
 { id: 2, appointment_date: "2026-09-14", appointment_time: "08:30:00", center_id: 2, doctor_id: 4, specialty_id: 5, status: "confirmed", patient_name: "Carlos" },
 { id: 3, appointment_date: "2026-09-15", appointment_time: "09:00:00", center_id: 1, doctor_id: 2, specialty_id: 3, status: "cancelled", patient_name: "Bea" },
];
const none = { centerId: "", doctorId: "", specialtyId: "", status: "" };
test("agenda carga un día como rango único", () => assert.deepEqual(agenda.rangeForView("2026-09-14", "day"), { start: "2026-09-14", end: "2026-09-14" }));
test("agenda carga semana con un rango de siete días", () => assert.deepEqual(agenda.rangeForView("2026-09-16", "week"), { start: "2026-09-14", end: "2026-09-20" }));
test("citas se ordenan cronológicamente", () => assert.deepEqual(agenda.sortByTime(items).map((item) => item.id), [2, 1, 3]));
test("filtro de centro limita el rango cargado", () => assert.deepEqual(agenda.filterAppointments(items, { ...none, centerId: "1" }).map((item) => item.id), [1, 3]));
test("filtro de médico limita el rango cargado", () => assert.deepEqual(agenda.filterAppointments(items, { ...none, doctorId: "4" }).map((item) => item.id), [2]));
test("filtro de especialidad conserva la cita correcta", () => assert.deepEqual(agenda.filterAppointments(items, { ...none, specialtyId: "3" }).map((item) => item.id), [1, 3]));
test("filtro de estado usa estados reales", () => assert.deepEqual(agenda.filterAppointments(items, { ...none, status: "confirmed" }).map((item) => item.id), [2]));
test("labels cubren los cinco estados reales", () => assert.deepEqual(Object.keys(agenda.appointmentStatusLabels), ["scheduled", "confirmed", "completed", "cancelled", "no_show"]));
test("botón Hoy usa fecha local ISO", () => assert.match(agenda.isoDate(new Date("2026-09-14T12:00:00")), /^2026-09-14$/));
test("navegación semanal inicia lunes", () => assert.equal(agenda.startOfWeek("2026-09-20"), "2026-09-14"));
test("no se introduce estado en espera", () => assert.equal(Object.hasOwn(agenda.appointmentStatusLabels, "waiting"), false));
test("no se introduce estado reprogramada", () => assert.equal(Object.hasOwn(agenda.appointmentStatusLabels, "rescheduled"), false));
