import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";
const { dom, setDesktop } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({
  server: { middlewareMode: true, ws: false },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
const { default: Appointments } = await server.ssrLoadModule(
  "/src/pages/Appointments.tsx",
);
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const NativeDate = globalThis.Date;
const host = document.getElementById("root");
const fixture = {
  id: 8,
  patient_id: 6,
  doctor_id: 2,
  center_id: 1,
  specialty_id: 3,
  appointment_date: "2026-09-14",
  appointment_time: "08:30:00",
  reason: "Control",
  status: "scheduled",
  notes: "Nota",
  patient_name: "Ana Torres",
  patient_phone: "809-555-0101",
  patient_date_of_birth: "1988-01-01",
  doctor_name: "Dr. Osiris Valdés",
  center_name: "Centro Norte",
  center_city: "Santiago",
  specialty_name: "Medicina Interna",
  coverage_id: null,
  original_doctor_id: null,
  original_doctor_name: null,
  has_clinical_history: false,
  clinical_history_id: null,
  clinical_history_status: null,
  clinical_history_doctor_id: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};
const defaultScope = {
  centers: [
    { id: 1, name: "Centro Norte" },
    { id: 5, name: "Centro Sur" },
  ],
  doctors: [
    {
      id: 2,
      full_name: "Dr. Osiris Valdés",
      center_ids: [1],
      specialties: [
        { id: 3, name: "Medicina Interna" },
        { id: 7, name: "Cardiología" },
      ],
    },
    {
      id: 9,
      full_name: "Dra. Tania",
      center_ids: [5],
      specialties: [{ id: 11, name: "Pediatría" }],
    },
  ],
};
let root, calls, items, scope, intercept, attended, queueLines, queueTickets;
function response(config, data) {
  return { data, status: 200, statusText: "OK", headers: {}, config };
}
function fail(detail) {
  throw { response: { data: { detail } } };
}
beforeEach(() => {
  setDesktop(true);
  globalThis.Date = class extends NativeDate {
    constructor(...args) {
      super(...(args.length ? args : ["2026-09-14T12:00:00"]));
    }
    static now() {
      return new NativeDate("2026-09-14T12:00:00").getTime();
    }
  };
  root = createRoot(host);
  calls = [];
  items = [{ ...fixture }];
  scope = structuredClone(defaultScope);
  intercept = null;
  attended = [];
  queueLines = [{ id: 3, center_id: 1, doctor_id: 2, specialty_id: 3, name: "Consulta QA", prefix: "C", is_active: true, call_on_consultation_start: false }];
  queueTickets = [];
  api.defaults.adapter = async (config) => {
    calls.push(config);
    if (intercept) {
      const result = intercept(config);
      if (result !== undefined) return await result;
    }
    if (config.url === "/appointments/scope-options" && config.method === "get")
      return response(config, scope);
    if (config.url === "/appointments/effective-mode" && config.method === "get")
      return response(config, { schedule_mode: "timed" });
    if (config.url === "/appointments/queue-capabilities" && config.method === "get")
      return response(config, { booking_order_enabled: true });
    if (config.url === "/queue-lines" && config.method === "get") return response(config, queueLines);
    if (config.url === "/queue-tickets" && config.method === "get") return response(config, queueTickets);
    if (config.url === "/waiting-rooms" && config.method === "get") return response(config, []);
    if (config.url === "/queue-tickets/arrivals/8" && config.method === "post") {
      if (queueTickets.some((ticket) => ticket.appointment_id === 8)) throw { response: { status: 409, data: { detail: "Esta cita ya tiene un turno emitido" } } };
      const ticket = { id: 11, appointment_id: 8, queue_line_id: 3, public_code: "C-021", status: "waiting", arrived_at: "2026-09-14T12:05:00", sequence_number: 21 };
      queueTickets.push(ticket);
      return response(config, ticket);
    }
    if (config.url === "/appointments/doctors" && config.method === "get")
      return response(
        config,
        scope.doctors.filter((item) =>
          item.center_ids.includes(config.params.center_id),
        ),
      );
    if (config.url === "/appointments" && config.method === "get") {
      assert.match(config.params.start, /^\d{4}-\d{2}-\d{2}$/);
      assert.match(config.params.end, /^\d{4}-\d{2}-\d{2}$/);
      return response(
        config,
        items
          .filter(
            (item) =>
              item.appointment_date >= config.params.start &&
              item.appointment_date <= config.params.end,
          )
          .map((item) => ({ ...item })),
      );
    }
    if (/^\/appointments\/\d+$/.test(config.url) && config.method === "put") {
      const payload = JSON.parse(config.data);
      const index = items.findIndex(
        (item) => item.id === Number(config.url.split("/").at(-1)),
      );
      assert.ok(index >= 0);
      items[index] = { ...items[index], ...payload };
      return response(config, { ...items[index] });
    }
    if (
      /^\/appointments\/\d+$/.test(config.url) &&
      config.method === "delete"
    ) {
      items = items.filter(
        (item) => item.id !== Number(config.url.split("/").at(-1)),
      );
      return response(config, null);
    }
    if (config.url === "/appointments" && config.method === "post") {
      const item = { ...fixture, ...JSON.parse(config.data), id: 20 };
      items.push(item);
      return response(config, item);
    }
    throw new Error(`Unexpected request ${config.method} ${config.url}`);
  };
});
afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter;
  globalThis.Date = NativeDate;
});
after(async () => {
  await server.close();
  dom.window.close();
});
async function mount(roles = ["secretary"], extras = {}) {
  await act(async () => {
    root.render(
      h(Appointments, {
        user: {
          id: 2,
          full_name: "Usuario",
          email: "u@example.test",
          roles,
          is_active: true,
        },
        onBack() {},
        canAccessClinical: roles.includes("doctor"),
        onAttendAppointment(item) {
          attended.push(item.id);
        },
        ...extras,
      }),
    );
  });
}
function button(text, container = document.body) {
  return [...container.querySelectorAll("button")].find(
    (item) => item.textContent.trim() === text,
  );
}
async function click(target) {
  assert.ok(target);
  await act(async () => target.click());
}
function dialog() {
  return document.querySelector("dialog[open]");
}
function panel() {
  return host.querySelector(".agenda-month-panel");
}
function detailSurface() {
  return dialog() ?? panel();
}
function closePanel() {
  return panel()?.querySelector('[aria-label="Cerrar panel del día"], [aria-label="Cerrar detalle de cita"]');
}
function closeDetail() {
  return dialog() ? button("Cerrar", dialog()) : closePanel();
}
function control(label, container = dialog()) {
  const target = [...container.querySelectorAll("label")].find((item) =>
    item.textContent.startsWith(label),
  );
  assert.ok(target, label);
  return document.getElementById(target.htmlFor);
}
async function change(target, value) {
  await act(async () => {
    const prototype =
      target.tagName === "SELECT"
        ? dom.window.HTMLSelectElement.prototype
        : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(target, value);
    target.dispatchEvent(
      new dom.window.Event(target.tagName === "SELECT" ? "change" : "input", {
        bubbles: true,
      }),
    );
  });
}
function gets() {
  return calls.filter(
    (item) => item.url === "/appointments" && item.method === "get",
  );
}
async function open() {
  await click(host.querySelector(".agenda-week-appointment-card") ?? host.querySelector(".agenda-appointment-card"));
}
async function edit() {
  await open();
  await click(button("Editar cita", detailSurface()));
}

test("409 al reprogramar conserva datos y permite cambiar solo Hora", async () => {
  await mount(); await edit();
  const before = ["Centro", "Médico", "Fecha", "Especialidad", "Motivo", "Observaciones"]
    .map((name) => [name, control(name).value]);
  intercept = (config) => {
    if (config.method === "put" && config.url === "/appointments/8")
      throw { response: { status: 409, data: { detail: "El médico ya tiene una cita activa en ese horario." } } };
  };
  await click(button("Guardar cita", dialog()));
  assert.match(dialog().textContent, /El médico ya tiene una cita activa en ese horario\./);
  assert.match(dialog().textContent, /Ana Torres/);
  for (const [name, value] of before) assert.equal(control(name).value, value, name);
  assert.equal(button("Guardar cita", dialog()).disabled, false);
  await change(control("Hora"), "11:30");
  intercept = null;
  await click(button("Guardar cita", dialog()));
  assert.equal(items[0].appointment_time, "11:30");
  assert.equal(items[0].patient_id, fixture.patient_id);
});
function navigateDay(day) {
  return click(
    [...host.querySelectorAll(".agenda-calendar-day")].find(
      (item) => item.textContent === String(day),
    ),
  );
}

