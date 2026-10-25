import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { QueueDisplayAudio, spokenTicketCode, announcementPhrase } = await server.ssrLoadModule("/src/services/queueDisplayAudio.ts");
const originalInterval = window.setInterval;
const originalClearInterval = window.clearInterval;
const originalTimeout = window.setTimeout;
const originalClearTimeout = window.clearTimeout;
const originalUtterance = globalThis.SpeechSynthesisUtterance;
const originalAudioContext = window.AudioContext;
let spoken;
let intervals;
let status;
let controllers;

const audio = { audio_enabled: true, audio_volume: 0.7, audio_language: "es-DO", audio_rate: 1.2,
  audio_pitch: 0.8, repeat_count: 1, repeat_delay_ms: 1000, announce_service_name: false, announce_provider_name: false };
const call = (code, revision = 1, date = "2030-10-15T11:30:00") => ({
  ticket_code: code, destination: "Consultorio 3", called_at: date, call_revision: revision,
  queue_line_name: "Cardiología", provider_name: "Dr. Sintético",
});
const state = (calls, changes = {}) => ({
  display_name: "Sintética", center_name: "Centro", current_calls: calls, recent_calls: [],
  updated_at: "2030-10-15T11:31:00", audio: { ...audio, ...changes },
});
function controller(token = Math.random().toString(36)) {
  const item = new QueueDisplayAudio(token, (value) => status.push(value));
  controllers.push(item);
  return item;
}

beforeEach(() => {
  spoken = []; intervals = []; status = []; controllers = [];
  window.localStorage.clear();
  globalThis.SpeechSynthesisUtterance = class {
    constructor(text) { this.text = text; }
  };
  window.speechSynthesis = { speak: (utterance) => spoken.push(utterance), cancel: () => {},
    getVoices: () => [{ lang: "es-DO", localService: true }] };
  window.setInterval = (fn, delay) => { intervals.push({ fn, delay }); return intervals.length; };
  window.clearInterval = () => {};
});
afterEach(() => {
  controllers.forEach((item) => item.dispose());
  window.setInterval = originalInterval;
  window.clearInterval = originalClearInterval;
  window.setTimeout = originalTimeout;
  window.clearTimeout = originalClearTimeout;
  globalThis.SpeechSynthesisUtterance = originalUtterance;
  window.AudioContext = originalAudioContext;
  delete window.speechSynthesis;
  window.localStorage.clear();
});
after(async () => { await server.close(); dom.window.close(); });

test("formato de voz habla C, T, CAR y PED sin datos personales", () => {
  assert.equal(spokenTicketCode("C-021"), "C cero veintiuno");
  assert.equal(spokenTicketCode("T-014"), "T cero catorce");
  assert.equal(spokenTicketCode("CAR-008"), "C A R cero ocho");
  assert.equal(spokenTicketCode("PED-012"), "P E D cero doce");
  assert.equal(announcementPhrase(call("C-021"), audio), "Turno C cero veintiuno, favor pasar al Consultorio tres.");
  assert.doesNotMatch(announcementPhrase(call("C-021"), audio), /Sintético|Cardiología|paciente|teléfono/i);
});

test("audio desactivado y carga inicial no hablan; llamada nueva y recall sí, polling igual no", () => {
  const item = controller("first-load");
  item.observe(state([call("C-021")], { audio_enabled: false }));
  item.activate();
  assert.equal(spoken.length, 0);
  item.observe(state([call("C-021")]));
  item.activate();
  item.observe(state([call("C-021")]));
  assert.equal(spoken.length, 0);
  item.observe(state([call("C-021", 2, "2030-10-15T11:35:00")]));
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].volume, 0.7);
  assert.equal(spoken[0].rate, 1.2);
  assert.equal(spoken[0].pitch, 0.8);
  assert.equal(spoken[0].lang, "es-DO");
  spoken[0].onend();
  item.observe(state([call("C-021", 2, "2030-10-15T11:35:00")]));
  assert.equal(spoken.length, 1);
  assert.equal(status.at(-1), "active");
});

test("dos llamadas esperan su turno y repetición respeta el retardo", () => {
  const item = controller("queue");
  item.observe(state([]));
  item.activate();
  let delayed;
  window.setTimeout = (fn, delay) => { delayed = fn; assert.equal(delay, 2500); return 11; };
  window.clearTimeout = () => {};
  item.observe(state([call("C-021"), call("T-014", 1, "2030-10-15T11:31:00")],
    { repeat_count: 2, repeat_delay_ms: 2500 }));
  assert.equal(spoken.length, 1);
  spoken[0].onend();
  assert.equal(spoken.length, 1);
  delayed();
  assert.equal(spoken.length, 2);
  spoken[1].onend();
  assert.equal(spoken.length, 3);
  assert.match(spoken[2].text, /T cero catorce/);
});

test("cuatro repeticiones por llamada también se aplican a RECALL sin repetir por polling", () => {
  const item = controller("four-repeats");
  item.observe(state([]));
  item.activate();
  let delayed;
  window.setTimeout = (fn, delay) => { assert.equal(delay, 1000); delayed = fn; return 11; };
  window.clearTimeout = () => {};
  item.observe(state([call("C-021")], { repeat_count: 4 }));
  for (let index = 0; index < 4; index += 1) {
    assert.equal(spoken.length, index + 1);
    spoken[index].onend();
    if (index < 3) delayed();
  }
  item.observe(state([call("C-021")], { repeat_count: 4 }));
  assert.equal(spoken.length, 4);
  item.observe(state([call("C-021", 2, "2030-10-15T11:35:00")], { repeat_count: 4 }));
  for (let index = 4; index < 8; index += 1) {
    assert.equal(spoken.length, index + 1);
    spoken[index].onend();
    if (index < 7) delayed();
  }
  item.observe(state([call("C-021", 2, "2030-10-15T11:35:00")], { repeat_count: 4 }));
  assert.equal(spoken.length, 8);
});

