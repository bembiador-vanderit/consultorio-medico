import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";
const { dom } = createBrowser();
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
let root, calls, items, scope, intercept, attended;
function response(config, data) {
  return { data, status: 200, statusText: "OK", headers: {}, config };
}
function fail(detail) {
  throw { response: { data: { detail } } };
}
beforeEach(() => {
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
  api.defaults.adapter = async (config) => {
    calls.push(config);
    if (intercept) {
      const result = intercept(config);
      if (result !== undefined) return await result;
    }
    if (config.url === "/appointments/scope-options" && config.method === "get")
      return response(config, scope);
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
  await click(button("Editar cita", dialog() ?? host.querySelector(".agenda-month-panel")));
}
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
  test(`${label} usa PUT /appointments/8 con payload completo y actualiza Drawer/lista`, async () => {
    await mount();
    await open();
    await click(button(label, dialog()));
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
      dialog().querySelector(".atlas-badge").textContent,
      labels[status],
    );
    assert.equal(
      host.querySelector(".atlas-badge").textContent,
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
  await click(button("Cerrar", dialog()));
  await click(button("Día", host));
  assert.match(host.querySelector("#agenda-day-heading").textContent, /martes/);
  assert.equal(host.querySelectorAll(".agenda-appointment-card").length, 1);
});
test("crear cita para otra fecha refresca lista y abre el Drawer real", async () => {
  await mount(["secretary"], {
    initialPatient: {
      id: 6,
      first_name: "Ana",
      last_name: "Torres",
      date_of_birth: "1988-01-01",
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
    assert.equal(button("Reprogramar", dialog()), undefined);
    await click(button("Editar cita", dialog()));
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
    assert.equal(button(label, dialog()), undefined);
  await click(button("Editar cita", dialog()));
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
    assert.equal(button("Iniciar consulta", dialog()), undefined);
    await click(button("Cerrar", dialog()));
    await open();
    await click(button("Iniciar consulta", dialog()));
    assert.deepEqual(attended, [8]);
  });
test("Admin puro no recibe acceso clínico", async () => {
  await mount(["admin"]);
  await open();
  assert.equal(button("Iniciar consulta", dialog()), undefined);
});
test("errores de PUT y DELETE son visibles dentro del Drawer activo", async () => {
  intercept = (config) => {
    if (config.method === "put" || config.method === "delete")
      fail("Operación rechazada por Atlas");
  };
  await mount();
  await open();
  await click(button("Confirmar", dialog()));
  assert.match(
    dialog().querySelector('[role="alert"]').textContent,
    /Operación rechazada/,
  );
  assert.equal(button("Confirmar", dialog()).disabled, false);
  const originalConfirm = window.confirm;
  window.confirm = () => true;
  try {
    await click(button("Eliminar cita", dialog()));
    assert.match(
      dialog().querySelector('[role="alert"]').textContent,
      /Operación rechazada/,
    );
  } finally {
    window.confirm = originalConfirm;
  }
});
test("Eliminar reutiliza DELETE, cierra Drawer y refresca lista", async () => {
  const originalConfirm = window.confirm;
  window.confirm = () => true;
  try {
    await mount();
    await open();
    await click(button("Eliminar cita", dialog()));
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
  assert.ok(button("Agregar nota adicional", dialog()));
  assert.equal(button("Eliminar cita", dialog()), undefined);
  assert.equal(button("Editar cita", dialog()), undefined);
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
  assert.equal(host.querySelectorAll(".atlas-badge").length, 2);
  await click(button("Semana", host));
  assert.equal(host.querySelectorAll(".agenda-week-appointment-card").length, 2);
  assert.deepEqual([...host.querySelectorAll(".agenda-week-status")].map((item) => item.textContent), ["Programada", "Confirmada"]);
  await click(button("Médicos", host));
  assert.equal(host.querySelectorAll(".agenda-doctor-group").length, 2);
  assert.match(host.textContent, /Medicina Interna/);
  assert.match(host.textContent, /Cardiología/);
  assert.deepEqual(
    [...host.querySelectorAll(".atlas-badge")].map((item) => item.textContent),
    ["Programada", "Confirmada"],
  );
});
test("búsqueda de identidad tiene IDs únicos y labels propios; Agenda no crea main", async () => {
  await mount();
  await click(button("+ Nueva cita", host));
  const inputs = dialog().querySelectorAll("input");
  const ids = [...inputs].map((item) => item.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.match(inputs[0].labels[0].textContent, /Teléfono o correo exacto/);
  assert.match(inputs[1].labels[0].textContent, /Fecha de nacimiento/);
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
  await mount(["doctor"]); await open(); await click(button("Agregar nota adicional", dialog()));
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
 assert.deepEqual([...host.querySelectorAll(".agenda-week-status")].map(item=>item.textContent),["Programada","Confirmada","Completada","Cancelada","No asistió"]);
 await click(button("Médicos",host));
 assert.deepEqual([...host.querySelectorAll(".atlas-badge")].map(item=>item.textContent),["Programada","Confirmada","Completada","Cancelada","No asistió"]);
});

test("Semana usa eje horario, tarjetas delimitadas y el panel único para lista y detalle", async () => {
  items = [
    { ...fixture, appointment_time: "08:30:00", status: "scheduled" },
    { ...fixture, id: 9, patient_name: "Berta", appointment_time: "10:15:00", status: "cancelled", specialty_name: "Cardiología", reason: "Motivo muy extenso que queda contenido" },
  ];
  await mount(); await click(button("Semana", host));
  assert.equal(host.querySelector('[role="grid"][aria-label="Agenda semanal por hora"]') !== null, true);
  assert.match(host.querySelector(".agenda-week-grid").textContent, /Hora[\s\S]*08:00[\s\S]*09:00[\s\S]*10:00/);
  const card = host.querySelector(".agenda-week-appointment-card--cancelled");
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
