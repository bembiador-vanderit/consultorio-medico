import type { PublicCall, PublicQueueDisplayState } from "../types/queueDisplay";

export type AudioStatus = "off" | "muted" | "needs_activation" | "active" | "standby" | "unsupported" | "error";

const small = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
  "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho",
  "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco",
  "veintiséis", "veintisiete", "veintiocho", "veintinueve"];
const tens = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"];

function spokenNumber(value: number): string {
  if (value < 30) return small[value] ?? String(value);
  if (value < 100) return tens[Math.floor(value / 10)] + (value % 10 ? ` y ${small[value % 10]}` : "");
  return String(value).split("").map((digit) => small[Number(digit)]).join(" ");
}

export function spokenTicketCode(code: string): string {
  const match = /^([A-Z]{1,4})-(\d{1,3})$/i.exec(code);
  if (!match) return code.replace(/[^A-Za-z0-9-]/g, " ").trim();
  const prefix = match[1].toUpperCase().split("").join(" ");
  const digits = match[2];
  const value = Number(digits);
  return `${prefix} ${digits.length > 1 && digits.startsWith("0") && value > 0 ? "cero " : ""}${spokenNumber(value)}`;
}

export function announcementPhrase(call: PublicCall, audio: PublicQueueDisplayState["audio"]): string {
  const destination = call.destination.trim().replace(/\b\d{1,2}\b/g, (value) => spokenNumber(Number(value)));
  const preposition = /^(consultorio|cubículo|módulo|box)\b/i.test(destination) ? "al" : "a";
  const optional = [
    audio.announce_service_name && call.queue_line_name ? ` Servicio: ${call.queue_line_name}.` : "",
    audio.announce_provider_name && call.provider_name ? ` Profesional: ${call.provider_name}.` : "",
  ].join("");
  return `Turno ${spokenTicketCode(call.ticket_code)}, favor pasar ${preposition} ${destination}.${optional}`;
}

export function callIdentity(call: PublicCall): string {
  return `${call.ticket_code}|${call.called_at}|${call.call_revision}`;
}

function scopeKey(token: string): string {
  let value = 2166136261;
  for (const char of token) value = Math.imul(value ^ char.charCodeAt(0), 16777619);
  return (value >>> 0).toString(16);
}

type Pending = { key: string; call: PublicCall };
type Lease = { id: string; until: number };

// The lease is browser-local; the database remains the source of truth for calls.
export class QueueDisplayAudio {
  private readonly tabId = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  private readonly key: string;
  private readonly preferenceKey: string;
  private readonly announcedKey: string;
  private channel: BroadcastChannel | null = null;
  private heartbeat: number | null = null;
  private seen = new Set<string>();
  private pending: Pending[] = [];
  private initialized = false;
  private armed = false;
  private muted = false;
  private leader = false;
  private disposed = false;
  private speaking = false;
  private repeatTimer: number | null = null;
  private cueTimer: number | null = null;
  private cue: OscillatorNode | null = null;
  private output: AudioContext | null = null;
  private audio: PublicQueueDisplayState["audio"] | null = null;

  constructor(token: string, private readonly status: (value: AudioStatus) => void) {
    const scope = scopeKey(token);
    this.key = `atlas.queue.audio.leader.${scope}`;
    this.preferenceKey = `atlas.queue.audio.preference.${scope}`;
    this.announcedKey = `atlas.queue.audio.announced.${scope}`;
    try { this.muted = this.storage()?.getItem(this.preferenceKey) === "off"; }
    catch { this.muted = false; }
    if (typeof BroadcastChannel !== "undefined") {
      this.channel = new BroadcastChannel(`atlas.queue.audio.${scope}`);
      this.channel.onmessage = (event: MessageEvent) => {
        if (event.data?.type === "spoken") {
          this.seen.add(event.data.key);
          this.pending = this.pending.filter((item) => item.key !== event.data.key);
        } else if (event.data?.type === "leader" || event.data?.type === "released") this.tick();
      };
    }
    window.addEventListener("storage", this.onStorage);
    window.speechSynthesis?.addEventListener?.("voiceschanged", this.onVoicesChanged);
  }

  private readonly onStorage = (event: StorageEvent) => {
    if (event.key === this.key) this.tick();
    if (event.key === this.announcedKey) this.pending = this.pending.filter((item) => !this.wasAnnounced(item.key));
  };

  private readonly onVoicesChanged = () => {
    if (!this.audio?.audio_enabled || this.disposed) return;
    this.status(this.supported() ? (this.armed ? (this.leader ? "active" : "standby") : this.muted ? "muted" : "needs_activation") : "unsupported");
  };

