import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { QueueLine } from "../../types/queue";
import type { QueueDisplay, QueueDisplayLine, QueueDisplayToken } from "../../types/queueDisplay";
import type { WaitingRoom } from "../../types/waitingRoom";

type Center = { id: number; name: string };
type Draft = {
  center_id: number;
  waiting_room_id: number | null;
  name: string;
  is_active: boolean;
  show_service_name: boolean;
  show_provider_name: boolean;
  recent_call_limit: number;
  audio_enabled: boolean;
  audio_volume: number;
  audio_language: "es-DO" | "es";
  audio_voice_uri: string | null;
  audio_rate: number;
  audio_pitch: number;
  repeat_count: number;
  repeat_delay_ms: number;
  announce_service_name: boolean;
  announce_provider_name: boolean;
  lines: QueueDisplayLine[];
};
const blank = (centerId = 0): Draft => ({ center_id: centerId, waiting_room_id: null, name: "", is_active: true,
  show_service_name: false, show_provider_name: false, recent_call_limit: 5, lines: [],
  audio_enabled: false, audio_volume: 1, audio_language: "es-DO", audio_voice_uri: null, audio_rate: 1, audio_pitch: 1,
  repeat_count: 1, repeat_delay_ms: 1000, announce_service_name: false, announce_provider_name: false });
const message = (reason: any) => reason?.response?.data?.detail || "No fue posible guardar la pantalla.";

