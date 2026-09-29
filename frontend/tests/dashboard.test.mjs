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
let root, data, failAppointments, holdAppointments, requests;

beforeEach(() => {
  root = createRoot(host);
  requests = [];
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
    requests.push({url: config.url, params: config.params});
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
  assert.deepEqual([...main().querySelectorAll(".dashboard-specialties .atlas-badge")].map((item) => item.textContent), ["Cardiología", "Medicina Interna"]);
  assert.match(main().textContent, /Seguimientos pendientes/);
  assert.deepEqual(actionLabels(), ["Nueva cita", "Pacientes", "Ver agenda", "Reportes de citas", "Ver seguimientos", "Mi disponibilidad", "Cobertura clínica"]);
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
  assert.equal(main().querySelector("h1").textContent, "Agenda");
  assert.ok(host.querySelector(".atlas-shell"));
});

test("Nueva cita abre el formulario operativo y cerrar conserva Agenda Día", async () => {
  await mount(["secretary"]);
  await clickAction("new-appointment", main());
  const modal = [...document.querySelectorAll("dialog")].find((item) => item.open);
  assert.ok(modal);
  assert.match(modal.textContent, /Nueva cita/);
  assert.ok(modal.querySelector(".agenda-form"));
  const before = requests.length;
  await act(async () => modal.dispatchEvent(new dom.window.Event("cancel", { cancelable: true })));
  assert.equal(modal.open, false);
  assert.equal(main().querySelector("h1").textContent, "Agenda");
  assert.equal(main().querySelector('[aria-pressed="true"]').textContent, "Día");
  assert.equal(requests.length, before);
});

test("admin prioriza destinos administrativos y no añade flujos ficticios", async () => {
  await mount(["admin"]);
  assert.deepEqual(actionLabels().slice(0, 2), ["Usuarios y roles", "Centros de atención"]);
  assert.ok(!actionLabels().includes("Iniciar consulta"));
  assert.doesNotMatch(main().textContent, /Laboratorio|Nueva receta|Ingresos|WhatsApp|En espera/);
  assert.equal(requests.filter((item) => item.url === "/follow-ups").length, 0);
});

test("secretaría no solicita fuentes clínicas y conserva todas las métricas reales", async () => {
  await mount(["secretary"]);
  assert.equal(requests.filter((item) => item.url === "/follow-ups").length, 0);
  assert.equal(requests.filter((item) => item.url === "/users" || item.url === "/centers").length, 0);
  const metrics = [...main().querySelectorAll(".dashboard-metric")];
  assert.deepEqual(metrics.map((item) => item.querySelector(".dashboard-metric-value").textContent), ["1", "12", "1"]);
  assert.ok(metrics.every((item) => item.querySelector("svg")));
});

test("médico sin especialidades y sin notificaciones usa vacíos pequeños y honestos", async () => {
  data.set("/follow-ups/notifications", []);
  await mount(["doctor"]);
  assert.match(main().querySelector(".dashboard-specialties").textContent, /pendientes de configurar/);
  assert.match(main().querySelector(".dashboard-notifications").textContent, /No hay notificaciones pendientes/);
  assert.equal(main().querySelectorAll(".dashboard-specialties .atlas-card").length, 0);
});

test("dashboard móvil marca Inicio y permite revelar accesos sin nuevas consultas", async () => {
  await mount(["doctor"]);
  await act(async () => setDesktop(false));
  const nav = host.querySelector('[aria-label="Navegación móvil"]');
  assert.deepEqual([...nav.querySelectorAll("button")].map((item) => item.textContent), ["Inicio", "Agenda", "Pacientes", "•••Más"]);
  assert.equal(nav.querySelector('[aria-current="page"]').textContent, "Inicio");
  const toggle = main().querySelector(".dashboard-more-actions");
  const before = requests.length;
  await act(async () => toggle.click());
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  assert.equal(main().querySelector(".dashboard-actions-grid").id, toggle.getAttribute("aria-controls"));
  await act(async () => toggle.click());
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(requests.length, before);
});

test("más accesos y controles del shell no repiten fuentes ni consultan cada cita", async () => {
  await mount(["doctor", "admin"]);
  for (const path of ["/patients/count", "/appointments", "/follow-ups", "/users", "/centers"]) assert.equal(requests.filter((item) => item.url === path).length, 1, path);
  // Bell and Dashboard retain their existing independent notification loads.
  assert.equal(requests.filter((item) => item.url === "/follow-ups/notifications").length, 2);
  assert.equal(requests.filter((item) => item.url.startsWith("/clinical-history") || item.url.startsWith("/insurance/")).length, 0);
  const before = requests.length;
  await act(async () => host.querySelector('.atlas-account-menu summary').click());
  await act(async () => main().querySelector('.dashboard-more-actions').click());
  assert.equal(requests.length, before);
});

test("agenda resumen ordena horas reales, limita cinco y conserva estado textual", async () => {
  data.set("/appointments", Array.from({length: 6}, (_, index) => ({id:index+1,patient_name:`Paciente ficticio ${index}`,doctor_name:"Médico ficticio",appointment_time:`${String(14-index).padStart(2,"0")}:30:00`,status:"scheduled"})));
  await mount(["doctor"]);
  const rows = main().querySelectorAll(".dashboard-appointments li");
  assert.equal(rows.length, 5);
  assert.equal(rows[0].querySelector("time").textContent, "09:30");
  assert.ok([...rows].every((item) => item.textContent.includes("Programada")));
  assert.match(main().textContent, /Mostrando 5 de 6 citas/);
});

test("roles médico y secretaría comparten acciones sin duplicación", async () => {
  await mount(["doctor", "secretary"]);
  const ids = [...main().querySelectorAll("[data-dashboard-action]")].map((item) => item.dataset.dashboardAction);
  assert.equal(ids.length, new Set(ids).size);
  assert.match(main().textContent, /Jornada clínica/);
  assert.match(main().textContent, /Operación de agenda/);
});


test("Dashboard shares the five appointment identities with Agenda", async () => {
  const statuses = ["scheduled", "confirmed", "completed", "cancelled", "no_show"];
  data.set("/appointments", statuses.map((status,index)=>({id:index+1,patient_name:"Paciente ficticio",appointment_time:`${8+index}:00:00`,status})));
  await mount(["doctor"]);
  const badges = [...main().querySelectorAll(".dashboard-appointments .atlas-badge")];
  assert.equal(badges.length, 5);
  for (const status of statuses) assert.ok(badges.some(node=>node.classList.contains(`appointment-status--${status}`)), status);
});