  private announced(): string[] {
    try {
      const value = JSON.parse(this.storage()?.getItem(this.announcedKey) || "[]");
      return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
    } catch { return []; }
  }

  private wasAnnounced(key: string): boolean {
    return this.announced().includes(key);
  }

  private markAnnounced(key: string): void {
    try { this.storage()?.setItem(this.announcedKey, JSON.stringify([...this.announced(), key].slice(-100))); }
    catch { /* BroadcastChannel still coordinates live tabs. */ }
  }

  private supported(): boolean {
    return typeof window.speechSynthesis !== "undefined" &&
      typeof SpeechSynthesisUtterance !== "undefined" && this.localVoice() !== null;
  }

  private localVoice(): SpeechSynthesisVoice | null {
    const voices = window.speechSynthesis?.getVoices?.() ?? [];
    const localSpanish = voices.filter((voice) => voice.localService === true && /^es(?:-|$)/i.test(voice.lang));
    if (this.audio?.audio_voice_uri) {
      return localSpanish.find((voice) => voice.voiceURI === this.audio?.audio_voice_uri) ?? null;
    }
    const requested = this.audio?.audio_language.toLowerCase() ?? "es-do";
    return localSpanish.find((voice) => voice.lang.toLowerCase() === requested) ?? localSpanish[0] ?? null;
  }

  private storage(): Storage | null {
    try { return window.localStorage; } catch { return null; }
  }

  private lease(): Lease | null {
    try {
      const raw = this.storage()?.getItem(this.key);
      if (!raw) return null;
      const lease = JSON.parse(raw) as Lease;
      return typeof lease.id === "string" && Number.isFinite(lease.until) ? lease : null;
    } catch { return null; }
  }

  private tick(): void {
    if (this.disposed || !this.armed || !this.audio?.audio_enabled) return;
    const storage = this.storage();
    if (!storage) { this.leader = false; this.status("unsupported"); return; }
    const lease = this.lease();
    if (!lease || lease.until <= Date.now() || lease.id === this.tabId) {
      try { storage.setItem(this.key, JSON.stringify({ id: this.tabId, until: Date.now() + 5000 })); }
      catch { this.leader = false; this.status("unsupported"); return; }
    }
    const isLeader = this.lease()?.id === this.tabId;
    if (!isLeader && this.leader && this.speaking) {
      if (this.repeatTimer !== null) { window.clearTimeout(this.repeatTimer); this.repeatTimer = null; }
      this.speaking = false;
      window.speechSynthesis.cancel();
    }
    if (isLeader && !this.leader) this.channel?.postMessage({ type: "leader" });
    this.leader = isLeader;
    this.status(isLeader ? "active" : "standby");
    if (isLeader) this.drain();
  }

  observe(state: PublicQueueDisplayState): void {
    if (this.disposed) return;
    this.audio = state.audio;
    const calls = [...state.current_calls, ...state.recent_calls];
    const valid = new Set(calls.map(callIdentity));
    this.pending = this.pending.filter((item) => valid.has(item.key));
    if (!state.audio.audio_enabled) {
      this.stop();
      this.status("off");
    } else if (!this.supported()) this.status("unsupported");
    else if (!this.armed) this.status(this.muted ? "muted" : "needs_activation");
    const novel = calls.filter((call) => !this.seen.has(callIdentity(call)))
      .sort((left, right) => left.called_at.localeCompare(right.called_at) || left.ticket_code.localeCompare(right.ticket_code));
    for (const call of novel) {
      const key = callIdentity(call);
      this.seen.add(key);
      if (this.initialized && state.audio.audio_enabled && this.armed) this.pending.push({ key, call });
    }
    this.initialized = true;
    if (this.armed) this.tick();
  }

  activate(): void {
    if (this.disposed || !this.audio?.audio_enabled) return;
    if (!this.supported()) { this.status("unsupported"); return; }
    if (!this.storage()) { this.status("unsupported"); return; }
    this.armed = true;
    this.muted = false;
    if (!this.output && typeof window.AudioContext !== "undefined") {
      try { this.output = new window.AudioContext(); }
      catch { this.output = null; }
    }
    if (this.output?.state === "suspended") void this.output.resume().catch(() => {});
    try { this.storage()?.setItem(this.preferenceKey, "on"); } catch { /* preference is optional */ }
    if (this.heartbeat === null) this.heartbeat = window.setInterval(() => this.tick(), 2000);
    this.tick();
  }

