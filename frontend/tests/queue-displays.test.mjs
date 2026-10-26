import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { default: QueueDisplayPage } = await server.ssrLoadModule("/src/pages/QueueDisplayPage.tsx");
const { QueueDisplaySettings } = await server.ssrLoadModule("/src/components/agenda/QueueDisplaySettings.tsx");
const { QueueDisplayVoiceSettings } = await server.ssrLoadModule("/src/components/agenda/QueueDisplayVoiceSettings.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const originalFetch = globalThis.fetch;
const originalSetInterval = window.setInterval;
const originalClearInterval = window.clearInterval;
const originalConfirm = window.confirm;
const originalUtterance = globalThis.SpeechSynthesisUtterance;
let root;

const call = (code, destination, extra = {}) => ({ ticket_code: code, destination, called_at: "2030-10-15T11:30:00", call_revision: 1, queue_line_name: null, provider_name: null, ...extra });
const audio = { audio_enabled: false, audio_volume: 1, audio_language: "es-DO", audio_rate: 1, audio_pitch: 1, repeat_count: 1, repeat_delay_ms: 1000, announce_service_name: false, announce_provider_name: false };
const publicState = (current_calls, recent_calls = []) => ({ display_name: "Sala Principal", center_name: "Centro Uno", current_calls, recent_calls, updated_at: "2030-10-15T11:31:00", audio });
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });

beforeEach(() => { root = createRoot(document.getElementById("root")); });
afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter;
  globalThis.fetch = originalFetch;
  window.setInterval = originalSetInterval;
  window.clearInterval = originalClearInterval;
  window.confirm = originalConfirm;
  globalThis.SpeechSynthesisUtterance = originalUtterance;
  delete window.speechSynthesis;
  document.getElementById("root").innerHTML = "";
});
after(async () => { await server.close(); dom.window.close(); });

test("TV pública muestra tres líneas y recientes sin login ni datos personales", async () => {
  let polled;
  window.setInterval = (fn, delay) => { assert.equal(delay, 3000); polled = fn; return 7; };
  window.clearInterval = () => {};
  let state = publicState([call("C-021", "Consultorio 3"), call("T-014", "Consultorio 2"), call("S-008", "Consultorio 5")], [call("C-020", "Consultorio 3")]);
  const requests = [];
  globalThis.fetch = async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => state }; };
  await act(async () => root.render(h(QueueDisplayPage, { token: "test-token" })));
  assert.match(document.body.textContent, /C-021/);
  assert.match(document.body.textContent, /T-014/);
  assert.match(document.body.textContent, /S-008/);
  assert.match(document.body.textContent, /Llamadas recientes/);
  assert.match(document.querySelector("main").className, /min-h-screen/);
  assert.ok(document.querySelector("strong.md\\:text-8xl"));
  assert.doesNotMatch(document.body.textContent, /Paciente Sintético|809-|diagnóstico|ARS/);
  assert.equal(requests[0].options.credentials, "omit");
  assert.equal(requests[0].options.cache, "no-store");
  state = publicState([call("T-015", "Consultorio 2")]);
  await act(async () => polled());
  assert.match(document.body.textContent, /T-015/);
  assert.doesNotMatch(document.body.textContent, /C-021/);
});

test("token inválido o display inactivo muestra mensaje neutro", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 404 });
  await act(async () => root.render(h(QueueDisplayPage, { token: "invalid" })));
  assert.match(document.body.textContent, /Pantalla no disponible/);
  assert.doesNotMatch(document.body.textContent, /404|Traceback|SQL/);
});

test("pantalla solicita activación y anuncia únicamente una nueva llamada", async () => {
  const spoken = [];
  globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  window.speechSynthesis = { speak: (utterance) => spoken.push(utterance), cancel: () => {},
    getVoices: () => [{ lang: "es-DO", localService: true }] };
  let polled;
  window.setInterval = (fn, delay) => { if (delay === 3000) polled = fn; return 7; };
  window.clearInterval = () => {};
  let current = { ...publicState([]), audio: { ...audio, audio_enabled: true } };
  globalThis.fetch = async () => ({ ok: true, json: async () => current });
  await act(async () => root.render(h(QueueDisplayPage, { token: "synthetic-audio-token" })));
  assert.match(document.body.textContent, /Activar audio/);
  const activate = [...document.querySelectorAll("button")].find((item) => item.textContent === "Activar audio");
  await act(async () => activate.click());
  assert.equal(spoken.length, 0);
  current = { ...current, current_calls: [call("C-021", "Consultorio 3")] };
  await act(async () => polled());
  assert.equal(spoken.length, 1);
  assert.match(spoken[0].text, /Turno C cero veintiuno/);
  assert.doesNotMatch(spoken[0].text, /paciente|teléfono|diagnóstico/i);
  spoken[0].onend();
  await act(async () => polled());
  assert.equal(spoken.length, 1);
});

