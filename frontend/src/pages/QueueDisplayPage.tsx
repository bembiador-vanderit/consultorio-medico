import { useEffect, useRef, useState } from "react";
import type { PublicCall, PublicQueueDisplayState } from "../types/queueDisplay";
import { QueueDisplayAudio, type AudioStatus } from "../services/queueDisplayAudio";

const apiBase = (import.meta.env.VITE_API_URL?.trim() || "/api/v1").replace(/\/$/, "");

function CallTile({ call, prominent = false }: { call: PublicCall; prominent?: boolean }) {
  return <article className={`rounded-3xl border border-cyan-400/40 bg-slate-800 p-6 ${prominent ? "md:p-10" : "md:p-7"}`}>
    <strong className={`block font-black tracking-tight text-cyan-200 ${prominent ? "text-6xl md:text-8xl" : "text-4xl md:text-5xl"}`}>{call.ticket_code}</strong>
    <span className={`mt-3 block font-semibold text-white ${prominent ? "text-3xl md:text-5xl" : "text-2xl md:text-3xl"}`}>{call.destination}</span>
    {call.queue_line_name && <span className="mt-3 block text-lg text-slate-300">{call.queue_line_name}</span>}
    {call.provider_name && <span className="block text-lg text-slate-300">{call.provider_name}</span>}
  </article>;
}

export default function QueueDisplayPage({ token }: { token: string }) {
  const [state, setState] = useState<PublicQueueDisplayState | null>(null);
  const [connection, setConnection] = useState<"loading" | "connected" | "refreshing" | "unavailable">("loading");
  const [audioStatus, setAudioStatus] = useState<AudioStatus>("off");
  const audioRef = useRef<QueueDisplayAudio | null>(null);

  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "referrer";
    meta.content = "no-referrer";
    document.head.append(meta);
    let mounted = true;
    let inFlight = false;
    const audio = new QueueDisplayAudio(token, (status) => { if (mounted) setAudioStatus(status); });
    audioRef.current = audio;
    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      if (mounted) setConnection((current) => current === "connected" ? "refreshing" : current);
      try {
        const response = await fetch(`${apiBase}/queue/displays/${encodeURIComponent(token)}/state`, {
          credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
        });
        if (!response.ok) throw new Error("unavailable");
        const data = await response.json() as PublicQueueDisplayState;
        if (mounted) { audio.observe(data); setState(data); setConnection("connected"); }
      } catch {
        if (mounted) { audio.suspend(); setState(null); setConnection("unavailable"); }
      } finally { inFlight = false; }
    }
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => { mounted = false; window.clearInterval(interval); audio.dispose(); audioRef.current = null; meta.remove(); };
  }, [token]);

  return <main className="min-h-screen bg-slate-950 px-5 py-8 text-white md:px-12 md:py-10" aria-label="Pantalla pública de turnos">
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-700 pb-6">
      <div><p className="text-lg font-semibold uppercase tracking-widest text-cyan-300">Turnos</p>
        <h1 className="mt-2 text-3xl font-bold md:text-5xl">{state?.display_name || "Pantalla de turnos"}</h1>
        {state?.waiting_room_name && <p className="mt-2 text-2xl font-semibold text-cyan-200">{state.waiting_room_name}</p>}
        {!!state?.provider_names?.length && <p className="mt-2 text-lg text-slate-200">{state.provider_names.join(" · ")}</p>}
        {!!state?.service_names?.length && <p className="mt-1 text-base text-slate-300">{state.service_names.join(" · ")}</p>}
        {state?.center_name && <p className="mt-2 text-xl text-slate-300">{state.center_name}</p>}</div>
      <p role="status" className="rounded-full border border-slate-600 px-4 py-2 text-sm text-slate-300">
        {connection === "connected" ? "Conectado" : connection === "refreshing" ? "Actualizando" : connection === "loading" ? "Conectando" : "Pantalla no disponible"}
      </p>
    </header>
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm" aria-label="Estado de audio">
      <span>{!state?.audio.audio_enabled ? "🔇 Audio desactivado" : audioStatus === "active" ? "🔊 Audio activo"
        : audioStatus === "standby" ? "🔇 Audio activo en otra pestaña"
        : audioStatus === "unsupported" && state?.audio.audio_voice_uri ? "La voz configurada no está instalada en este dispositivo"
        : audioStatus === "unsupported" ? "Audio no disponible en este dispositivo"
        : audioStatus === "error" ? "Audio no disponible; puede reactivarlo"
        : audioStatus === "muted" ? "🔇 Audio silenciado en este dispositivo" : "🔇 Audio pendiente de activación"}</span>
      {state?.audio.audio_enabled && (audioStatus === "needs_activation" || audioStatus === "muted" || audioStatus === "error") &&
        <button type="button" className="rounded border border-cyan-400 px-3 py-2 text-cyan-200" onClick={() => audioRef.current?.activate()}>Activar audio</button>}
      {state?.audio.audio_enabled && (audioStatus === "active" || audioStatus === "standby") &&
        <button type="button" className="rounded border border-slate-500 px-3 py-2" onClick={() => audioRef.current?.mute()}>Silenciar aquí</button>}
    </div>
    {connection === "unavailable" ? <p className="mt-16 text-center text-2xl">No es posible mostrar los turnos en este momento.</p> : <>
      <section className="mt-10" aria-label="Turnos llamados"><h2 className="mb-6 text-2xl font-bold uppercase tracking-wider text-cyan-300">Ahora</h2>
        {state?.current_calls.length ? <div className="grid gap-5 xl:grid-cols-2 2xl:grid-cols-3">{state.current_calls.map((call, index) => <CallTile key={`${call.ticket_code}-${call.called_at}-${call.call_revision}`} call={call} prominent={index === 0} />)}</div>
          : <p className="rounded-2xl bg-slate-800 p-8 text-2xl text-slate-300">Sin turnos llamados en este momento</p>}
      </section>
      {!!state?.recent_calls.length && <section className="mt-12" aria-label="Llamadas recientes"><h2 className="mb-6 text-2xl font-bold uppercase tracking-wider text-slate-300">Llamadas recientes</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{state.recent_calls.map((call) => <CallTile key={`${call.ticket_code}-${call.called_at}-${call.call_revision}`} call={call} />)}</div>
      </section>}
    </>}
  </main>;
}
