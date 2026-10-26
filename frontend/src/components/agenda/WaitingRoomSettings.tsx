import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { QueueLine } from "../../types/queue";
import type { WaitingRoom } from "../../types/waitingRoom";

type Center = { id: number; name: string };
type Person = { id: number; full_name: string; roles: string[]; is_active: boolean; centerIds: number[] };
type Draft = { center_id: number; name: string; code: string; description: string; is_active: boolean; sort_order: number };
const blank = (centerId = 0): Draft => ({ center_id: centerId, name: "", code: "", description: "", is_active: true, sort_order: 0 });
const message = (error: any) => error?.response?.data?.detail || "No fue posible guardar la sala.";

export function WaitingRoomSettings({ centers, people }: { centers: Center[]; people: Person[] }) {
  const [rooms, setRooms] = useState<WaitingRoom[]>([]);
  const [lines, setLines] = useState<QueueLine[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(blank(centers[0]?.id));
  const [lineIds, setLineIds] = useState<number[]>([]);
  const [secretaryIds, setSecretaryIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const [roomsResponse, linesResponse] = await Promise.all([
      api.get<WaitingRoom[]>("/waiting-rooms"), api.get<QueueLine[]>("/queue-lines"),
    ]);
    setRooms(roomsResponse.data); setLines(linesResponse.data);
    return roomsResponse.data;
  }
  useEffect(() => { void load().catch((reason) => setError(message(reason))); }, []);

  function selectRoom(id: number | null, available = rooms) {
    setSelected(id); setError("");
    const room = available.find((item) => item.id === id);
    setDraft(room ? { center_id: room.center_id, name: room.name, code: room.code || "",
      description: room.description || "", is_active: room.is_active, sort_order: room.sort_order } : blank(centers[0]?.id));
    setLineIds(room?.queue_lines.map((line) => line.id) || []);
    setSecretaryIds(room?.secretaries.map((person) => person.user_id) || []);
  }

  async function saveRoom() {
    if (busy || !draft.center_id || !draft.name.trim()) return;
    setBusy(true); setError("");
    try {
      const payload = { ...draft, name: draft.name.trim(), code: draft.code.trim() || null,
        description: draft.description.trim() || null };
      const { data } = selected
        ? await api.put<WaitingRoom>(`/waiting-rooms/${selected}`, payload)
        : await api.post<WaitingRoom>("/waiting-rooms", payload);
      const available = await load(); selectRoom(data.id, available);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function saveAssignments(kind: "queue-lines" | "secretaries") {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try {
      await api.put(`/waiting-rooms/${selected}/${kind}`, kind === "queue-lines"
        ? { queue_line_ids: lineIds } : { secretary_user_ids: secretaryIds });
      const available = await load(); selectRoom(selected, available);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  const room = rooms.find((item) => item.id === selected);
  const availableLines = lines.filter((line) => line.center_id === draft.center_id);
  const secretaries = people.filter((person) => person.roles.includes("secretary") && person.is_active && person.centerIds.includes(draft.center_id));
  const toggle = (ids: number[], id: number) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];

  return <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm" aria-label="Salas de espera">
    <h3 className="font-semibold">Salas de espera</h3>
    <p className="mt-1 text-sm text-slate-500">Cada sala pertenece a un centro. La asignación no modifica permisos de agenda ni clínicos.</p>
    <div className="mt-4 flex flex-wrap gap-2">{rooms.map((item) =>
      <button key={item.id} type="button" className={`rounded border px-3 py-2 text-sm ${selected === item.id ? "border-teal-700 bg-teal-50" : ""}`}
        onClick={() => selectRoom(item.id)}>{item.name} · {centers.find((center) => center.id === item.center_id)?.name || item.center_id}{!item.is_active ? " · inactiva" : ""}</button>)}
      <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => selectRoom(null)}>Nueva sala</button></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label className="text-sm">Centro<select className="mt-1 w-full rounded border p-2" disabled={!!selected} value={draft.center_id || ""} onChange={(event) => setDraft(blank(Number(event.target.value)))}><option value="">Seleccione</option>{centers.map((center) => <option key={center.id} value={center.id}>{center.name}</option>)}</select></label>
      <label className="text-sm">Nombre<input className="mt-1 w-full rounded border p-2" maxLength={120} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
      <label className="text-sm">Código opcional<input className="mt-1 w-full rounded border p-2" maxLength={30} value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} /></label>
      <label className="text-sm sm:col-span-2">Descripción<input className="mt-1 w-full rounded border p-2" maxLength={500} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
      <label className="text-sm">Orden<input className="mt-1 w-full rounded border p-2" type="number" min={0} value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label>
    </div>
    <label className="mt-3 block text-sm"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /> Sala activa</label>
    <button type="button" className="mt-4 rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy || !draft.center_id || !draft.name.trim() || draft.sort_order < 0} onClick={() => void saveRoom()}>{selected ? "Guardar sala" : "Crear sala"}</button>
    {selected && <div className="mt-5 grid gap-5 lg:grid-cols-2">
      <fieldset className="rounded border p-3"><legend className="px-1 font-medium">Médicos y líneas de atención</legend>
        {availableLines.map((line) => <label key={line.id} className="mt-2 block text-sm"><input type="checkbox" checked={lineIds.includes(line.id)} disabled={!draft.is_active && !lineIds.includes(line.id)} onChange={() => setLineIds(toggle(lineIds, line.id))} /> {line.doctor_name} — {line.name} — {line.prefix}{line.waiting_room_id && line.waiting_room_id !== selected ? " · cambiará de sala" : ""}</label>)}
        {!availableLines.length && <p className="text-sm text-slate-500">No hay líneas en este centro.</p>}
        <button type="button" className="mt-3 rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={busy} onClick={() => void saveAssignments("queue-lines")}>Guardar líneas</button></fieldset>
      <fieldset className="rounded border p-3"><legend className="px-1 font-medium">Secretarias</legend>
        {secretaries.map((person) => <label key={person.id} className="mt-2 block text-sm"><input type="checkbox" checked={secretaryIds.includes(person.id)} disabled={!draft.is_active && !secretaryIds.includes(person.id)} onChange={() => setSecretaryIds(toggle(secretaryIds, person.id))} /> {person.full_name}</label>)}
        {!secretaries.length && <p className="text-sm text-slate-500">No hay secretarias asignadas al centro.</p>}
        <button type="button" className="mt-3 rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={busy} onClick={() => void saveAssignments("secretaries")}>Guardar secretarias</button></fieldset>
      <div><h4 className="font-medium">Pantallas de esta sala</h4>{room?.displays.length ? room.displays.map((display) => <p key={display.id} className="text-sm">{display.name} · {display.is_active ? "Activa" : "Inactiva"}</p>) : <p className="text-sm text-slate-500">Ninguna pantalla asignada.</p>}</div>
    </div>}
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
  </section>;
}
