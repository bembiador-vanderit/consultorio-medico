import { useEffect, useState } from "react";
import { api } from "../../services/api";

type Doctor = { id: number; full_name: string; centerIds: number[] };
type Center = { id: number; name: string };
type Mode = "timed" | "queue";
type Policy = { allowed_timed: boolean; allowed_queue: boolean; default_mode: Mode };
type Resolution = {
  base_mode: Mode;
  exception_mode: Mode | null;
  effective_mode: Mode;
  base_policy?: Policy;
  exception_policy?: Policy | null;
  effective_policy?: Policy;
  queue_line_available?: boolean;
  multimode_enabled?: boolean;
};

const label = (mode: Mode) => mode === "timed" ? "Por hora" : "Por turno";
const singleton = (mode: Mode): Policy => ({ allowed_timed: mode === "timed", allowed_queue: mode === "queue", default_mode: mode });
function PolicyEditor({ title, policy, onChange }: { title: string; policy: Policy; onChange: (policy: Policy) => void }) {
  function toggle(mode: Mode, checked: boolean) {
    const next = { ...policy, [mode === "timed" ? "allowed_timed" : "allowed_queue"]: checked };
    if (!next.allowed_timed && !next.allowed_queue) return;
    if ((next.default_mode === "timed" && !next.allowed_timed) || (next.default_mode === "queue" && !next.allowed_queue)) {
      next.default_mode = next.allowed_timed ? "timed" : "queue";
    }
    onChange(next);
  }
  return <fieldset className="rounded-lg border p-3">
    <legend className="font-semibold">{title}</legend>
    <p className="font-medium">Modalidades permitidas</p>
    <div className="mt-2 flex flex-wrap gap-4">
      <label><input type="checkbox" checked={policy.allowed_timed} disabled={policy.allowed_timed && !policy.allowed_queue} onChange={event => toggle("timed", event.target.checked)} /> Por hora</label>
      <label><input type="checkbox" checked={policy.allowed_queue} disabled={policy.allowed_queue && !policy.allowed_timed} onChange={event => toggle("queue", event.target.checked)} /> Por turno</label>
    </div>
    <p className="mt-3 font-medium">Modalidad predeterminada</p>
    <div className="mt-2 flex flex-wrap gap-4">
      <label><input type="radio" name={`${title}-default`} checked={policy.default_mode === "timed"} disabled={!policy.allowed_timed} onChange={() => onChange({ ...policy, default_mode: "timed" })} /> Por hora</label>
      <label><input type="radio" name={`${title}-default`} checked={policy.default_mode === "queue"} disabled={!policy.allowed_queue} onChange={() => onChange({ ...policy, default_mode: "queue" })} /> Por turno</label>
    </div>
  </fieldset>;
}
const today = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