test("administración configura líneas, destino, modo visible y rota token", async () => {
  const requests = [];
  let displays = [];
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/queue-displays") return response(config, displays);
    if (config.method === "get" && config.url === "/queue-lines") return response(config, [
      { id: 1, center_id: 1, name: "Cardiología", prefix: "C", is_active: true },
      { id: 2, center_id: 1, name: "Traumatología", prefix: "T", is_active: true },
    ]);
    if (config.method === "post" && config.url === "/queue-displays") {
      const data = JSON.parse(config.data);
      displays = [{ ...data, id: 1, center_name: "Centro Uno", lines: data.lines.map((line) => ({ ...line, line_name: "Cardiología" })) }];
      return response(config, { ...displays[0], access_token: "safe-example-token" });
    }
    if (config.method === "post" && config.url === "/queue-displays/1/rotate-token") return response(config, { ...displays[0], access_token: "rotated-token" });
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
  await act(async () => root.render(h(QueueDisplaySettings, { centers: [{ id: 1, name: "Centro Uno" }] })));
  const input = [...document.querySelectorAll("input")].find((item) => item.maxLength === 120);
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, "Sala Principal"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  const lineCheck = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("C · Cardiología"))?.querySelector("input");
  await act(async () => { lineCheck.click(); });
  const destination = document.querySelector('input[placeholder="Consultorio 3"]');
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(destination, "Consultorio 3"); destination.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  const audioCheck = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Audio habilitado"))?.querySelector("input");
  await act(async () => audioCheck.click());
  const volume = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Volumen"))?.querySelector("input");
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(volume, "0.6"); volume.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  const repeats = [...document.querySelectorAll("label")].find((item) => item.textContent.includes("Repeticiones por llamada"))?.querySelector("input");
  assert.equal(repeats.max, "10");
  await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(repeats, "4"); repeats.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
  const create = [...document.querySelectorAll("button")].find((item) => item.textContent === "Crear pantalla");
  await act(async () => create.click());
  const created = requests.find((item) => item.method === "post" && item.url === "/queue-displays");
  assert.equal(JSON.parse(created.data).lines[0].destination, "Consultorio 3");
  assert.equal(JSON.parse(created.data).audio_enabled, true);
  assert.equal(JSON.parse(created.data).audio_volume, 0.6);
  assert.equal(JSON.parse(created.data).repeat_count, 4);
  assert.match(document.body.textContent, /no se volverá a mostrar/);
  assert.match(document.body.textContent, /safe-example-token/);
  window.confirm = () => true;
  const rotate = [...document.querySelectorAll("button")].find((item) => item.textContent === "Regenerar clave");
  await act(async () => rotate.click());
  assert.match(document.body.textContent, /rotated-token/);
  assert.doesNotMatch(document.body.textContent, /safe-example-token/);
});

test("administración prueba y guarda solo una voz española local por pantalla", async () => {
  const spoken = [];
  const requests = [];
  globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  window.speechSynthesis = {
    getVoices: () => [
      { voiceURI: "local-es-mx", name: "Voz MX", lang: "es-MX", localService: true },
      { voiceURI: "remote-es-mx", name: "Voz remota", lang: "es-MX", localService: false },
    ],
    addEventListener() {}, removeEventListener() {}, cancel() {}, speak: (utterance) => spoken.push(utterance),
  };
  const display = { id: 1, center_id: 1, center_name: "Centro Uno", name: "Pantalla QA",
    audio_voice_uri: null, audio_enabled: true, lines: [] };
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === "get" && config.url === "/queue-displays") return response(config, [display]);
    if (config.method === "put" && config.url === "/queue-displays/1/voice") return response(config, { ...display, audio_voice_uri: JSON.parse(config.data).audio_voice_uri });
    throw new Error(`Unexpected ${config.method} ${config.url}`);
  };
  await act(async () => root.render(h(QueueDisplayVoiceSettings)));
  assert.match(document.body.textContent, /Voz MX/);
  assert.doesNotMatch(document.body.textContent, /Voz remota/);
  const selector = [...document.querySelectorAll("select")].find((item) => item.parentElement.textContent.includes("Voz local"));
  await act(async () => { selector.value = "local-es-mx"; selector.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  await act(async () => [...document.querySelectorAll("button")].find((item) => item.textContent === "Probar voz").click());
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].voice.voiceURI, "local-es-mx");
  assert.equal(spoken[0].lang, "es-MX");
  await act(async () => [...document.querySelectorAll("button")].find((item) => item.textContent === "Guardar voz").click());
  assert.equal(JSON.parse(requests.find((item) => item.method === "put").data).audio_voice_uri, "local-es-mx");
  assert.match(document.body.textContent, /Voz guardada/);
});
