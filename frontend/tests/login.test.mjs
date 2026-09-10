import { after, afterEach, beforeEach, test, mock } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: "http://localhost:5184" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
// Import React DOM only after installing the browser environment.
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { AxiosError } = await import("axios");
const server = await createServer({ server: { middlewareMode: true }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: Login } = await server.ssrLoadModule("/src/pages/Login.tsx");
const { default: App } = await server.ssrLoadModule("/src/App.tsx");
const { authenticate } = await server.ssrLoadModule("/src/services/login.ts");
const { api, setAccessToken } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
let root;
let host;
let requests;
const fixture = { email: "prueba@example.test", password: "PasswordFicticio123" };
const profile = { id: 1, email: fixture.email, full_name: "Personal de prueba", is_active: true, roles: ["doctor"] };

function response(config, data, status = 200) { return { config, data, status, statusText: "", headers: {} }; }
function rejectRequest(config, status, detail = "Credenciales inválidas") {
  return new AxiosError("Error de prueba", "ERR_BAD_RESPONSE", config, undefined, response(config, { detail }, status));
}
function adapter(handler) {
  api.defaults.adapter = async (config) => { requests.push(config); return handler(config); };
}
async function mount(Component = Login, props = { onSignIn: async () => {} }) {
  await act(async () => { root.render(h(Component, props)); });
}
async function fill(name, value) {
  const input = host.querySelector(`input[name="${name}"]`);
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}
async function fillCredentials() { await fill("email", fixture.email); await fill("password", fixture.password); }
async function submit() { await act(async () => { host.querySelector("form").requestSubmit(); }); }
async function click(button) { await act(async () => button.click()); }

beforeEach(() => {
  host = document.getElementById("root");
  root = createRoot(host);
  requests = [];
  setAccessToken(null);
  adapter((config) => { throw new Error(`Unexpected request: ${config.url}`); });
});
afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter;
  setAccessToken(null);
  mock.restoreAll();
});
after(async () => { await server.close(); dom.window.close(); });

test("real Login renders foundation form, associated labels and existing email/password contract", async () => {
  await mount();
  assert.match(host.textContent, /Atlas Consultorio/);
  assert.equal(host.querySelector("h1").textContent, "Bienvenido a Atlas");
  const email = host.querySelector('[name="email"]');
  const password = host.querySelector('[name="password"]');
  assert.equal(email.type, "email");
  assert.equal(email.autocomplete, "username");
  assert.match(email.labels[0].textContent, /Correo electrónico/);
  assert.match(password.labels[0].textContent, /Contraseña/);
  assert.equal(password.type, "password");
  assert.equal(password.autocomplete, "current-password");
  assert.equal(password.minLength, 8);
  assert.equal(password.maxLength, 128);
  assert.equal(email.required && password.required, true);
  assert.equal(host.querySelector('button[type="submit"]').textContent, "Iniciar sesión");
  assert.equal(host.querySelector("nav"), null);
  assert.equal(requests.length, 0);
});

test("password visibility toggles with an accessible button without submitting or changing value", async () => {
  const signIn = mock.fn(async () => {});
  await mount(Login, { onSignIn: signIn });
  await fill("password", fixture.password);
  const button = host.querySelector('[aria-label="Mostrar contraseña"]');
  assert.equal(button.type, "button");
  assert.equal(button.getAttribute("aria-controls"), host.querySelector('[name="password"]').id);
  await click(button);
  assert.equal(host.querySelector('[name="password"]').type, "text");
  assert.equal(host.querySelector('[name="password"]').value, fixture.password);
  assert.equal(button.getAttribute("aria-label"), "Ocultar contraseña");
  await click(button);
  assert.equal(host.querySelector('[name="password"]').type, "password");
  assert.equal(signIn.mock.callCount(), 0);
});

test("native form validation rejects missing credentials before authentication", async () => {
  const signIn = mock.fn(async () => {});
  await mount(Login, { onSignIn: signIn });
  await submit();
  assert.equal(host.querySelector("form").checkValidity(), false);
  assert.equal(signIn.mock.callCount(), 0);
});