test("Día y Semana envían un único GET con start/end reales", async () => {
  await mount();
  assert.equal(gets().length, 1);
  assert.deepEqual(gets()[0].params, {
    start: "2026-09-14",
    end: "2026-09-14",
  });
  await click(button("Semana", host));
  assert.equal(gets().length, 2);
  assert.deepEqual(gets()[1].params, {
    start: "2026-09-14",
    end: "2026-09-20",
  });
  await navigateDay(16);
  assert.equal(gets().length, 2);
  await click(button("Médicos", host));
  assert.deepEqual(gets().at(-1).params, {
    start: "2026-09-16",
    end: "2026-09-16",
  });
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 0);
});
for (const [label, status] of [
  ["Confirmar", "confirmed"],
  ["Cancelar", "cancelled"],
  ["Marcar No asistió", "no_show"],
]) {
  test(`${label} usa PUT /appointments/8 con payload completo y actualiza el detalle/lista`, async () => {
    await mount();
    await open();
    await click(button(label, detailSurface()));
    const call = calls.find((item) => item.method === "put");
    assert.equal(call.url, "/appointments/8");
    assert.deepEqual(JSON.parse(call.data), {
      patient_id: 6,
      doctor_id: 2,
      center_id: 1,
      specialty_id: 3,
      appointment_date: "2026-09-14",
      appointment_time: "08:30:00",
      reason: "Control",
      status,
      notes: "Nota",
    });
    const labels = {
      confirmed: "Confirmada",
      cancelled: "Cancelada",
      no_show: "No asistió",
    };
    assert.equal(
      detailSurface().querySelector(".atlas-badge").textContent,
      labels[status],
    );
    assert.equal(
      dialog().querySelector(".atlas-badge").textContent,
      labels[status],
    );
  });
}
test("edición dentro de misma semana refresca aunque start/end no cambien", async () => {
  await mount();
  await click(button("Semana", host));
  await navigateDay(16);
  await edit();
  await change(control("Motivo"), "Control actualizado");
  const count = gets().length;
  await click(button("Guardar cita", dialog()));
  assert.equal(gets().length, count + 1);
  assert.deepEqual(gets().at(-1).params, {
    start: "2026-09-14",
    end: "2026-09-20",
  });
  assert.match(
    host.querySelector(".agenda-week-appointment-card").textContent,
    /Control actualizado/,
  );
  assert.match(host.querySelector(".agenda-month-panel").textContent, /Control actualizado/);
  assert.equal(
    host.querySelector('.agenda-calendar-day[aria-pressed="true"]').textContent,
    "14",
  );
});
test("reprogramar dentro de misma semana mueve la tarjeta y actualiza selección", async () => {
  await mount();
  await click(button("Semana", host));
  await edit();
  await change(control("Fecha"), "2026-09-15");
  await click(button("Guardar cita", dialog()));
  const days = [...host.querySelectorAll(".agenda-week-day")];
  assert.equal(days[0].querySelectorAll(".agenda-week-appointment-card").length, 0);
  assert.equal(days[1].querySelectorAll(".agenda-week-appointment-card").length, 1);
  assert.equal(
    host.querySelector('.agenda-calendar-day[aria-pressed="true"]').textContent,
    "15",
  );
  assert.match(host.querySelector(".agenda-month-panel").textContent, /martes/);
});
test("reprogramación Médicos mantiene fecha/rango/calendario y transición a Día coherentes", async () => {
  await mount();
  await click(button("Médicos", host));
  await edit();
  await change(control("Fecha"), "2026-09-15");
  await click(button("Guardar cita", dialog()));
  assert.deepEqual(gets().at(-1).params, {
    start: "2026-09-15",
    end: "2026-09-15",
  });
  assert.equal(
    host.querySelector('.agenda-calendar-day[aria-pressed="true"]').textContent,
    "15",
  );
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 1);
  await click(closePanel());
  await click(button("Día", host));
  assert.match(host.querySelector(".agenda-day h3").textContent, /martes/);
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 1);
});
test("crear cita para otra fecha refresca lista y abre el panel contextual", async () => {
  await mount(["secretary"], {
    initialPatient: {
      id: 6,
      first_name: "Ana",
      last_name: "Torres",
      date_of_birth: "1988-01-01",
      selection_token: "fixture-selection-proof",
    },
  });
  await change(control("Centro"), "1");
  await change(control("Médico"), "2");
  await change(control("Especialidad"), "7");
  await change(control("Fecha"), "2026-09-15");
  await click(button("Guardar cita", dialog()));
  const call = calls.find(
    (item) => item.method === "post" && item.url === "/appointments",
  );
  assert.equal(JSON.parse(call.data).specialty_id, 7);
  assert.equal(JSON.parse(call.data).patient_selection_token, "fixture-selection-proof");
  assert.deepEqual(gets().at(-1).params, {
    start: "2026-09-15",
    end: "2026-09-15",
  });
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 1);
  assert.match(dialog().textContent, /Ana Torres/);
});
test("respuesta y error antiguos no reemplazan Día C", async () => {
  const pending = [];
  intercept = (config) =>
    config.url === "/appointments" && config.method === "get"
      ? new Promise((resolve, reject) =>
          pending.push({ config, resolve, reject }),
        )
      : undefined;
  await mount();
  await navigateDay(15);
  await navigateDay(16);
  assert.equal(pending.length, 3);
  await act(async () =>
    pending[2].resolve(
      response(pending[2].config, [
        {
          ...fixture,
          appointment_date: "2026-09-16",
          patient_name: "Paciente C",
        },
      ]),
    ),
  );
  await act(async () =>
    pending[0].resolve(
      response(pending[0].config, [{ ...fixture, patient_name: "Paciente A" }]),
    ),
  );
  await act(async () =>
    pending[1].reject({ response: { data: { detail: "Error B" } } }),
  );
  assert.match(host.textContent, /Paciente C/);
  assert.doesNotMatch(host.textContent, /Paciente A|Error B|Cargando citas/);
});
test("fallo del nuevo rango no presenta datos del rango anterior", async () => {
  await mount();
  intercept = (config) => {
    if (config.url === "/appointments" && config.params.start === "2026-09-15")
      fail("Error de rango");
  };
  await navigateDay(15);
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 0);
  assert.match(host.textContent, /Error de rango/);
});
test("Secretaría reprograma cobertura con identidad y especialidad registradas", async () => {
  items[0] = {
    ...fixture,
    coverage_id: 4,
    original_doctor_id: 9,
    original_doctor_name: "Dra. Tania",
  };
  await mount();
  await edit();
  for (const label of ["Centro", "Médico", "Especialidad"])
    assert.equal(control(label).disabled, true);
  assert.equal(
    control("Médico").selectedOptions[0].textContent,
    fixture.doctor_name,
  );
  assert.equal(
    control("Especialidad").selectedOptions[0].textContent,
    fixture.specialty_name,
  );
  assert.equal(control("Fecha").disabled, false);
  assert.equal(control("Hora").disabled, false);
  assert.equal(button("Cambiar", dialog()), undefined);
  await change(control("Fecha"), "2026-09-15");
  await change(control("Hora"), "09:45");
  await click(button("Guardar cita", dialog()));
  const payload = JSON.parse(calls.find((item) => item.method === "put").data);
  assert.equal(payload.doctor_id, 2);
  assert.equal(payload.specialty_id, 3);
  assert.equal(payload.appointment_time, "09:45");
});
for (const roles of [["doctor"], ["admin"], ["secretary", "admin"]])
  test(`cobertura bloquea horario para ${roles.join("+")}`, async () => {
    items[0].coverage_id = 4;
    await mount(roles);
    await open();
    assert.equal(button("Reprogramar", detailSurface()), undefined);
    await click(button("Editar cita", detailSurface()));
    assert.equal(control("Fecha").disabled, true);
    assert.equal(control("Hora").disabled, true);
  });