export function AgendaModeSettings({ doctors, centers }: { doctors: Doctor[]; centers: Center[] }) {
  const [doctorId, setDoctorId] = useState("");
  const [centerId, setCenterId] = useState("");
  const [day, setDay] = useState(today);
  const [resolution, setResolution] = useState<Resolution | null>(null);
  const [base, setBase] = useState<Policy>(singleton("timed"));
  const [exception, setException] = useState<Policy>(singleton("timed"));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(doctor: string, center: string, date: string) {
    if (!doctor || !center || !date) { setResolution(null); return; }
    try {
      const { data } = await api.get<Resolution>(`/agenda-settings/${doctor}/${center}/${date}`);
      setResolution(data);
      setBase(data.base_policy ?? singleton(data.base_mode));
      setException(data.exception_policy ?? data.effective_policy ?? singleton(data.effective_mode));
      setError("");
    } catch (reason: any) {
      setResolution(null);
      setError(reason?.response?.data?.detail || "No fue posible consultar la modalidad.");
    }
  }

  useEffect(() => { void load(doctorId, centerId, day); }, [doctorId, centerId, day]);

  async function save(operation: "base" | "exception" | "remove") {
    if (!doctorId || !centerId || !day) return;
    setBusy(true);
    setError("");
    try {
      const path = `/agenda-settings/${doctorId}/${centerId}`;
      if (operation === "base") await api.put(`${path}/base`, resolution?.multimode_enabled ? base : { mode: base.default_mode });
      else if (operation === "exception") await api.put(`${path}/exceptions/${day}`, resolution?.multimode_enabled ? exception : { mode: exception.default_mode });
      else await api.delete(`${path}/exceptions/${day}`);
      await load(doctorId, centerId, day);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible guardar la modalidad.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm" aria-label="Modalidad de agenda">
    <h3 className="font-semibold">Modalidad de agenda</h3>
    <p className="mt-1 text-sm text-slate-500">Modalidades por médico y centro, con excepciones por fecha. Las citas existentes conservan su modalidad registrada.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-3">
      <label className="text-sm font-medium">Médico<select className="mt-1 w-full rounded-lg border p-2.5" value={doctorId} onChange={event => { setDoctorId(event.target.value); setCenterId(""); }}><option value="">Seleccione</option>{doctors.map(doctor => <option key={doctor.id} value={doctor.id}>{doctor.full_name}</option>)}</select></label>
      <label className="text-sm font-medium">Centro<select className="mt-1 w-full rounded-lg border p-2.5" value={centerId} onChange={event => setCenterId(event.target.value)}><option value="">Seleccione</option>{centers.filter(center => doctors.find(doctor => doctor.id === Number(doctorId))?.centerIds.includes(center.id)).map(center => <option key={center.id} value={center.id}>{center.name}</option>)}</select></label>
      <label className="text-sm font-medium">Fecha de excepción<input className="mt-1 w-full rounded-lg border p-2.5" type="date" value={day} onChange={event => setDay(event.target.value)} /></label>
    </div>
    {resolution && <div className="mt-4 space-y-3 text-sm">
      <p>Predeterminada para esta fecha: <strong>{label(resolution.effective_mode)}</strong>{resolution.exception_mode && " · excepción"}</p>
      {resolution.multimode_enabled ? <>
        <p className="text-amber-800">Si desactiva una modalidad, las citas existentes conservarán su tipo original; revise las jornadas futuras antes de guardar.</p>
        <PolicyEditor title="Modo habitual" policy={base} onChange={setBase} />
        <button type="button" className="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy} onClick={() => void save("base")}>Guardar modo habitual</button>
        <PolicyEditor title="Excepción de esta fecha" policy={exception} onChange={setException} />
        <button type="button" className="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy} onClick={() => void save("exception")}>Guardar excepción</button>
      </> : <>
        <p className="text-slate-500">La selección de ambas modalidades estará disponible al activar la siguiente migración. Mientras tanto, se conserva una modalidad por jornada.</p>
        <div className="flex flex-wrap items-end gap-3"><label>Modo habitual<select className="ml-2 rounded-lg border p-2" value={base.default_mode} onChange={event => setBase(singleton(event.target.value as Mode))}><option value="timed">Por hora</option><option value="queue">Por turno</option></select></label><button type="button" className="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy} onClick={() => void save("base")}>Guardar modo habitual</button></div>
        <div className="flex flex-wrap items-end gap-3"><label>Excepción de esta fecha<select className="ml-2 rounded-lg border p-2" value={exception.default_mode} onChange={event => setException(singleton(event.target.value as Mode))}><option value="timed">Por hora</option><option value="queue">Por turno</option></select></label><button type="button" className="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" disabled={busy} onClick={() => void save("exception")}>Guardar excepción</button></div>
      </>}
      {resolution.exception_mode && <button type="button" className="rounded-lg border px-4 py-2 disabled:opacity-50" disabled={busy} onClick={() => void save("remove")}>Quitar excepción</button>}
      {(base.allowed_queue || exception.allowed_queue) && resolution.queue_line_available === false && <p role="alert" className="text-amber-800">Configure una línea de turnos para utilizar esta modalidad.</p>}
    </div>}
    <p className="mt-4 text-xs text-slate-500">Las citas por turno se agendan sin hora; el turno se asigna al registrar llegada.</p>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
  </section>;
}