test("submit uses the existing login then me flow, disables duplicate submits and clears password on success", async () => {
  let release;
  let authenticatedUser;
  const gate = new Promise((resolve) => { release = resolve; });
  adapter(async (config) => {
    assert.equal(config.withCredentials, true);
    if (config.url === "/auth/login") {
      assert.equal(config.method, "post");
      assert.deepEqual(JSON.parse(config.data), fixture);
      await gate;
      return response(config, { access_token: "token-ficticio" });
    }
    assert.equal(config.url, "/auth/me");
    assert.equal(config.method, "get");
    assert.equal(config.headers.get("Authorization"), "Bearer token-ficticio");
    return response(config, profile);
  });
  await mount(Login, { onSignIn: async (credentials) => { authenticatedUser = await authenticate(credentials); } });
  await fillCredentials();
  await submit();
  assert.equal(host.querySelector('button[type="submit"]').disabled, true);
  assert.equal(host.querySelector('[name="email"]').readOnly, true);
  assert.equal(host.querySelector('[name="password"]').readOnly, true);
  assert.equal(host.querySelector('[aria-label="Mostrar contraseña"]').disabled, true);
  assert.match(host.textContent, /Ingresando/);
  await act(async () => { host.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true })); });
  assert.equal(requests.length, 1);
  await act(async () => { release(); await gate; });
  assert.deepEqual(requests.map((item) => item.url), ["/auth/login", "/auth/me"]);
  assert.deepEqual(authenticatedUser, profile);
  assert.equal(host.querySelector('[name="password"]').value, "");
  assert.equal(host.querySelector('button[type="submit"]').disabled, false);
  assert.equal(window.localStorage.length, 0);
  assert.equal(window.sessionStorage.length, 0);
  assert.doesNotMatch(host.textContent, /token-ficticio|PasswordFicticio123/);
});

for (const scenario of ["invalid credentials", "inactive account", "backend rejection", "network failure", "server failure"]) {
  test(`Login handles ${scenario} safely and remains usable`, async () => {
    const logs = mock.method(console, "error", () => {});
    adapter((config) => {
      if (scenario === "network failure") throw new AxiosError("Network Error", "ERR_NETWORK", config);
      throw rejectRequest(config, scenario === "server failure" ? 500 : scenario === "backend rejection" ? 403 : 401, "internal stack trace must not be shown");
    });
    await mount(Login, { onSignIn: async (credentials) => { await authenticate(credentials); } });
    await fillCredentials();
    await submit();
    const alert = host.querySelector('[role="alert"]');
    assert.ok(alert);
    assert.match(alert.textContent, scenario === "invalid credentials" || scenario === "inactive account" ? /Correo o contraseña incorrectos/ : /No fue posible iniciar sesión/);
    assert.doesNotMatch(alert.textContent, /internal stack trace/);
    assert.equal(host.querySelector('button[type="submit"]').disabled, false);
    assert.equal(api.defaults.headers.common.Authorization, undefined);
    assert.equal(logs.mock.callCount(), 0);
  });
}

test("failed profile request clears the newly issued access token and does not authenticate the UI", async () => {
  let authenticated = false;
  adapter((config) => {
    if (config.url === "/auth/login") return response(config, { access_token: "token-ficticio" });
    throw rejectRequest(config, 401);
  });
  await mount(Login, { onSignIn: async (credentials) => { await authenticate(credentials); authenticated = true; } });
  await fillCredentials();
  await submit();
  assert.equal(authenticated, false);
  assert.equal(api.defaults.headers.common.Authorization, undefined);
  assert.ok(host.querySelector('[role="alert"]'));
});

function appAdapter(restored) {
  adapter((config) => {
    if (config.url === "/auth/refresh") {
      if (!restored) throw rejectRequest(config, 401);
      return response(config, { access_token: "token-restaurado-ficticio" });
    }
    if (config.url === "/auth/login") { assert.deepEqual(JSON.parse(config.data), fixture); return response(config, { access_token: "token-ficticio" }); }
    if (config.url === "/auth/me") return response(config, profile);
    if (config.url === "/auth/logout") return response(config, undefined, 204);
    if (config.url === "/patients/count") return response(config, { count: 0 });
    if (config.url === "/follow-ups/notifications/sync") return response(config, {});
    if (config.url === "/follow-ups/notifications") return response(config, []);
    throw new Error(`Unexpected endpoint: ${config.url}`);
  });
}

test("App mounts operational Login after rejected restoration, then opens the unchanged authenticated workspace", async () => {
  appAdapter(false);
  await mount(App, {});
  assert.ok(host.querySelector(".atlas-login"));
  await fillCredentials();
  await submit();
  assert.equal(host.querySelector(".atlas-login"), null);
  assert.match(host.textContent, /Bienvenido, Personal de prueba/);
  assert.match(host.textContent, /Sistema de gestión/);
  assert.equal(host.querySelector(".atlas-shell"), null);
});

test("App restores existing session and preserves logout returning to an empty Login", async () => {
  appAdapter(true);
  await mount(App, {});
  assert.equal(host.querySelector(".atlas-login"), null);
  assert.match(host.textContent, /Bienvenido, Personal de prueba/);
  assert.ok(!requests.some((request) => request.url === "/auth/login"));
  const signOut = [...host.querySelectorAll("button")].find((button) => button.textContent === "Cerrar sesión");
  await click(signOut);
  assert.ok(requests.some((request) => request.url === "/auth/logout" && request.method === "post"));
  assert.ok(host.querySelector(".atlas-login"));
  assert.equal(host.querySelector('[name="password"]').value, "");
  assert.equal(api.defaults.headers.common.Authorization, undefined);
});