export function QueueDisplaySettings({ centers, showWaitingRooms = false }: { centers: Center[]; showWaitingRooms?: boolean }) {
  const [displays, setDisplays] = useState<QueueDisplay[]>([]);
  const [rooms, setRooms] = useState<WaitingRoom[]>([]);
  const [lines, setLines] = useState<QueueLine[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(blank(centers[0]?.id));
  const [newToken, setNewToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [displayResponse, lineResponse] = await Promise.all([
      api.get<QueueDisplay[]>("/queue-displays"), api.get<QueueLine[]>("/queue-lines"),
    ]);
    setDisplays(displayResponse.data);
    setLines(lineResponse.data);
    if (showWaitingRooms) {
      const roomResponse = await api.get<WaitingRoom[]>("/waiting-rooms");
      setRooms(roomResponse.data);
    }
  }
  useEffect(() => { void load().catch((reason) => setError(message(reason))); }, []);

  function selectDisplay(id: number | null) {
    setSelectedId(id);
    setNewToken(null);
    const display = displays.find((item) => item.id === id);
    setDraft(display ? { center_id: display.center_id, waiting_room_id: display.waiting_room_id ?? null, name: display.name, is_active: display.is_active,
      show_service_name: display.show_service_name, show_provider_name: display.show_provider_name,
      recent_call_limit: display.recent_call_limit, lines: display.lines.map((line) => ({ ...line })),
      audio_enabled: display.audio_enabled, audio_volume: display.audio_volume,
      audio_language: display.audio_language, audio_voice_uri: display.audio_voice_uri,
      audio_rate: display.audio_rate, audio_pitch: display.audio_pitch,
      repeat_count: display.repeat_count, repeat_delay_ms: display.repeat_delay_ms,
      announce_service_name: display.announce_service_name, announce_provider_name: display.announce_provider_name }
      : blank(centers[0]?.id));
  }

  function toggleLine(line: QueueLine, checked: boolean) {
    setDraft((current) => ({ ...current, lines: checked
      ? [...current.lines, { queue_line_id: line.id, destination: "", sort_order: current.lines.length, is_active: true }]
      : current.lines.filter((item) => item.queue_line_id !== line.id).map((item, index) => ({ ...item, sort_order: index })) }));
  }

  function editLine(lineId: number, change: Partial<QueueDisplayLine>) {
    setDraft((current) => ({ ...current, lines: current.lines.map((item) => item.queue_line_id === lineId ? { ...item, ...change } : item) }));
  }

  function moveLine(lineId: number, offset: number) {
    setDraft((current) => {
      const ordered = [...current.lines].sort((a, b) => a.sort_order - b.sort_order);
      const from = ordered.findIndex((item) => item.queue_line_id === lineId);
      const to = from + offset;
      if (from < 0 || to < 0 || to >= ordered.length) return current;
      [ordered[from], ordered[to]] = [ordered[to], ordered[from]];
      return { ...current, lines: ordered.map((item, index) => ({ ...item, sort_order: index })) };
    });
  }

  async function save() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const payload = { ...draft, name: draft.name.trim(), lines: draft.lines.map((line) => ({
        queue_line_id: line.queue_line_id, destination: line.destination.trim(),
        sort_order: line.sort_order, is_active: line.is_active,
      })) };
      if (selectedId) await api.put(`/queue-displays/${selectedId}`, payload);
      else {
        const { data } = await api.post<QueueDisplayToken>("/queue-displays", payload);
        setSelectedId(data.id); setNewToken(data.access_token);
      }
      await load();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function rotate() {
    if (!selectedId || busy || !window.confirm("¿Regenerar la clave? La pantalla anterior dejará de funcionar.")) return;
    setBusy(true); setError("");
    try { const { data } = await api.post<QueueDisplayToken>(`/queue-displays/${selectedId}/rotate-token`);
      setNewToken(data.access_token); await load();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  const availableLines = lines.filter((line) => line.center_id === draft.center_id &&
    (line.is_active || draft.lines.some((item) => item.queue_line_id === line.id)));
  const orderedLines = [...draft.lines].sort((a, b) => a.sort_order - b.sort_order);
  const link = newToken ? `${window.location.origin}/queue-display/${encodeURIComponent(newToken)}` : null;

  return <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm" aria-label="Pantallas de turnos">
    <h3 className="font-semibold">Pantallas de turnos</h3>
    <p className="mt-1 text-sm text-slate-500">Una pantalla reúne varias líneas del mismo centro. Solo publica código de turno y destino.</p>
    <div className="mt-4 flex flex-wrap gap-2">{displays.map((display) =>
      <button key={display.id} type="button" className={`rounded border px-3 py-2 text-sm ${selectedId === display.id ? "border-teal-700 bg-teal-50" : ""}`} onClick={() => selectDisplay(display.id)}>{display.name} · {display.center_name}</button>)}
      <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => selectDisplay(null)}>Nueva pantalla</button>
    </div>
    <fieldset className="mt-5 rounded border p-4" aria-label="Audio de pantalla">
      <legend className="px-1 font-medium">Audio (solo en la pantalla pública)</legend>
      <p className="mb-2 text-xs text-slate-500">La voz concreta se elige en Seguridad con una cuenta administradora.</p>
      <label className="block text-sm"><input type="checkbox" checked={draft.audio_enabled} onChange={(event) => setDraft((current) => ({ ...current, audio_enabled: event.target.checked }))} /> Audio habilitado</label>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm">Volumen (0–1)<input className="mt-1 w-full rounded border p-2" type="number" min={0} max={1} step={0.1} value={draft.audio_volume} onChange={(event) => setDraft((current) => ({ ...current, audio_volume: Number(event.target.value) }))} /></label>
        <label className="text-sm">Idioma<select className="mt-1 w-full rounded border p-2" value={draft.audio_language} onChange={(event) => setDraft((current) => ({ ...current, audio_language: event.target.value as "es-DO" | "es" }))}><option value="es-DO">Español (RD)</option><option value="es">Español</option></select></label>
        <label className="text-sm">Velocidad (0.5–2)<input className="mt-1 w-full rounded border p-2" type="number" min={0.5} max={2} step={0.1} value={draft.audio_rate} onChange={(event) => setDraft((current) => ({ ...current, audio_rate: Number(event.target.value) }))} /></label>
        <label className="text-sm">Tono (0.5–2)<input className="mt-1 w-full rounded border p-2" type="number" min={0.5} max={2} step={0.1} value={draft.audio_pitch} onChange={(event) => setDraft((current) => ({ ...current, audio_pitch: Number(event.target.value) }))} /></label>
        <label className="text-sm">Repeticiones por llamada (1–10)<input className="mt-1 w-full rounded border p-2" type="number" min={1} max={10} value={draft.repeat_count} onChange={(event) => setDraft((current) => ({ ...current, repeat_count: Number(event.target.value) }))} /></label>
        <label className="text-sm">Pausa entre repeticiones (ms)<input className="mt-1 w-full rounded border p-2" type="number" min={1000} max={5000} step={500} value={draft.repeat_delay_ms} onChange={(event) => setDraft((current) => ({ ...current, repeat_delay_ms: Number(event.target.value) }))} /></label>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        <label><input type="checkbox" checked={draft.announce_service_name} disabled={!draft.show_service_name} onChange={(event) => setDraft((current) => ({ ...current, announce_service_name: event.target.checked }))} /> Anunciar servicio</label>
        <label><input type="checkbox" checked={draft.announce_provider_name} disabled={!draft.show_provider_name} onChange={(event) => setDraft((current) => ({ ...current, announce_provider_name: event.target.checked }))} /> Anunciar médico</label>
      </div>
    </fieldset>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label className="text-sm">Centro<select className="mt-1 w-full rounded border p-2" value={draft.center_id || ""} disabled={!!selectedId} onChange={(event) => setDraft(blank(Number(event.target.value)))}><option value="">Seleccione</option>{centers.map((center) => <option key={center.id} value={center.id}>{center.name}</option>)}</select></label>
      {showWaitingRooms && <label className="text-sm">Sala de espera<select className="mt-1 w-full rounded border p-2" value={draft.waiting_room_id ?? ""} onChange={(event) => setDraft((current) => ({ ...current, waiting_room_id: Number(event.target.value) || null }))}><option value="">Sin sala (líneas explícitas)</option>{rooms.filter((room) => room.center_id === draft.center_id && (room.is_active || room.id === draft.waiting_room_id)).map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>}
      <label className="text-sm">Nombre<input className="mt-1 w-full rounded border p-2" maxLength={120} value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
      <label className="text-sm">Llamadas recientes<input className="mt-1 w-full rounded border p-2" type="number" min={3} max={10} value={draft.recent_call_limit} onChange={(event) => setDraft((current) => ({ ...current, recent_call_limit: Number(event.target.value) }))} /></label>
      <div className="flex flex-col gap-2 text-sm"><label><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))} /> Pantalla activa</label>
        <label><input type="checkbox" checked={draft.show_service_name} onChange={(event) => setDraft((current) => ({ ...current, show_service_name: event.target.checked }))} /> Mostrar servicio</label>
        <label><input type="checkbox" checked={draft.show_provider_name} onChange={(event) => setDraft((current) => ({ ...current, show_provider_name: event.target.checked }))} /> Mostrar médico</label></div>
    </div>
    <div className="mt-5"><h4 className="font-medium">Líneas del centro</h4>{showWaitingRooms && draft.waiting_room_id && <p className="text-xs text-slate-500">La sala aporta sus líneas automáticamente. Las asociaciones explícitas de esa sala pueden ajustar destino y visibilidad; las de otras salas se conservan, pero no se muestran.</p>}{availableLines.length ? availableLines.map((line) => {
      const assignment = draft.lines.find((item) => item.queue_line_id === line.id);
      return <div key={line.id} className="mt-2 flex flex-wrap items-center gap-3 rounded border p-3 text-sm">
        <label><input type="checkbox" checked={!!assignment} onChange={(event) => toggleLine(line, event.target.checked)} /> {line.prefix} · {line.name}</label>
        {assignment && <><label>Destino visible<input className="ml-2 rounded border p-2" maxLength={80} placeholder="Consultorio 3" value={assignment.destination} onChange={(event) => editLine(line.id, { destination: event.target.value })} /></label>
          <label><input type="checkbox" checked={assignment.is_active} onChange={(event) => editLine(line.id, { is_active: event.target.checked })} /> Mostrar</label>
          <button type="button" aria-label={`Subir ${line.name}`} onClick={() => moveLine(line.id, -1)}>↑</button>
          <button type="button" aria-label={`Bajar ${line.name}`} onClick={() => moveLine(line.id, 1)}>↓</button></>}
      </div>;
    }) : <p className="mt-2 text-sm text-slate-500">No hay líneas configuradas en este centro.</p>}</div>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    <div className="mt-4 flex flex-wrap gap-2"><button type="button" className="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy || !draft.center_id || !draft.name.trim() || draft.recent_call_limit < 3 || draft.recent_call_limit > 10 || draft.audio_volume < 0 || draft.audio_volume > 1 || draft.audio_rate < 0.5 || draft.audio_rate > 2 || draft.audio_pitch < 0.5 || draft.audio_pitch > 2 || draft.repeat_count < 1 || draft.repeat_count > 10 || draft.repeat_delay_ms < 1000 || draft.repeat_delay_ms > 5000 || orderedLines.some((item) => !item.destination.trim())} onClick={() => void save()}>{selectedId ? "Guardar pantalla" : "Crear pantalla"}</button>
      {selectedId && <button type="button" className="rounded border px-4 py-2 disabled:opacity-50" disabled={busy} onClick={() => void rotate()}>Regenerar clave</button>}</div>
    {link && <p className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm">Enlace público (cópielo ahora; no se volverá a mostrar): <a className="break-all font-medium text-teal-800 underline" href={link} target="_blank" rel="noreferrer">{link}</a></p>}
  </section>;
}
