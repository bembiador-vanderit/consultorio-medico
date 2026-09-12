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
let root, requests, data;
const baseLabels = ["Dashboard", "Agenda", "Reportes de citas", "Pacientes"];
const headings = { Dashboard: "Bienvenido, Personal de prueba", Agenda: "Agenda de citas", "Reportes de citas": "Reportes de citas", Pacientes: "Pacientes", Seguimientos: "Seguimiento de pacientes", "Mi disponibilidad": "Mi disponibilidad", "Cobertura clínica": "Cobertura clínica", "Usuarios y roles": "Usuarios y roles", "Localidades y centros": "Localidades y centros" };
const listEndpoints = ["/patients", "/appointments", "/centers/mine", "/follow-ups", "/doctor-availability", "/clinical-coverages", "/users", "/centers", "/localities/all", "/clinical-catalog/specialties", "/appointments/doctors"];

beforeEach(() => {
  root = createRoot(host);
  requests = [];
  data = new Map(listEndpoints.map((path) => [path, []]));
  data.set("/patients/count", { count: 0 });
  data.set("/appointments/scope-options", { doctors: [], centers: [] });
  data.set("/follow-ups/notifications", []);
  data.set("/follow-ups/notifications/sync", {});
  data.set("/auth/refresh", { access_token: "fixture-only" });
  data.set("/auth/logout", null);
  setAccessToken(null);
  setDesktop(true);
  api.defaults.adapter = async (config) => {
    requests.push({ url: config.url, method: config.method });
    if (!data.has(config.url)) throw new Error(`Unexpected endpoint ${config.url}`);
    return { data: data.get(config.url), status: 200, statusText: "OK", headers: {}, config };
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; setAccessToken(null); });
after(async () => { await server.close(); dom.window.close(); });

async function mount(roles) {
  data.set("/auth/me", { id: 1, full_name: "Personal de prueba", email: "personal@example.com", roles, is_active: true });
  await act(async () => root.render(h(App)));
}
async function click(button) { assert.ok(button); await act(async () => button.click()); }
function button(text, scope = host) { return [...scope.querySelectorAll("button")].find((item) => item.textContent.trim() === text); }
function navigation() { return host.querySelector(".atlas-sidebar nav"); }

for (const roles of [[], ["doctor"], ["secretary"], ["admin"], ["doctor", "admin"], ["doctor", "secretary"], ["secretary", "admin"], ["doctor", "secretary", "admin"], ["unexpected"]]) {
  test(`operational navigation and reachable bodies preserve roles ${roles.join("+") || "none"}`, async () => {
    await mount(roles);
    assert.ok(host.querySelector(".atlas-shell"));
    assert.equal(host.querySelector(".atlas-login"), null);
    const expected = [...baseLabels];
    if (roles.includes("doctor")) expected.push("Seguimientos", "Mi disponibilidad");
    if (roles.includes("doctor") || roles.includes("secretary")) expected.push("Cobertura clínica");
    if (roles.includes("admin")) expected.push("Usuarios y roles", "Localidades y centros");
    assert.deepEqual([...navigation().querySelectorAll("button")].map((item) => item.textContent), expected);
    for (const label of expected) {
      await click(button(label, navigation()));
      assert.equal(navigation().querySelectorAll('[aria-current="page"]').length, 1);
      assert.equal(navigation().querySelector('[aria-current="page"]').textContent, label);
      assert.equal(host.querySelector("main h2").textContent, headings[label]);
    }
    assert.ok(host.querySelector(".atlas-topbar .atlas-user").textContent.includes("Personal de prueba"));
    if (!roles.includes("doctor")) assert.ok(!button("Seguimientos", navigation()));
  });
}

test("existing page back callback updates the single active view", async () => {
  await mount(["doctor"]);
  await click(button("Pacientes", navigation()));
  await click(button("← Volver al dashboard", host.querySelector("main")));
  assert.equal(navigation().querySelector('[aria-current="page"]').textContent, "Dashboard");
  assert.match(host.querySelector("main").textContent, /Bienvenido, Personal de prueba/);
});

test("patient scheduling opens Agenda with that patient; navigation to Agenda clears the selection", async () => {
  data.set("/patients", [{ id: 9, first_name: "Paciente", last_name: "Ficticio", date_of_birth: "1980-01-01" }]);
  await mount(["doctor"]);
  await click(button("Pacientes", navigation()));
  await click(button("Agendar cita", host.querySelector("main")));
  assert.equal(navigation().querySelector('[aria-current="page"]').textContent, "Agenda");
  assert.match(host.querySelector("main").textContent, /Paciente Ficticio/);
  await click(button("Dashboard", navigation()));
  await click(button("Agenda", navigation()));
  assert.doesNotMatch(host.querySelector("main").textContent, /Paciente Ficticio/);
});

test("real notification bell keeps unread data, read endpoint and Dashboard callback", async () => {
  data.set("/follow-ups/notifications", [{ id: 7, title: "Aviso ficticio", message: "Mensaje de prueba", notification_type: "validation", is_read: false }]);
  data.set("/follow-ups/notifications/7/read", {});
  await mount(["doctor"]);
  await click(button("Pacientes", navigation()));
  await click(host.querySelector('[aria-label="Notificaciones, 1 sin leer"]'));
  assert.match(host.querySelector(".atlas-notification-panel").textContent, /Aviso ficticio/);
  data.set("/follow-ups/notifications", []);
  await click(button("Marcar como leída", host.querySelector(".atlas-notification-panel")));
  assert.ok(requests.some((request) => request.url === "/follow-ups/notifications/7/read" && request.method === "post"));
  assert.ok(host.querySelector('[aria-label="Notificaciones"]'));
  assert.match(host.querySelector(".atlas-notification-panel").textContent, /No tienes notificaciones pendientes/);
  await click(button("Ver en Dashboard"));
  assert.equal(navigation().querySelector('[aria-current="page"]').textContent, "Dashboard");
});

test("mobile navigation closes after destination, cancel and desktop transition", async () => {
  setDesktop(false);
  await mount(["secretary"]);
  const trigger = host.querySelector('[aria-label="Abrir navegación"]');
  const drawer = document.querySelector("dialog");
  trigger.focus();
  await click(trigger);
  assert.equal(drawer.open, true);
  assert.equal(trigger.getAttribute("aria-expanded"), "true");
  assert.equal(document.activeElement, drawer.querySelector("h2"));
  await click(button("Agenda", drawer));
  assert.equal(drawer.open, false);
  assert.equal(document.activeElement, trigger);
  assert.equal(navigation().querySelector('[aria-current="page"]').textContent, "Agenda");
  await click(trigger);
  await act(async () => drawer.dispatchEvent(new dom.window.Event("cancel", { bubbles: false, cancelable: true })));
  assert.equal(drawer.open, false);
  await click(trigger);
  await act(async () => setDesktop(true));
  assert.equal(drawer.open, false);
  assert.equal(document.body.style.overflow, "");
});

test("shell logout uses the existing API and returns approved Login without shell", async () => {
  await mount(["admin"]);
  await click(button("Cerrar sesión"));
  assert.ok(requests.some((request) => request.url === "/auth/logout" && request.method === "post"));
  assert.equal(api.defaults.headers.common.Authorization, undefined);
  assert.equal(host.querySelector(".atlas-shell"), null);
  assert.equal(host.querySelector("h1").textContent, "Bienvenido a Atlas");
});
