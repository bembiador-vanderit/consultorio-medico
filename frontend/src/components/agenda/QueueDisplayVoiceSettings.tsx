import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { QueueDisplay } from "../../types/queueDisplay";

function localSpanishVoices(): SpeechSynthesisVoice[] {
  return (window.speechSynthesis?.getVoices?.() ?? [])
    .filter((voice) => voice.localService === true && /^es(?:-|$)/i.test(voice.lang))
    .sort((left, right) => left.lang.localeCompare(right.lang) || left.name.localeCompare(right.name));
}

export function QueueDisplayVoiceSettings() {
  const [displays, setDisplays] = useState<QueueDisplay[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [voiceUri, setVoiceUri] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const refreshVoices = () => { if (active) setVoices(localSpanishVoices()); };
    refreshVoices();
    window.speechSynthesis?.addEventListener?.("voiceschanged", refreshVoices);
    void api.get<QueueDisplay[]>("/queue-displays")
      .then(({ data }) => { if (active) {
        setDisplays(data);
        if (data.length) { setSelectedId(data[0].id); setVoiceUri(data[0].audio_voice_uri ?? ""); }
      } })
      .catch((reason) => { if (active) setError(reason?.response?.data?.detail || "No se pudieron cargar las pantallas."); });
    return () => {
      active = false;
      window.speechSynthesis?.removeEventListener?.("voiceschanged", refreshVoices);
      window.speechSynthesis?.cancel?.();
    };
  }, []);

  function selectDisplay(id: number) {
    setSelectedId(id);
    setVoiceUri(displays.find((display) => display.id === id)?.audio_voice_uri ?? "");
    setMessage(""); setError("");
  }

  function preview() {
    const voice = voices.find((item) => item.voiceURI === voiceUri) ?? voices[0];
    if (!voice || typeof SpeechSynthesisUtterance === "undefined") return;
    window.speechSynthesis.cancel();
    const sample = new SpeechSynthesisUtterance("Atención. Turno C cero veintiuno, favor pasar al Consultorio tres.");
    sample.voice = voice;
    sample.lang = voice.lang;
    window.speechSynthesis.speak(sample);
  }

  async function save() {
    if (!selectedId || busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const { data } = await api.put<QueueDisplay>(`/queue-displays/${selectedId}/voice`, { audio_voice_uri: voiceUri || null });
      setDisplays((current) => current.map((display) => display.id === data.id ? data : display));
      setVoiceUri(data.audio_voice_uri ?? "");
      setMessage("Voz guardada para esta pantalla.");
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No se pudo guardar la voz.");
    } finally { setBusy(false); }
  }

  const selected = displays.find((display) => display.id === selectedId);
  const selectedVoiceMissing = !!voiceUri && !voices.some((voice) => voice.voiceURI === voiceUri);
  return <section className="rounded-xl border bg-white p-5" aria-label="Voz de pantallas de turnos">
    <h3 className="font-bold">Voz de pantallas de turnos</h3>
    <p className="mt-1 text-sm text-slate-600">Solo voces españolas locales de este navegador; no se envían anuncios a proveedores externos. Pruebe la voz para elegir el timbre y acento.</p>
    {!displays.length && !error && <p className="mt-3 text-sm">No hay pantallas configuradas.</p>}
    {!!displays.length && <div className="mt-3 flex flex-wrap items-end gap-3">
      <label className="text-sm">Pantalla<select className="mt-1 block rounded border p-2" value={selectedId} onChange={(event) => selectDisplay(Number(event.target.value))}>
        {displays.map((display) => <option key={display.id} value={display.id}>{display.name} · {display.center_name}</option>)}
      </select></label>
      <label className="text-sm">Voz local<select className="mt-1 block max-w-full rounded border p-2" value={voiceUri} onChange={(event) => setVoiceUri(event.target.value)}>
        <option value="">Automática (voz española local disponible)</option>
        {selectedVoiceMissing && <option value={voiceUri} disabled>Voz configurada no instalada aquí</option>}
        {voices.map((voice) => <option key={`${voice.voiceURI}|${voice.lang}`} value={voice.voiceURI}>{voice.name} · {voice.lang}</option>)}
      </select></label>
      <button type="button" className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={!voices.length || selectedVoiceMissing} onClick={preview}>Probar voz</button>
      <button type="button" className="rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={busy || !selected || selectedVoiceMissing} onClick={() => void save()}>Guardar voz</button>
    </div>}
    {!voices.length && <p className="mt-2 text-sm text-amber-800">Esta PC no ofrece voces españolas locales al navegador. Instale una voz local y vuelva a abrir el panel.</p>}
    {selectedVoiceMissing && <p className="mt-2 text-sm text-amber-800">La voz guardada no está instalada en esta PC. Seleccione otra o use el modo automático. La pantalla de TV también debe tener instalada la voz elegida.</p>}
    {!!voices.length && <p className="mt-2 text-xs text-slate-500">El navegador informa nombre e idioma, no género. Una voz latinoamericana solo aparecerá si está instalada localmente en la PC que la reproduce.</p>}
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="mt-2 text-sm text-teal-700">{message}</p>}
  </section>;
}