test("consulta iniciada oculta acciones prohibidas y bloquea horario/contexto", async () => {
  items[0] = {
    ...fixture,
    has_clinical_history: true,
    clinical_history_status: "in_progress",
  };
  await mount(["doctor"]);
  await open();
  for (const label of [
    "Reprogramar",
    "Cancelar",
    "Marcar No asistió",
    "Eliminar cita",
  ])
    assert.equal(button(label, detailSurface()), undefined);
  await click(button("Editar cita", detailSurface()));
  for (const label of ["Fecha", "Hora", "Centro", "Médico", "Especialidad"])
    assert.equal(control(label).disabled, true);
  assert.ok(
    ![...control("Estado").options].some((item) =>
      ["cancelled", "no_show", "completed"].includes(item.value),
    ),
  );
});
test("médico puro protege paciente/centro/médico y conserva especialidad editable antes de historia", async () => {
  await mount(["doctor"]);
  await edit();
  assert.equal(button("Cambiar", dialog()), undefined);
  assert.equal(control("Centro").disabled, true);
  assert.equal(control("Médico").disabled, true);
  assert.equal(control("Especialidad").disabled, false);
  assert.equal(control("Fecha").disabled, false);
});
for (const roles of [
  ["doctor", "admin"],
  ["doctor", "secretary"],
])
  test(`multirol ${roles.join("+")} atiende únicamente sus citas`, async () => {
    items.push({
      ...fixture,
      id: 9,
      doctor_id: 9,
      patient_name: "Paciente ajeno",
    });
    await mount(roles);
    await click(host.querySelectorAll(".agenda-appointment-card")[1]);
    assert.equal(button("Iniciar consulta", detailSurface()), undefined);
    await click(closeDetail());
    await open();
    await click(button("Iniciar consulta", detailSurface()));
    assert.deepEqual(attended, [8]);
  });