  mute(): void {
    this.muted = true;
    try { this.storage()?.setItem(this.preferenceKey, "off"); } catch { /* preference is optional */ }
    this.stop();
    this.status(this.audio?.audio_enabled ? "muted" : "off");
  }

  suspend(): void {
    this.stop();
    this.status(this.audio?.audio_enabled ? (this.muted ? "muted" : "needs_activation") : "off");
  }

  private stop(): void {
    this.armed = false;
    this.leader = false;
    this.pending = [];
    this.speaking = false;
    if (this.repeatTimer !== null) { window.clearTimeout(this.repeatTimer); this.repeatTimer = null; }
    if (this.cueTimer !== null) { window.clearTimeout(this.cueTimer); this.cueTimer = null; }
    if (this.cue) { try { this.cue.stop(); } catch { /* Already stopped. */ } this.cue.disconnect(); this.cue = null; }
    if (this.output) { void this.output.close().catch(() => {}); this.output = null; }
    if (this.heartbeat !== null) { window.clearInterval(this.heartbeat); this.heartbeat = null; }
    if (this.lease()?.id === this.tabId) {
      try { this.storage()?.removeItem(this.key); } catch { /* best effort */ }
      this.channel?.postMessage({ type: "released" });
    }
    window.speechSynthesis?.cancel();
  }

  private primeOutput(continueSpeaking: () => void): void {
    const context = this.output;
    const level = Math.min(0.12, (this.audio?.audio_volume ?? 1) * 0.12);
    if (!context || context.state !== "running" || level <= 0) { continueSpeaking(); return; }
    try {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const start = context.currentTime;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(660, start);
      gain.gain.setValueAtTime(0.001, start);
      gain.gain.linearRampToValueAtTime(level, start + 0.04);
      gain.gain.setValueAtTime(level, start + 0.4);
      gain.gain.linearRampToValueAtTime(0.001, start + 0.5);
      oscillator.connect(gain);
      gain.connect(context.destination);
      this.cue = oscillator;
      oscillator.onended = () => {
        oscillator.disconnect(); gain.disconnect();
        if (this.cue === oscillator) this.cue = null;
        if (this.armed && !this.disposed) this.cueTimer = window.setTimeout(() => {
          this.cueTimer = null;
          continueSpeaking();
        }, 150);
      };
      oscillator.start(start);
      oscillator.stop(start + 0.51);
    } catch { this.cue = null; continueSpeaking(); }
  }

  private drain(): void {
    if (!this.armed || !this.leader || this.speaking || !this.pending.length || !this.audio?.audio_enabled) return;
    if (this.lease()?.id !== this.tabId) { this.leader = false; this.status("standby"); return; }
    const next = this.pending.shift()!;
    if (this.wasAnnounced(next.key)) { this.drain(); return; }
    const audio = this.audio;
    this.speaking = true;
    this.markAnnounced(next.key);
    this.channel?.postMessage({ type: "spoken", key: next.key });
    let remaining = audio.repeat_count;
    let primed = false;
    const speak = () => {
      if (!this.armed || !this.leader || !this.audio?.audio_enabled || this.lease()?.id !== this.tabId) {
        this.speaking = false; return;
      }
      if (!primed) { primed = true; this.primeOutput(speak); return; }
      try {
        const utterance = new SpeechSynthesisUtterance(announcementPhrase(next.call, audio));
        utterance.volume = audio.audio_volume;
        utterance.rate = audio.audio_rate;
        utterance.pitch = audio.audio_pitch;
        const voice = this.localVoice();
        if (!voice) { this.stop(); this.status("unsupported"); return; }
        utterance.voice = voice;
        utterance.lang = voice.lang;
        utterance.onend = () => {
          if (!this.armed) return;
          remaining -= 1;
          if (remaining > 0) this.repeatTimer = window.setTimeout(() => { this.repeatTimer = null; speak(); }, audio.repeat_delay_ms);
          else { this.speaking = false; this.drain(); }
        };
        utterance.onerror = () => {
          console.warn("Queue display speech unavailable");
          this.stop();
          this.status("error");
        };
        window.speechSynthesis.speak(utterance);
      } catch {
        console.warn("Queue display speech unavailable");
        this.stop();
        this.status("error");
      }
    };
    speak();
  }

  dispose(): void {
    if (this.disposed) return;
    this.stop();
    this.disposed = true;
    window.removeEventListener("storage", this.onStorage);
    window.speechSynthesis?.removeEventListener?.("voiceschanged", this.onVoicesChanged);
    this.channel?.close();
  }
}
