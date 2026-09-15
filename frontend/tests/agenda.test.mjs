import { after, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true, ws: false },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
const agenda = await server.ssrLoadModule("/src/components/agenda/agenda.ts");
after(async () => {
  await server.close();
});
const items = [
  {
    id: 1,
    appointment_date: "2026-09-14",
    appointment_time: "10:00:00",
    center_id: 1,
    doctor_id: 2,
    specialty_id: 3,
    status: "scheduled",
    patient_name: "Ana",
  },
  {
    id: 2,
    appointment_date: "2026-09-14",
    appointment_time: "08:30:00",
    center_id: 2,
    doctor_id: 4,
    specialty_id: 5,
    status: "confirmed",
    patient_name: "Carlos",
  },
  {
    id: 3,
    appointment_date: "2026-09-15",
    appointment_time: "09:00:00",
    center_id: 1,
    doctor_id: 2,
    specialty_id: 3,
    status: "cancelled",
    patient_name: "Bea",
  },
];
const none = { centerId: "", doctorId: "", specialtyId: "", status: "" };
test("agenda carga un día como rango único", () =>
  assert.deepEqual(agenda.rangeForView("2026-09-14", "day"), {
    start: "2026-09-14",
    end: "2026-09-14",
  }));
test("agenda carga semana con un rango de siete días", () =>
  assert.deepEqual(agenda.rangeForView("2026-09-16", "week"), {
    start: "2026-09-14",
    end: "2026-09-20",
  }));
test("citas se ordenan cronológicamente", () =>
  assert.deepEqual(
    agenda.sortByTime(items).map((item) => item.id),
    [2, 1, 3],
  ));
test("filtro de centro limita el rango cargado", () =>
  assert.deepEqual(
    agenda
      .filterAppointments(items, { ...none, centerId: "1" })
      .map((item) => item.id),
    [1, 3],
  ));
test("filtro de médico limita el rango cargado", () =>
  assert.deepEqual(
    agenda
      .filterAppointments(items, { ...none, doctorId: "4" })
      .map((item) => item.id),
    [2],
  ));
test("filtro de especialidad conserva la cita correcta", () =>
  assert.deepEqual(
    agenda
      .filterAppointments(items, { ...none, specialtyId: "3" })
      .map((item) => item.id),
    [1, 3],
  ));
test("filtro de estado usa estados reales", () =>
  assert.deepEqual(
    agenda
      .filterAppointments(items, { ...none, status: "confirmed" })
      .map((item) => item.id),
    [2],
  ));
test("labels cubren los cinco estados reales", () =>
  assert.deepEqual(Object.keys(agenda.appointmentStatusLabels), [
    "scheduled",
    "confirmed",
    "completed",
    "cancelled",
    "no_show",
  ]));
test("botón Hoy usa fecha local ISO", () =>
  assert.match(
    agenda.isoDate(new Date("2026-09-14T12:00:00")),
    /^2026-09-14$/,
  ));
test("navegación semanal inicia lunes", () =>
  assert.equal(agenda.startOfWeek("2026-09-20"), "2026-09-14"));
test("no se introduce estado en espera", () =>
  assert.equal(
    Object.hasOwn(agenda.appointmentStatusLabels, "waiting"),
    false,
  ));
test("no se introduce estado reprogramada", () =>
  assert.equal(
    Object.hasOwn(agenda.appointmentStatusLabels, "rescheduled"),
    false,
  ));

test("filtros combinados y reconciliación mantienen únicamente opciones válidas", () => {
  const scope = {
    centers: [
      { id: 1, name: "A" },
      { id: 2, name: "B" },
    ],
    doctors: [
      {
        id: 2,
        full_name: "A",
        center_ids: [1],
        specialties: [{ id: 3, name: "Interna" }],
      },
      {
        id: 4,
        full_name: "B",
        center_ids: [2],
        specialties: [{ id: 5, name: "Cardio" }],
      },
    ],
  };
  assert.deepEqual(
    agenda
      .filterAppointments(items, {
        centerId: "1",
        doctorId: "2",
        specialtyId: "3",
        status: "scheduled",
      })
      .map((x) => x.id),
    [1],
  );
  assert.deepEqual(
    agenda.reconcileFilters(
      { centerId: "2", doctorId: "2", specialtyId: "3", status: "confirmed" },
      scope,
    ),
    { centerId: "2", doctorId: "", specialtyId: "", status: "confirmed" },
  );
  assert.equal(
    agenda.reconcileFilters(
      { centerId: "", doctorId: "4", specialtyId: "3", status: "" },
      scope,
    ).specialtyId,
    "",
  );
});
test("calendario cruza años, febrero bisiesto y meses cortos", () => {
  assert.equal(agenda.addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(agenda.addDays("2028-02-28", 1), "2028-02-29");
  assert.equal(agenda.addDays("2026-02-28", 1), "2026-03-01");
  assert.equal(agenda.addDays("2026-04-30", 1), "2026-05-01");
});

test("nota adicional y atención no elevan permisos por rol administrativo ni usuario inactivo",()=>{
 const appointment={status:"completed",has_clinical_history:true,clinical_history_status:"completed",clinical_history_id:42,clinical_history_doctor_id:2,doctor_id:2};
 assert.equal(agenda.appointmentRules(appointment,{id:2,roles:["admin"],is_active:true}).canAddAddendum,false);
 assert.equal(agenda.appointmentRules(appointment,{id:9,roles:["doctor","admin"],is_active:true}).canAddAddendum,false);
 assert.equal(agenda.appointmentRules({...appointment,status:"scheduled"},{id:2,roles:["doctor"],is_active:false}).canAttend,false);
});
test("Mes carga el rango completo y navega por primer día de cada mes", () => {
 assert.deepEqual(agenda.rangeForView("2026-09-14", "month"), { start: "2026-09-01", end: "2026-09-30" });
 assert.deepEqual(agenda.rangeForView("2028-02-14", "month"), { start: "2028-02-01", end: "2028-02-29" });
 assert.equal(agenda.addMonths("2026-03-31", -1), "2026-02-01");
 assert.equal(agenda.addMonths("2026-12-15", 1), "2027-01-01");
});
test("eje semanal se limita a las horas registradas sin inferir duración", () => {
 assert.deepEqual(agenda.weekTimelineBounds([{ appointment_time: "08:30:00" }, { appointment_time: "10:15:00" }]), { startMinutes: 480, endMinutes: 660, hours: 3 });
 assert.equal(agenda.weekTimelineBounds([]), null);
 assert.equal(agenda.formatTimelineHour(600), "10:00");
});
test("workspace de Agenda no conserva un max-width global restrictivo", async () => {
 const { readFile } = await import("node:fs/promises");
 const shell = await readFile(new URL("../src/layouts/operational-shell.css", import.meta.url), "utf8");
 const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8");
 assert.match(shell, /atlas-operational-workspace--agenda\s*\{[^}]*max-width:\s*none/);
 assert.match(css, /\.agenda-page \{ max-width:none/);
 assert.match(css, /agenda-layout--panel/);
 assert.match(css, /agenda-week-grid \{ --agenda-week-hours: 1; display:grid/);
 const statusCss = await readFile(new URL("../src/components/agenda/appointment-status.css", import.meta.url), "utf8");
 assert.match(statusCss, /agenda-week-appointment-card--scheduled/);
 assert.match(statusCss, /agenda-week-appointment-card--no_show/);
 assert.match(css, /grid-template-rows:auto repeat\(6,minmax\(5\.5rem,1fr\)\)/);
 assert.match(css, /agenda-month-panel-scroll\{min-height:0;overflow-y:auto/);
});