test("Admin puro no recibe acceso clínico", async () => {
  await mount(["admin"]);
  await open();
  assert.equal(button("Iniciar consulta", detailSurface()), undefined);
});
test("errores de PUT y DELETE son visibles dentro del panel activo", async () => {
  intercept = (config) => {
    if (config.method === "put" || config.method === "delete")
      fail("Operación rechazada por Atlas");
  };
  await mount();
  await open();
  await click(button("Confirmar", detailSurface()));
  assert.match(
    detailSurface().querySelector('[role="alert"]').textContent,
    /Operación rechazada/,
  );
  assert.equal(button("Confirmar", detailSurface()).disabled, false);
  const originalConfirm = window.confirm;
  window.confirm = () => true;
  try {
    await click(button("Eliminar cita", detailSurface()));
    assert.match(
      detailSurface().querySelector('[role="alert"]').textContent,
      /Operación rechazada/,
    );
  } finally {
    window.confirm = originalConfirm;
  }
});
test("Eliminar reutiliza DELETE, cierra el panel y refresca lista", async () => {
  const originalConfirm = window.confirm;
  window.confirm = () => true;
  try {
    await mount();
    await open();
    await click(button("Eliminar cita", detailSurface()));
    assert.ok(
      calls.some(
        (item) => item.method === "delete" && item.url === "/appointments/8",
      ),
    );
    assert.equal(dialog(), null);
    assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 0);
  } finally {
    window.confirm = originalConfirm;
  }
});
test("nota adicional solo está disponible para autor médico de consulta completada", async () => {
  items[0] = {
    ...fixture,
    status: "completed",
    has_clinical_history: true,
    clinical_history_status: "completed",
    clinical_history_id: 42,
    clinical_history_doctor_id: 2,
  };
  await mount(["doctor", "admin"]);
  await open();
  assert.ok(button("Agregar nota adicional", detailSurface()));
  assert.equal(button("Eliminar cita", detailSurface()), undefined);
  assert.equal(button("Editar cita", detailSurface()), undefined);
});
test("filtros combinados reconcilian especialidad al cambiar centro/médico y scope", async () => {
  items.push({
    ...fixture,
    id: 9,
    specialty_id: 7,
    specialty_name: "Cardiología",
  });
  await mount();
  const filters = host.querySelector(".agenda-filters");
  const selects = filters.querySelectorAll("select");
  await change(selects[0], "1");
  await change(selects[1], "2");
  await change(selects[2], "7");
  await change(selects[3], "scheduled");
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 1);
  assert.match(
    host.querySelector(".agenda-appointment-card").textContent,
    /Cardiología/,
  );
  await change(selects[0], "5");
  assert.equal(selects[1].value, "");
  assert.equal(selects[2].value, "");
  await click(button("Limpiar filtros", filters));
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 2);
  await change(selects[1], "2");
  await change(selects[2], "7");
  scope.doctors = scope.doctors.filter((item) => item.id !== 2);
  await navigateDay(15);
  assert.equal(selects[1].value, "");
  assert.equal(selects[2].value, "");
});
test("homónimos no se fusionan y cada cita conserva especialidad y estado en las tres vistas", async () => {
  items = [
    { ...fixture },
    {
      ...fixture,
      id: 9,
      doctor_id: 9,
      specialty_id: 7,
      specialty_name: "Cardiología",
      status: "confirmed",
    },
  ];
  await mount();
  assert.equal(host.querySelectorAll(".agenda-event-status").length, 2);
  await click(button("Semana", host));
  assert.equal(host.querySelectorAll(".agenda-week-appointment-card").length, 2);
  assert.deepEqual([...host.querySelectorAll(".agenda-event-status")].map((item) => item.textContent), ["Programada", "Confirmada"]);
  await click(button("Médicos", host));
  assert.equal(host.querySelectorAll(".agenda-doctor-group").length, 2);
  assert.match(host.textContent, /Medicina Interna/);
  assert.match(host.textContent, /Cardiología/);
  assert.deepEqual(
    [...host.querySelectorAll(".agenda-event-status")].map((item) => item.textContent),
    ["Programada", "Confirmada"],
  );
});
test("selector de paciente tiene IDs únicos, búsqueda principal y verificación secundaria; Agenda no crea main", async () => {
  await mount();
  await click(button("+ Nueva cita", host));
  const inputs = dialog().querySelectorAll("input");
  const ids = [...inputs].map((item) => item.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.match(inputs[0].labels[0].textContent, /Paciente/);
  assert.match(inputs[0].placeholder, /nombre, cédula, teléfono o correo/);
  assert.match(dialog().querySelector(".agenda-patient-verification").textContent, /Teléfono o correo exacto/);
  assert.equal(host.querySelector("main"), null);
});

test("Agregar nota adicional abre el flujo existente y usa su POST sin editar la consulta", async () => {
  items[0] = { ...fixture, status: "completed", has_clinical_history: true, clinical_history_status: "completed", clinical_history_id: 42, clinical_history_doctor_id: 2 };
  const history = { id: 42, patient_id: 6, appointment_id: 8, doctor_id: 2, center_id: 1, specialty_id: 3, specialty_name: "Medicina Interna", doctor_name: fixture.doctor_name, center_name: fixture.center_name, status: "completed", consultation_date: "2026-09-14", requested_tests: [], reason_for_visit: "Control", created_at: "2026-09-14", updated_at: "2026-09-14" };
  intercept = (config) => {
    if (config.url === "/clinical-history/patients/6") return response(config, [history]);
    if (config.method === "get" && /^\/clinical-history\/42\//.test(config.url)) return response(config, config.url.endsWith("vital-signs") ? null : []);
    if (config.method === "post" && config.url === "/clinical-history/42/addenda") return response(config, { id: 1, clinical_history_id: 42, author_user_id: 2, author_name: "Usuario", ...JSON.parse(config.data), created_at: "2026-09-14" });
  };
  await mount(["doctor"]); await open(); await click(button("Agregar nota adicional", detailSurface()));
  const addendum = document.querySelector('[aria-label="Agregar nota clínica adicional"]'); assert.ok(addendum);
  await change(addendum.querySelector("input"), "Aclaración administrativa ficticia"); await click(button("Guardar nota adicional", addendum));
  const call = calls.find((item) => item.method === "post" && item.url === "/clinical-history/42/addenda");
  assert.deepEqual(JSON.parse(call.data), { reason: "Aclaración administrativa ficticia", note: null });
  assert.ok(!calls.some((item) => item.method === "put")); assert.match(host.textContent, /Nota adicional registrada/);
});

test("las cinco etiquetas de estado permanecen en Semana y Médicos", async () => {
 items = ["scheduled","confirmed","completed","cancelled","no_show"].map((status,index)=>({...fixture,id:index+1,status}));
 await mount();
 await click(button("Semana",host));
 assert.deepEqual([...host.querySelectorAll(".agenda-event-status")].map(item=>item.textContent),["Programada","Confirmada","Completada","Cancelada","No asistió"]);
 await click(button("Médicos",host));
 assert.deepEqual([...host.querySelectorAll(".agenda-event-status")].map(item=>item.textContent),["Programada","Confirmada","Completada","Cancelada","No asistió"]);
});

test("Semana usa eje horario, tarjetas delimitadas y el panel único para lista y detalle", async () => {
  items = [
    { ...fixture, appointment_time: "08:30:00", status: "scheduled" },
    { ...fixture, id: 9, patient_name: "Berta", appointment_time: "10:15:00", status: "cancelled", specialty_name: "Cardiología", reason: "Motivo muy extenso que queda contenido" },
  ];
  await mount(); await click(button("Semana", host));
  assert.equal(host.querySelector('[role="grid"][aria-label="Agenda semanal por hora"]') !== null, true);
  assert.match(host.querySelector(".agenda-week-grid").textContent, /Hora[\s\S]*08:00[\s\S]*09:00[\s\S]*10:00/);
  const card = host.querySelector(".agenda-week-appointment-card.agenda-appointment-card--cancelled");
  assert.match(card.textContent, /10:15[\s\S]*Berta[\s\S]*Motivo muy extenso[\s\S]*Cardiología[\s\S]*Cancelada/);
  await click(host.querySelector(".agenda-week-day-heading"));
  assert.match(host.textContent, /Citas del día/); assert.equal(host.querySelectorAll(".agenda-day-list-item").length, 2);
  await click(host.querySelector(".agenda-day-list-item"));
  assert.match(host.textContent, /Detalle de la cita/); assert.equal(document.querySelector("dialog[open]"), null);
  await click(button("← Citas del día", host)); await click(host.querySelector('[aria-label="Cerrar panel del día"]'));
  assert.equal(host.querySelector(".agenda-month-panel"), null);
});

test("Mes hace una carga mensual, abre lista completa, detalle y libera panel", async () => {
  items = Array.from({ length: 5 }, (_, index) => ({ ...fixture, id: index + 1, patient_name: `Paciente ${index + 1}`, appointment_time: `0${8 + index}:00:00` }));
  await mount(); await click(button("Mes", host));
  assert.deepEqual(gets().at(-1).params, { start: "2026-09-01", end: "2026-09-30" });
  const day = [...host.querySelectorAll(".agenda-month-day")].find((item) => item.querySelector(".agenda-month-date").textContent === "14" && !item.classList.contains("agenda-month-day--outside"));
  await click(day); assert.match(host.textContent, /Citas del día/); assert.equal(host.querySelectorAll(".agenda-day-list-item").length, 5); assert.match(host.textContent, /\+2 más/);
  await click(host.querySelector(".agenda-day-list-item")); assert.match(host.textContent, /Detalle de la cita/); assert.equal(document.querySelector("dialog[open]"), null);
  await click(button("← Citas del día", host)); assert.equal(host.querySelectorAll(".agenda-day-list-item").length, 5);
  await click(host.querySelector('[aria-label="Cerrar panel del día"]')); assert.equal(host.querySelector(".agenda-month-panel"), null);
});

test("click directo de una cita mensual abre detalle en el mismo panel", async () => {
  await mount(); await click(button("Mes", host));
  await click(host.querySelector(".agenda-month-entry"));
  assert.match(host.textContent, /Detalle de la cita/); assert.equal(document.querySelectorAll("dialog[open]").length, 0);
});

test("+N más abre la lista completa del día sin expandir su celda", async () => {
  items = Array.from({ length: 5 }, (_, index) => ({ ...fixture, id: index + 1, patient_name: `Paciente ${index + 1}`, appointment_time: `0${8 + index}:00:00` }));
  await mount(); await click(button("Mes", host));
  await click(button("+2 más", host));
  assert.match(host.textContent, /Citas del día/);
  assert.equal(host.querySelectorAll(".agenda-day-list-item").length, 5);
});

test("Mes aplica filtros antes de construir la lista del día", async () => {
  items = [{ ...fixture }, { ...fixture, id: 9, specialty_id: 7, specialty_name: "Cardiología" }];
  await mount(); await click(button("Mes", host));
  const selects = host.querySelector(".agenda-filters").querySelectorAll("select"); await change(selects[2], "7");
  const day = [...host.querySelectorAll(".agenda-month-day")].find((item) => item.querySelector(".agenda-month-date").textContent === "14" && !item.classList.contains("agenda-month-day--outside"));
  await click(day); assert.equal(host.querySelectorAll(".agenda-day-list-item").length, 1); assert.match(host.textContent, /Cardiología/);
});

test("Día abre el detalle modal y Médicos conserva el panel contextual", async () => {
  await mount();
  await click(host.querySelector(".agenda-appointment-card--day"));
  assert.match(dialog().textContent, /Detalle de cita/);
  assert.equal(panel(), null);
  assert.ok(host.querySelector(".agenda-day-grid"));
  await click(closeDetail());
  await click(button("Médicos", host));
  await click(host.querySelector(".agenda-appointment-card--doctor"));
  assert.match(panel().textContent, /Detalle de la cita/);
  assert.equal(dialog(), null);
  assert.ok(host.querySelector(".agenda-doctor-group"));
});

test("detalle modal de Día cierra por backdrop, botón, Escape y conserva contexto", async () => {
  await mount();
  const filters = host.querySelector(".agenda-filters").querySelectorAll("select");
  await change(filters[3], "scheduled");
  const trigger = host.querySelector(".agenda-appointment-card--day");
  trigger.focus(); // jsdom click() does not apply native mouse focus before opening.
  const initialGets = gets().length;
  await click(trigger);
  const modal = dialog();
  await click(modal.querySelector(".atlas-dialog-body"));
  assert.ok(dialog(), "un click dentro del contenido no debe cerrar");
  await act(async () => modal.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
  assert.equal(dialog(), null, "el backdrop debe cerrar el modal");
  assert.equal(document.activeElement, trigger, "el foco vuelve a la cita que abrió el modal");
  assert.equal(filters[3].value, "scheduled");
  assert.equal(host.querySelector('.agenda-calendar-day[aria-pressed="true"]').textContent, "14");
  assert.equal(gets().length, initialGets, "cerrar no recarga la Agenda");
  await click(trigger);
  await click(button("Cerrar", dialog()));
  assert.equal(dialog(), null, "el botón Cerrar debe funcionar");
  await click(trigger);
  await act(async () => dialog().dispatchEvent(new dom.window.Event("cancel", { bubbles: true, cancelable: true })));
  assert.equal(dialog(), null, "Escape debe seguir cerrando el modal");
});

test("las tarjetas comparten color y texto de estado en las cuatro vistas", async () => {
  const statuses = ["scheduled", "confirmed", "completed", "cancelled", "no_show"];
  items = statuses.map((status, index) => ({ ...fixture, id: index + 1, status }));
  await mount();
  for (const status of statuses)
    assert.ok(host.querySelector(`.agenda-appointment-card--day.agenda-appointment-card--${status}`));
  await click(button("Semana", host));
  for (const status of statuses)
    assert.ok(host.querySelector(`.agenda-week-appointment-card.agenda-appointment-card--${status}`));
  await click(button("Mes", host));
  await click(button("+2 más", host));
  for (const status of statuses) {
    const card = host.querySelector(`.agenda-day-list-item.agenda-appointment-card--${status}`);
    assert.ok(card);
    assert.match(card.textContent, /Programada|Confirmada|Completada|Cancelada|No asistió/);
  }
  await click(host.querySelector('[aria-label="Cerrar panel del día"]'));
  await click(button("Médicos", host));
  for (const status of statuses)
    assert.ok(host.querySelector(`.agenda-appointment-card--doctor.agenda-appointment-card--${status}`));
});

test("Semana móvil renderiza una sola lista legible y vuelve a cuadrícula al ampliar", async () => {
  items = [{...fixture}, {...fixture,id:9,appointment_date:"2026-09-15",status:"confirmed"}];
  await mount();
  await act(async () => setDesktop(false));
  await click(button("Semana", host));
  assert.equal(host.querySelector(".agenda-week-grid"), null);
  assert.equal(host.querySelectorAll(".agenda-week-mobile .agenda-appointment-card").length, 2);
  assert.deepEqual([...host.querySelectorAll(".agenda-week-mobile .agenda-event-status")].map((item) => item.textContent), ["Programada", "Confirmada"]);
  const headings = [...host.querySelectorAll(".agenda-week-mobile .agenda-day h3")];
  assert.equal(new Set(headings.map((item) => item.id)).size, 2);
  const before = gets().length;
  await act(async () => setDesktop(true));
  assert.ok(host.querySelector(".agenda-week-grid"));
  assert.equal(host.querySelector(".agenda-week-mobile"), null);
  assert.equal(gets().length, before);
});

test("calendario/filtros móvil se despliegan y conservan filtro al cerrar detalle Día", async () => {
  await mount();
  await act(async () => setDesktop(false));
  const toggle = host.querySelector(".agenda-mobile-filter-toggle");
  const sidebar = host.querySelector(".agenda-sidebar");
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(toggle.getAttribute("aria-controls"), sidebar.id);
  await click(toggle);
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  assert.ok(!sidebar.classList.contains("agenda-sidebar--collapsed"));
  const filters = sidebar.querySelectorAll("select");
  await change(filters[3], "scheduled");
  const before = gets().length;
  await click(toggle);
  const trigger = host.querySelector(".agenda-appointment-card--day");
  trigger.focus();await click(trigger);await click(button("Cerrar",dialog()));
  assert.equal(filters[3].value,"scheduled");
  assert.equal(gets().length,before);
  assert.equal(document.activeElement,trigger);
});

test("cada vista muestra el teléfono de su paciente y tolera la ausencia de contacto", async () => {
  items = [
    { ...fixture, id: 8, patient_id: 6, patient_name: "Ana Torres", patient_phone: "809-555-0101" },
    { ...fixture, id: 9, patient_id: 7, patient_name: "Berta Díaz", patient_phone: "829-555-0202", appointment_time: "09:30:00" },
    { ...fixture, id: 10, patient_id: 8, patient_name: "Carlos Pérez", patient_phone: null, appointment_time: "10:30:00" },
  ];
  await mount();
  const expected = [
    ["Ana Torres", "809-555-0101"],
    ["Berta Díaz", "829-555-0202"],
    ["Carlos Pérez", "Sin teléfono"],
  ];
  for (const [view, selector] of [
    [null, ".agenda-appointment-card--day"],
    ["Semana", ".agenda-week-appointment-card"],
    ["Mes", ".agenda-month-entry"],
    ["Médicos", ".agenda-appointment-card--doctor"],
  ]) {
    if (view) await click(button(view, host));
    const cards = [...host.querySelectorAll(selector)];
    assert.equal(cards.length, 3);
    for (const [index, [name, phone]] of expected.entries()) {
      assert.match(cards[index].textContent, new RegExp(name));
      assert.equal(cards[index].querySelector(".agenda-patient-phone").textContent, phone);
      for (const [otherName, otherPhone] of expected) {
        if (otherName !== name && otherPhone !== "Sin teléfono") assert.doesNotMatch(cards[index].textContent, new RegExp(otherPhone));
      }
    }
    if (view === "Mes") {
      await click(cards[1]);
      assert.match(host.querySelector(".agenda-details").textContent, /Teléfono[\s\S]*829-555-0202/);
      await click(host.querySelector('[aria-label="Cerrar detalle de cita"]'));
      const day = [...host.querySelectorAll(".agenda-month-day")].find((item) => item.querySelector(".agenda-month-date").textContent === "14" && !item.classList.contains("agenda-month-day--outside"));
      await click(day);
      assert.deepEqual([...host.querySelectorAll(".agenda-day-list-item .agenda-patient-phone")].map((item) => item.textContent), expected.map(([, phone]) => phone));
      await click(host.querySelector('[aria-label="Cerrar panel del día"]'));
    }
  }
  await click(host.querySelectorAll(".agenda-appointment-card--doctor")[2]);
  assert.match(host.querySelector(".agenda-details").textContent, /Teléfono[\s\S]*Sin teléfono/);
});

test("Mes móvil usa el mismo Drawer para lista/detalle, volver, Escape y contexto", async () => {
  await mount();await act(async () => setDesktop(false));await click(button("Mes",host));
  const trigger = [...host.querySelectorAll(".agenda-month-day")].find((item) => item.querySelector(".agenda-month-date").textContent === "14" && !item.classList.contains("agenda-month-day--outside"));
  trigger.focus();await click(trigger);
  const drawer = dialog();assert.ok(drawer.classList.contains("atlas-dialog--drawer"));
  const before = gets().length;
  await click(drawer.querySelector(".agenda-day-list-item"));
  assert.equal(dialog(),drawer);
  assert.match(drawer.querySelector(".atlas-dialog-header").textContent,/Detalle de la cita/);
  await click(button("← Citas del día",drawer));
  assert.equal(dialog(),drawer);
  assert.match(drawer.querySelector(".atlas-dialog-header").textContent,/Citas del día/);
  await act(async () => drawer.dispatchEvent(new dom.window.Event("cancel",{cancelable:true})));
  assert.equal(dialog(),null);
  assert.equal(document.activeElement,trigger);
  assert.equal(gets().length,before);
  assert.equal(host.querySelector('[aria-pressed="true"]').textContent,"Mes");
});

test("bloques independientes separan fecha, llegadas y controles de vista con estado accesible", async () => {
  await mount();
  const page = host.querySelector(".agenda-page");
  const stack = page.querySelector(".agenda-controls-stack");
  const operations = page.querySelector(".agenda-operational-panels");
  const dateNavigation = page.querySelector('[aria-label="Navegación de fechas"]');
  const contacts = page.querySelector(".agenda-contacts-block");
  const arrivalsBlock = page.querySelector(".agenda-arrivals-block");
  const viewControls = page.querySelector('[aria-label="Controles de vista de Agenda"]');
  const todayAction = viewControls.querySelector(".agenda-today-action");
  const viewSwitch = viewControls.querySelector('[aria-label="Modo de visualización de Agenda"]');
  const content = page.querySelector(".agenda-layout");
  assert.ok(dateNavigation);
  assert.ok(arrivalsBlock);
  assert.ok(viewControls);
  assert.ok(content);
  assert.ok(stack);
  assert.ok(operations);
  assert.equal(stack.parentElement, page);
  assert.equal(dateNavigation.parentElement, stack);
  assert.equal(viewControls.parentElement, stack);
  assert.equal(operations.parentElement, page);
  assert.equal(contacts.parentElement, operations);
  assert.equal(arrivalsBlock.parentElement, operations);
  assert.equal(content.parentElement, page);
  assert.ok(stack.compareDocumentPosition(operations) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.ok(operations.compareDocumentPosition(content) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.ok(contacts.compareDocumentPosition(arrivalsBlock) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.ok(viewControls.compareDocumentPosition(content) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.equal(operations.contains(todayAction), false);
  assert.equal(arrivalsBlock.contains(viewSwitch), false);
  assert.ok(todayAction);
  assert.ok(viewSwitch);
  assert.equal(todayAction.contains(viewSwitch), false);
  assert.equal(dateNavigation.contains(viewSwitch), false);
  assert.deepEqual([...viewSwitch.querySelectorAll("button")].map(item => item.textContent.trim()), ["Día", "Semana", "Mes", "Médicos"]);
  assert.equal(button("Día", viewSwitch).getAttribute("aria-pressed"), "true");
  assert.equal(button("Día", viewSwitch).getAttribute("aria-current"), "true");
  await click(button("Semana", viewSwitch));
  assert.equal(button("Semana", viewSwitch).getAttribute("aria-pressed"), "true");
  assert.equal(button("Día", viewSwitch).hasAttribute("aria-current"), false);
  await click(button("Mes", viewSwitch));
  assert.equal(button("Mes", viewSwitch).getAttribute("aria-current"), "true");
  await click(dateNavigation.querySelector('[aria-label="Fecha siguiente"]'));
  assert.match(dateNavigation.querySelector(".agenda-date-context span").textContent, /octubre/i);
  assert.equal(todayAction.querySelector('[aria-label="Ir a hoy"]').textContent.trim(), "Hoy");
  await click(dateNavigation.querySelector('[aria-label="Fecha anterior"]'));
  assert.match(dateNavigation.querySelector(".agenda-date-context span").textContent, /septiembre/i);
});

test("Agenda blocks have stable IDs and responsive structure for future personalization", async () => {
  await mount();
  const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8");
  const shellCss = await readFile(new URL("../src/layouts/operational-shell.css", import.meta.url), "utf8");
  assert.match(css, /\.agenda-date-navigation\s*\{/);
  assert.match(css, /\.agenda-controls-stack\s*\{/);
  assert.match(css, /\.agenda-operational-panels\s*\{/);
  assert.match(css, /\.agenda-arrivals-panel\s*\{/);
  assert.match(css, /\.agenda-view-controls\s*\{/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /@media\(max-width:1199px\)/);
  assert.match(css, /@media\(max-width:639px\)/);
  assert.match(css, /@media\s*\(max-width:\s*1023px\)/);
  assert.match(css, /@media\s*\(max-width:\s*639px\)/);
  assert.match(css, /min-height:44px/);
  assert.match(css, /\.agenda-controls-stack\{grid-template-columns:minmax\(0,1fr\) auto;align-items:center\}/);
  assert.match(css, /\.agenda-operational-panels>\.is-expanded\{grid-column:1\/-1\}/);
  const viewSwitchRule = css.match(/\.agenda-view-switch\s*\{[^}]*\}/)?.[0] ?? "";
  assert.ok(viewSwitchRule);
  assert.doesNotMatch(viewSwitchRule, /position\s*:/);
  assert.match(shellCss, /\.agenda-page \.agenda-mobile-filter-toggle/);
  assert.match(shellCss, /\.atlas-operational-workspace--agenda:has\(\.agenda-page--operational-expanded\)/);
  const page = host.querySelector(".agenda-page");
  for (const id of ["agenda.controls", "agenda.date-navigation", "agenda.view-controls", "agenda.contacts", "agenda.arrivals", "agenda.sidebar", "agenda.calendar", "agenda.filters", "agenda.legend", "agenda.schedule"]) {
    assert.ok(page.querySelector(`[data-atlas-block-id="${id}"]`), id);
  }
  for (const selector of [".agenda-controls-stack", ".agenda-operational-panels", ".agenda-contacts-block", ".agenda-arrivals-block", ".agenda-layout"]) {
    const block = page.querySelector(selector);
    assert.ok(block);
    assert.equal(block.parentElement, selector === ".agenda-contacts-block" || selector === ".agenda-arrivals-block"
      ? page.querySelector(".agenda-operational-panels") : page);
    assert.equal(block.closest(".agenda-toolbar"), null);
    assert.doesNotMatch(block.getAttribute("style") ?? "", /position\s*:/);
  }
});

test("Contactos previos y Llegadas y turnos se expanden en flujo con aria controls", async () => {
  await mount();
  const contactsToggle = host.querySelector(".agenda-contacts-block .agenda-operational-toggle");
  const contactsPanel = document.getElementById(contactsToggle.getAttribute("aria-controls"));
  assert.equal(contactsToggle.getAttribute("aria-expanded"), "false");
  assert.equal(contactsPanel.hidden, true);
  assert.equal(host.querySelector(".agenda-page--operational-expanded"), null);
  await click(contactsToggle);
  assert.equal(contactsToggle.getAttribute("aria-expanded"), "true");
  assert.equal(contactsPanel.hidden, false);
  assert.ok(host.querySelector(".agenda-page--operational-expanded"));

  const arrivalsToggle = host.querySelector(".agenda-arrivals-block .agenda-operational-toggle");
  const arrivalsPanel = document.getElementById(arrivalsToggle.getAttribute("aria-controls"));
  const schedule = host.querySelector('[data-atlas-block-id="agenda.schedule"]');
  assert.equal(arrivalsToggle.getAttribute("aria-expanded"), "false");
  assert.equal(arrivalsPanel.hidden, true);
  await click(arrivalsToggle);
  assert.equal(arrivalsToggle.getAttribute("aria-expanded"), "true");
  assert.equal(arrivalsPanel.hidden, false);
  assert.ok(host.querySelector(".agenda-page--operational-expanded"));
  assert.ok(arrivalsPanel.querySelector('[aria-label="Llegadas y turnos"]'));
  assert.ok(arrivalsPanel.compareDocumentPosition(schedule) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.equal(arrivalsPanel.closest(".agenda-view-controls"), null);
});

test("empty appointments render a composed empty-state block", async () => {
  items = [];
  await mount();
  assert.ok(host.querySelector(".agenda-empty-state"));
  assert.ok(host.querySelector(".agenda-empty-state-icon svg[aria-hidden='true']"));
  assert.match(host.querySelector(".agenda-empty-state").textContent, /No hay citas para esta fecha/);
});

test("detalle Día registra una sola llegada, muestra código real y conserva las otras acciones", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount(); await open();
  const actions = dialog().querySelector(".agenda-drawer-actions");
  assert.ok(button("Registrar llegada", actions));
  assert.ok(button("Editar cita", actions));
  assert.ok(button("Reprogramar", actions));
  assert.ok(button("Cancelar", actions));
  assert.ok(button("Marcar No asistió", actions));
  assert.ok(button("Eliminar cita", actions));
  assert.ok([...actions.querySelectorAll("button")].indexOf(button("Registrar llegada", actions)) <
    [...actions.querySelectorAll("button")].indexOf(button("Editar cita", actions)));
  const previousGets = gets().length;
  await click(button("Registrar llegada", actions));
  assert.deepEqual(JSON.parse(calls.find((call) => call.url === "/queue-tickets/arrivals/8").data), { queue_line_id: 3 });
  assert.equal(queueTickets.length, 1);
  assert.equal(queueTickets[0].status, "waiting");
  assert.match(dialog().textContent, /Llegada registrada · Turno C-021 · Estado: En espera/);
  assert.equal(button("Registrar llegada", dialog()), undefined);
  assert.ok(gets().length > previousGets, "la Agenda se refresca sin recargar la página");
  await click(button("Cerrar", dialog())); await open();
  assert.match(dialog().textContent, /Turno C-021/);
  assert.equal(button("Registrar llegada", dialog()), undefined);
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/arrivals/8").length, 1);
});

test("doble clic y conflicto 409 recuperan el turno existente sin duplicarlo", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  intercept = (config) => {
    if (config.method !== "post" || config.url !== "/queue-tickets/arrivals/8") return;
    queueTickets.push({ id: 11, appointment_id: 8, queue_line_id: 3, public_code: "C-021", status: "waiting", arrived_at: "2026-09-14T12:05:00" });
    throw { response: { status: 409, data: { detail: "Esta cita ya tiene un turno emitido" } } };
  };
  await mount(); await open();
  const control = button("Registrar llegada", dialog());
  await act(async () => { control.click(); control.click(); });
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/arrivals/8").length, 1);
  assert.equal(queueTickets.length, 1);
  assert.match(dialog().textContent, /Llegada registrada · Turno C-021/);
  assert.equal(button("Registrar llegada", dialog()), undefined);
});

test("cancelada, no asistió y llegada por hora pendiente de activación no ofrecen acción", async () => {
  items = [
    { ...fixture, id: 8, schedule_mode: "queue", status: "cancelled" },
    { ...fixture, id: 9, schedule_mode: "queue", status: "no_show" },
    { ...fixture, id: 10, schedule_mode: "timed", status: "scheduled", arrival_enabled: false },
  ];
  await mount();
  for (const card of [...host.querySelectorAll(".agenda-appointment-card--day")]) {
    await click(card);
    assert.equal(button("Registrar llegada", dialog()), undefined);
    await click(button("Cerrar", dialog()));
  }
  assert.equal(calls.filter((call) => call.method === "post" && call.url?.includes("/arrivals/")).length, 0);
});

test("sin línea activa no muestra Registrar llegada", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  queueLines = [];
  await mount(); await open();
  assert.equal(button("Registrar llegada", dialog()), undefined);
});

test("rol sin permiso efectivo no puede registrar llegada", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount(["secretary"], { user: {
    id: 2, full_name: "Usuario", email: "u@example.test", roles: ["secretary"],
    is_active: true, permissions: [], denied_permissions: ["patients:access"],
  } });
  await open();
  assert.equal(button("Registrar llegada", dialog()), undefined);
  assert.equal(calls.some((call) => call.url === "/queue-tickets/arrivals/8"), false);
});

test("fuera del alcance de centro y médico no ofrece llegada", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  scope.doctors = [];
  await mount();
  await open();
  assert.equal(button("Registrar llegada", dialog()), undefined);
  assert.equal(calls.some((call) => call.url === "/queue-lines"), false);
});

test("fecha distinta a la jornada actual no ofrece registrar llegada", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  globalThis.Date = class extends NativeDate {
    constructor(...args) { super(...(args.length ? args : ["2026-09-15T12:00:00"])); }
    static now() { return new NativeDate("2026-09-15T12:00:00").getTime(); }
  };
  await mount();
  await click(host.querySelector('[aria-label="Fecha anterior"]'));
  await open();
  assert.equal(button("Registrar llegada", dialog()), undefined);
});

test("varias líneas requieren selección explícita antes de emitir el turno", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  queueLines.push({ ...queueLines[0], id: 4, name: "Consulta QA 2", prefix: "D" });
  await mount(); await open();
  assert.equal(button("Registrar llegada", dialog()).disabled, true);
  const select = [...dialog().querySelectorAll("label")].find((item) => item.textContent.startsWith("Línea de turnos")).querySelector("select");
  await change(select, "3");
  assert.equal(button("Registrar llegada", dialog()).disabled, false);
  await click(button("Registrar llegada", dialog()));
  assert.equal(queueTickets.length, 1);
});

test("Semana y Mes ofrecen la misma llegada en el detalle contextual", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount();
  await click(button("Semana", host));
  await click(host.querySelector(".agenda-week-appointment-card"));
  assert.ok(button("Registrar llegada", panel()));
  await click(host.querySelector('[aria-label="Cerrar detalle de cita"]'));
  await click(button("Mes", host));
  await click(host.querySelector(".agenda-month-entry"));
  assert.ok(button("Registrar llegada", panel()));
  await click(button("Registrar llegada", panel()));
  assert.match(panel().textContent, /Turno C-021 · Estado: En espera/);
  assert.equal(button("Registrar llegada", panel()), undefined);
});

test("Día registra llegada desde la fila y muestra código y estado sin abrir detalle", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount();
  const row = host.querySelector(".agenda-appointment-entry--day");
  assert.ok(row);
  assert.match(row.textContent, /Programada/);
  assert.ok(button("Registrar llegada", row));
  assert.equal(dialog(), null);
  const action = button("Registrar llegada", row);
  await act(async () => { action.click(); action.click(); });
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/arrivals/8").length, 1);
  assert.equal(queueTickets.length, 1);
  assert.equal(queueTickets[0].status, "waiting");
  const updated = host.querySelector(".agenda-appointment-entry--day");
  assert.match(updated.textContent, /✓ Llegada registrada[\s\S]*Turno C-021[\s\S]*Estado: En espera/);
  assert.equal(button("Registrar llegada", updated), undefined);
  assert.equal(dialog(), null);
  await click(host.querySelector(".agenda-arrivals-block .agenda-operational-toggle"));
  assert.match(host.querySelector(".agenda-page").textContent, /C-021/);
});

test("ticket ya existente oculta la acción en fila, pero conserva su resultado", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  queueTickets = [{ id: 11, appointment_id: 8, queue_line_id: 3, public_code: "C-021", status: "waiting" }];
  await mount();
  const row = host.querySelector(".agenda-appointment-entry--day");
  assert.equal(button("Registrar llegada", row), undefined);
  assert.match(row.textContent, /Turno C-021[\s\S]*Estado: En espera/);
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/arrivals/8").length, 0);
});

test("Agenda administrativa avisa cuando la cita queue no tiene línea válida", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  queueLines = [];
  await mount(["admin"]);
  const row = host.querySelector(".agenda-appointment-entry--day");
  assert.equal(button("Registrar llegada", row), undefined);
  assert.match(row.textContent, /Este médico no tiene una línea de turnos configurada para este centro/);
  assert.equal(calls.filter((call) => call.url === "/queue-tickets/arrivals/8").length, 0);
});

test("queue sin hora muestra Orden de agenda y Turno independiente en Día, Semana y Mes", async () => {
  items = [{ ...fixture, schedule_mode: "queue", appointment_time: null, daily_booking_order: 7 }];
  await mount();
  const row = host.querySelector(".agenda-queue-table-row");
  assert.ok(row);
  assert.match(host.querySelector(".agenda-queue-table-head").textContent, /Orden de agenda[\s\S]*Turno/);
  assert.match(row.textContent, /7[\s\S]*Ana Torres[\s\S]*—[\s\S]*Programada/);
  assert.equal(host.querySelector(".agenda-day-grid"), null);
  await click(button("Registrar llegada", row));
  assert.match(host.querySelector(".agenda-queue-table-row").textContent, /C-021[\s\S]*En espera/);
  await click(button("Semana", host));
  assert.equal(host.querySelector(".agenda-week-grid"), null);
  assert.match(host.querySelector(".agenda-week-queue").textContent, /1 cita por turno/);
  await click(button("Mes", host));
  assert.match(host.querySelector(".agenda-month-queue-count").textContent, /1 por turno/);
});

test("Agenda Día muestra citas por hora y por turno de la misma fecha en secciones distintas", async () => {
  items = [
    { ...fixture, id: 8, schedule_mode: "timed" },
    { ...fixture, id: 9, patient_name: "Paciente por turno", schedule_mode: "queue", appointment_time: null, daily_booking_order: 1 },
  ];
  await mount();
  assert.match(host.querySelector(".agenda-day-grid").textContent, /Ana Torres/);
  assert.match(host.querySelector(".agenda-queue-table-row").textContent, /Paciente por turno/);
  assert.doesNotMatch(host.querySelector(".agenda-day-grid").textContent, /Paciente por turno/);
  assert.doesNotMatch(host.querySelector(".agenda-queue-table-row").textContent, /08:30/);
});

test("formulario queue activo oculta Hora y envía null al editar", async () => {
  items = [{ ...fixture, schedule_mode: "queue", appointment_time: null, daily_booking_order: 1 }];
  intercept = (config) => {
    if (config.url === "/appointments/queue-capabilities") return response(config, { booking_order_enabled: true });
    if (config.url === "/appointments/effective-mode") return response(config, { schedule_mode: "queue" });
  };
  await mount(); await edit();
  assert.equal([...dialog().querySelectorAll("label")].some((item) => item.textContent.startsWith("Hora")), false);
  assert.match(dialog().textContent, /Cita por turno\. El turno se asigna al registrar llegada/);
  await click(button("Guardar cita", dialog()));
  const payload = JSON.parse(calls.find((call) => call.method === "put").data);
  assert.equal(payload.appointment_time, null);
});

test("Tipo de cita se resuelve por centro, médico y fecha sin permitir elección incompatible", async () => {
  intercept = (config) => {
    if (config.url === "/appointments/effective-mode") return response(config, {
      schedule_mode: config.params.day === "2026-09-15" ? "queue" : "timed",
    });
  };
  await mount(["secretary"], { initialPatient: {
    id: 6, first_name: "Ana", last_name: "Torres", date_of_birth: "1988-01-01", selection_token: "fixture-selection-proof",
  } });
  const mode = () => dialog().querySelector(".agenda-appointment-mode");
  const timed = () => mode().querySelector('input[value="timed"]');
  const queue = () => mode().querySelector('input[value="queue"]');
  const hour = () => [...dialog().querySelectorAll("label")].find((item) => item.textContent.startsWith("Hora"));
  assert.match(mode().textContent, /Tipo de cita/);
  assert.equal(timed().checked, false);
  assert.equal(queue().checked, false);
  assert.equal(hour(), undefined);
  assert.equal(button("Guardar cita", dialog()).disabled, true);

  await change(control("Centro"), "1");
  await change(control("Médico"), "2");
  assert.equal(timed().checked, true);
  assert.equal(queue().checked, false);
  assert.equal(timed().closest("fieldset").disabled, true);
  assert.ok(hour());
  assert.match(hour().textContent, /Hora\s*\*/);
  assert.doesNotMatch(hour().textContent, /\(obligatorio\)/);
  assert.equal(button("Guardar cita", dialog()).disabled, false);

  await change(control("Fecha"), "2026-09-15");
  assert.equal(timed().checked, false);
  assert.equal(queue().checked, true);
  assert.equal(hour(), undefined);
  assert.match(dialog().textContent, /El turno se asigna al registrar llegada/);
  await change(control("Especialidad"), "3");
  await click(button("Guardar cita", dialog()));
  const created = JSON.parse(calls.find((call) => call.url === "/appointments" && call.method === "post").data);
  assert.equal(created.appointment_time, null);
});

test("configuración multimodal permite alternar sin conservar Hora y envía snapshot elegido", async () => {
  intercept = (config) => {
    if (config.url === "/appointments/effective-mode") return response(config, {
      schedule_mode: "timed", default_mode: "timed", allowed_timed: true,
      allowed_queue: true, queue_line_available: true, multimode_enabled: true,
    });
  };
  await mount(["secretary"], { initialPatient: {
    id: 6, first_name: "Ana", last_name: "Torres", date_of_birth: "1988-01-01", selection_token: "fixture-selection-proof",
  } });
  await change(control("Centro"), "1");
  await change(control("Médico"), "2");
  const mode = dialog().querySelector(".agenda-appointment-mode");
  assert.equal(mode.disabled, false);
  assert.equal(mode.querySelector('input[value="timed"]').checked, true);
  assert.ok(control("Hora"));
  await click(mode.querySelector('input[value="queue"]'));
  assert.equal(mode.querySelector('input[value="queue"]').checked, true);
  assert.equal([...dialog().querySelectorAll("label")].some(item => item.textContent.startsWith("Hora")), false);
  await change(control("Especialidad"), "3");
  await click(button("Guardar cita", dialog()));
  const payload = JSON.parse(calls.find(call => call.url === "/appointments" && call.method === "post").data);
  assert.equal(payload.schedule_mode, "queue");
  assert.equal(payload.appointment_time, null);
});

test("al volver de una fecha por turno a una por hora reaparece Hora obligatoria", async () => {
  intercept = (config) => {
    if (config.url === "/appointments/effective-mode") return response(config, {
      schedule_mode: config.params.day === "2026-09-15" ? "queue" : "timed",
    });
  };
  await mount(); await edit();
  await change(control("Fecha"), "2026-09-15");
  assert.equal(dialog().querySelector('input[value="queue"]').checked, true);
  assert.equal([...dialog().querySelectorAll("label")].some((item) => item.textContent.startsWith("Hora")), false);
  await change(control("Fecha"), "2026-09-14");
  assert.equal(dialog().querySelector('input[value="timed"]').checked, true);
  assert.ok(control("Hora"));
  assert.equal(control("Hora").required, true);
});

test("cambiar centro y médico descarta la modalidad anterior antes de resolver la nueva", async () => {
  intercept = (config) => {
    if (config.url === "/appointments/effective-mode") return response(config, {
      schedule_mode: config.params.doctor_id === 9 ? "queue" : "timed",
    });
  };
  await mount(["secretary"], { initialPatient: {
    id: 6, first_name: "Ana", last_name: "Torres", date_of_birth: "1988-01-01", selection_token: "fixture-selection-proof",
  } });
  await change(control("Centro"), "1");
  await change(control("Médico"), "2");
  assert.equal(dialog().querySelector('input[value="timed"]').checked, true);
  await change(control("Centro"), "5");
  assert.equal(dialog().querySelector('input[value="timed"]').checked, false);
  assert.equal(dialog().querySelector('input[value="queue"]').checked, false);
  assert.equal([...dialog().querySelectorAll("label")].some((item) => item.textContent.startsWith("Hora")), false);
  await change(control("Médico"), "9");
  assert.equal(dialog().querySelector('input[value="queue"]').checked, true);
  assert.match(dialog().textContent, /El turno se asigna al registrar llegada/);
});

test("Agenda y detalle identifican la cita por turno sin mostrar Hora vacía", async () => {
  items = [{ ...fixture, schedule_mode: "queue", appointment_time: null, daily_booking_order: 2 }];
  await mount();
  assert.match(host.querySelector(".agenda-queue-table-row").textContent, /Cita por turno/);
  assert.doesNotMatch(host.textContent, /Sin hora/);
  await open();
  const details = detailSurface().querySelector(".agenda-details");
  assert.match(details.textContent, /ModalidadPor turno/);
  assert.equal([...details.querySelectorAll("dt")].some((item) => item.textContent === "Hora"), false);
  await click(closeDetail());
  await click(button("Semana", host));
  assert.match(host.querySelector(".agenda-week-queue").textContent, /Cita por turno/);
  await click(button("Mes", host));
  assert.match(host.querySelector(".agenda-month-entry").textContent, /Por turno/);
  assert.doesNotMatch(host.textContent, /Sin hora/);
});

test("fila no ofrece llegada a canceladas, ausentes, llegada por hora no activada ni usuario sin permiso", async () => {
  items = [
    { ...fixture, id: 8, schedule_mode: "queue", status: "cancelled" },
    { ...fixture, id: 9, schedule_mode: "queue", status: "no_show" },
    { ...fixture, id: 10, schedule_mode: "timed", status: "scheduled", arrival_enabled: false },
  ];
  await mount();
  assert.equal(button("Registrar llegada", host), undefined);
  await act(async () => root.unmount());
  root = createRoot(host);
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount(["secretary"], { user: {
    id: 2, full_name: "Usuario", email: "u@example.test", roles: ["secretary"],
    is_active: true, permissions: [], denied_permissions: ["patients:access"],
  } });
  assert.equal(button("Registrar llegada", host), undefined);
  assert.equal(calls.some((call) => call.url === "/queue-tickets/arrivals/8"), false);
});

test("Semana y lista de Mes ofrecen la misma acción rápida sin anidar botones", async () => {
  items = [{ ...fixture, schedule_mode: "queue" }];
  await mount();
  await click(button("Semana", host));
  const week = host.querySelector(".agenda-appointment-entry--week");
  assert.ok(button("Registrar llegada", week));
  assert.equal(week.querySelector("button button"), null);
  await click(button("Mes", host));
  const day = [...host.querySelectorAll(".agenda-month-day")].find((item) =>
    item.querySelector(".agenda-month-date")?.textContent === "14" && !item.classList.contains("agenda-month-day--outside"));
  await click(day);
  const list = panel().querySelector(".agenda-appointment-entry--list");
  assert.ok(button("Registrar llegada", list));
  assert.equal(list.querySelector("button button"), null);
  await click(button("Registrar llegada", list));
  assert.match(panel().textContent, /Turno C-021[\s\S]*Estado: En espera/);
  assert.equal(queueTickets.length, 1);
});

test("Agenda Por hora registra presencia y refresca sin emitir turno en móvil", async () => {
  setDesktop(false);
  items = [{ ...fixture, schedule_mode: "timed", arrival_enabled: true, arrived_at: null }];
  intercept = (config) => {
    if (config.method === "post" && config.url === "/appointments/8/arrival") {
      items = [{ ...items[0], arrived_at: "2026-09-14T12:05:00", arrival_registered_by: 2 }];
      return response(config, items[0]);
    }
  };
  await mount();
  assert.ok(button("Registrar llegada", host));
  await click(button("Registrar llegada", host));
  assert.equal(calls.filter(call => call.method === "post" && call.url === "/appointments/8/arrival").length, 1);
  assert.match(host.textContent, /Llegó · En espera/);
  assert.equal(button("Registrar llegada", host), undefined);
  assert.equal(items[0].appointment_time, fixture.appointment_time);
  assert.equal(items[0].schedule_mode, "timed");
  assert.equal(queueTickets.length, 0);
});
