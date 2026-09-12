import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom, setDesktop } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: App } = await server.ssrLoadModule("/src/App.tsx");
const { api, setAccessToken } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
let root, data, failAppointments, holdAppointments;

beforeEach(() => {
  root = createRoot(host);
  setDesktop(true);
  failAppointments = false;
  holdAppointments = false;
  data = new Map([
    ["/auth/refresh", { access_token: "fixture-only" }], ["/auth/logout", null], ["/patients/count", { count: 12 }],
    ["/appointments", [{ id: 8, patient_name: "Ana Pérez", doctor_name: "Dra. Prueba", center_name: "Centro Norte", appointment_time: "09:30:00", status: "confirmed" }]],
    ["/follow-ups/notifications/sync", {}], ["/follow-ups/notifications", [{ id: 3, title: "Cita próxima", message: "Ana Pérez", is_read: false }]],
    ["/follow-ups", [{ id: 1, status: "pending" }, { id: 2, status: "completed" }]],
    ["/users", [{ id: 1, is_active: true }, { id: 2, is_active: false }]], ["/centers", [{ id: 1, is_active: true }, { id: 2, is_active: true }]],
    ["/patients", []], ["/centers/mine", []], ["/appointments/scope-options", { doctors: [], centers: [] }], ["/doctor-availability", []], ["/clinical-coverages", []], ["/clinical-catalog/specialties", []], ["/localities/all", []],
  ]);
  setAccessToken(null);
  api.defaults.adapter = async (config) => {
    if (config.url === "/appointments" && holdAppointments) return new Promise(() => {});
    if (config.url === "/appointments" && failAppointments) throw new Error("Agenda no disponible");
    if (!data.has(config.url)) throw new Error(`Unexpected endpoint ${config.url}`);
    return { data: data.get(config.url), status: 200, statusText: "OK", headers: {}, config };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; setAccessToken(null); });
after(async () => { await server.close(); dom.window.close(); });

async function mount(roles, specialty_names = []) {
  data.set("/auth/me", { id: 1, full_name: "Dr. Osiris Valdés", email: "osiris@example.com", roles, specialty_names, is_active: true });
  await act(async () => { root.render(h(App)); await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
}

async function clickAction(id, scope = host) {
  const target = scope.querySelector(`[data-dashboard-action="${id}"]`);
  assert.ok(target, `No se encontró la acción ${id}`);
  await act(async () => target.click());
}

function main() { return host.querySelector("main"); }
function actionLabels() { return [...main().querySelectorAll("[data-dashboard-action]")].map((item) => item.getAttribute("aria-label")); }

test("médico ve jornada, especialidades múltiples y acciones clínicas reales", async () => {
  await mount(["doctor"], ["Cardiología", "Medicina Interna"]);
  assert.match(main().textContent, /Jornada clínica/);
  assert.match(main().textContent, /Cardiología · Medicina Interna/);
  assert.match(main().textContent, /Seguimientos pendientes/);
  assert.deepEqual(actionLabels(), ["Ver agenda", "Pacientes", "Reportes de citas", "Ver seguimientos", "Mi disponibilidad", "Cobertura clínica"]);
  assert.doesNotMatch(main().textContent, /Usuarios activos/);
});

test("secretaría recibe operación permitida sin contenido clínico protegido", async () => {
  await mount(["secretary"]);
  assert.match(main().textContent, /Operación de agenda/);
  assert.match(main().textContent, /Agenda de hoy/);
  assert.ok(actionLabels().includes("Cobertura clínica"));
  assert.ok(!actionLabels().includes("Ver seguimientos"));
  assert.doesNotMatch(main().textContent, /Especialidades asignadas|Seguimientos pendientes|Historia clínica|Diagnóstico|Receta/);
});

test("administrador ve resumen administrativo sin obtener bloques clínicos", async () => {
  await mount(["admin"]);
  assert.match(main().textContent, /Administración operativa/);
  assert.match(main().textContent, /Usuarios activos/);
  assert.match(main().textContent, /Centros activos/);
  assert.ok(actionLabels().includes("Usuarios y roles"));
  assert.ok(actionLabels().includes("Centros de atención"));
  assert.doesNotMatch(main().textContent, /Jornada clínica|Especialidades asignadas|Seguimientos pendientes/);
});

test("médico y administrador reciben la unión de bloques y acciones sin duplicados", async () => {
  await mount(["doctor", "admin"], ["Cardiología", "Medicina Interna"]);
  assert.match(main().textContent, /Jornada clínica/);
  assert.match(main().textContent, /Administración operativa/);
  const labels = actionLabels();
  assert.equal(labels.filter((label) => label === "Ver agenda").length, 1);
  assert.equal(labels.filter((label) => label === "Usuarios y roles").length, 1);
  assert.equal(labels.filter((label) => label === "Ver seguimientos").length, 1);
});

test("dashboard expresa carga, vacío y error de agenda sin colapsar sus acciones", async () => {
  holdAppointments = true;
  await mount(["secretary"]);
  assert.match(main().textContent, /Cargando citas de hoy…/);
  await act(async () => root.unmount());

  root = createRoot(host);
  holdAppointments = false;
  data.set("/appointments", []);
  await mount(["secretary"]);
  assert.match(main().textContent, /No hay citas para hoy dentro de tu alcance/);
  await act(async () => root.unmount());

  root = createRoot(host);
  failAppointments = true;
  await mount(["secretary"]);
  assert.match(main().textContent, /No fue posible cargar las citas de hoy/);
  assert.ok(actionLabels().includes("Ver agenda"));
});

test("acción rápida usa la navegación real dentro del App Shell", async () => {
  await mount(["doctor"]);
  await clickAction("agenda", main());
  assert.equal(host.querySelector('.atlas-sidebar [aria-current="page"]').textContent, "Agenda");
  assert.equal(main().querySelector("h2").textContent, "Agenda de citas");
  assert.ok(host.querySelector(".atlas-shell"));
});