test("servicio y médico solo se pronuncian con autorización explícita", () => {
  const phrase = announcementPhrase(call("C-021"), { ...audio, announce_service_name: true, announce_provider_name: true });
  assert.match(phrase, /Cardiología/);
  assert.match(phrase, /Dr. Sintético/);
});

test("sin speechSynthesis y error TTS degradan sin romper polling", () => {
  const item = controller("unsupported");
  delete window.speechSynthesis;
  item.observe(state([]));
  assert.equal(status.at(-1), "unsupported");
  item.activate();
  assert.equal(spoken.length, 0);
  window.speechSynthesis = { speak: () => { throw new Error("blocked"); }, cancel: () => {},
    getVoices: () => [{ lang: "es-DO", localService: true }] };
  const another = controller("blocked");
  another.observe(state([]));
  another.activate();
  another.observe(state([call("C-021")]));
  assert.equal(status.at(-1), "error");
  another.observe(state([call("C-021")]));
  assert.equal(spoken.length, 0);
});

test("voz remota no se usa aunque el navegador la ofrezca", () => {
  window.speechSynthesis.getVoices = () => [{ lang: "es-DO", localService: false }];
  const item = controller("remote-voice");
  item.observe(state([]));
  item.activate();
  item.observe(state([call("C-021")]));
  assert.equal(spoken.length, 0);
  assert.equal(status.at(-1), "unsupported");
});

test("es-DO usa una voz española local alternativa si no hay voz dominicana", () => {
  window.speechSynthesis.getVoices = () => [{ lang: "es", localService: true }];
  const item = controller("spanish-fallback");
  item.observe(state([]));
  item.activate();
  item.observe(state([call("C-021")]));
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].voice.lang, "es");
});

test("selección explícita usa solo la voz local exacta y su acento", () => {
  window.speechSynthesis.getVoices = () => [
    { name: "Local MX", voiceURI: "local-mx", lang: "es-MX", localService: true },
    { name: "Remota MX", voiceURI: "remote-mx", lang: "es-MX", localService: false },
  ];
  const item = controller("chosen-local");
  item.observe(state([], { audio_voice_uri: "local-mx" }));
  item.activate();
  item.observe(state([call("C-021")], { audio_voice_uri: "local-mx" }));
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].voice.voiceURI, "local-mx");
  assert.equal(spoken[0].lang, "es-MX");
  spoken[0].onend();
  const missing = controller("missing-local");
  missing.observe(state([], { audio_voice_uri: "remote-mx" }));
  missing.activate();
  missing.observe(state([call("C-022")], { audio_voice_uri: "remote-mx" }));
  assert.equal(spoken.length, 1);
  assert.equal(status.at(-1), "unsupported");
});

test("un aviso sonoro previo termina antes de iniciar la frase y no se repite en polling", () => {
  const cues = [];
  const timers = [];
  window.AudioContext = class {
    state = "running";
    currentTime = 0;
    destination = {};
    createOscillator() {
      const cue = { frequency: { setValueAtTime() {} }, connect() {}, disconnect() {}, start() {}, stop() {} };
      cues.push(cue);
      return cue;
    }
    createGain() { return { gain: { setValueAtTime() {}, linearRampToValueAtTime() {} }, connect() {}, disconnect() {} }; }
    close() { return Promise.resolve(); }
  };
  window.setTimeout = (fn, delay) => { timers.push({ fn, delay }); return timers.length; };
  const item = controller("hdmi-preroll");
  item.observe(state([]));
  item.activate();
  item.observe(state([call("C-021")]));
  assert.equal(cues.length, 1);
  assert.equal(spoken.length, 0);
  cues[0].onended();
  assert.equal(timers[0].delay, 150);
  timers[0].fn();
  assert.equal(spoken.length, 1);
  assert.match(spoken[0].text, /^Turno C cero veintiuno/);
  spoken[0].onend();
  item.observe(state([call("C-021")]));
  assert.equal(cues.length, 1);
  assert.equal(spoken.length, 1);
});

test("silenciar se recuerda localmente, pero reactivar siempre requiere clic", () => {
  const first = controller("local-choice");
  first.observe(state([]));
  first.activate();
  first.mute();
  first.dispose();
  const second = controller("local-choice");
  second.observe(state([]));
  assert.equal(status.at(-1), "muted");
  second.observe(state([call("C-021")]));
  assert.equal(spoken.length, 0);
  second.activate();
  assert.equal(status.at(-1), "active");
});

test("dos pestañas del mismo display eligen un líder de audio", () => {
  const first = controller("same-display");
  const second = controller("same-display");
  first.observe(state([]));
  second.observe(state([]));
  first.activate();
  second.activate();
  first.observe(state([call("C-021")]));
  second.observe(state([call("C-021")]));
  assert.equal(spoken.length, 1);
  assert.equal(intervals.filter((item) => item.delay === 2000).length, 2);
  first.dispose();
  second.observe(state([call("C-021")]));
  assert.equal(spoken.length, 1);
  second.observe(state([call("C-021"), call("T-014", 1, "2030-10-15T11:32:00")]));
  assert.equal(spoken.length, 2);
});
