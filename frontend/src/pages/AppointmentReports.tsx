import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import type { Appointment } from "../types/appointment";

type Props = { onBack: () => void };
const labels: Record<string, string> = { scheduled: "Programada", confirmed: "Confirmada", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió" };

export default function AppointmentReports({ onBack }: Props) {
  const [items, setItems] = useState<Appointment[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { api.get<Appointment[]>("/appointments").then(r => setItems(r.data)).catch((e: any) => setError(e?.response?.data?.detail || "No fue posible cargar las citas.")); }, []);

  const filtered = useMemo(() => items.filter(a => {
    const dateOk = (!from || a.appointment_date >= from) && (!to || a.appointment_date <= to);
    const statusOk = status === "all" || a.status === status;
    const q = query.trim().toLowerCase();
    const text = `${a.patient_name} ${a.doctor_name} ${a.center_name || ""} ${a.reason || ""}`.toLowerCase();
    return dateOk && statusOk && (!q || text.includes(q));
  }), [items, from, to, status, query]);

  const shareText = `Reporte de citas: ${filtered.length} citas. ${from || ""}${from || to ? " a " : ""}${to || ""}`;
  const whatsapp = () => window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, "_blank", "noopener,noreferrer");
  const email = () => { window.location.href = `mailto:?subject=${encodeURIComponent("Reporte de citas")}&body=${encodeURIComponent(shareText)}`; };

  return <section>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between print:hidden"><div><button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button><h2 className="mt-2 text-2xl font-bold">Reportes de citas</h2><p className="mt-1 text-sm text-slate-500">Consulta, filtra e imprime la agenda.</p></div><div className="flex gap-2"><button onClick={() => window.print()} className="rounded-lg bg-slate-800 px-4 py-2 font-medium text-white">Imprimir / PDF</button><button onClick={whatsapp} className="rounded-lg bg-green-700 px-4 py-2 font-medium text-white">WhatsApp</button><button onClick={email} className="rounded-lg bg-teal-700 px-4 py-2 font-medium text-white">Correo</button></div></div>
    {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="mt-5 grid gap-3 rounded-xl border bg-white p-4 shadow-sm sm:grid-cols-4 print:hidden"><label className="text-sm font-medium">Desde<input type="date" value={from} onChange={e => setFrom(e.target.value)} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-sm font-medium">Hasta<input type="date" value={to} onChange={e => setTo(e.target.value)} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-sm font-medium">Estado<select value={status} onChange={e => setStatus(e.target.value)} className="mt-1 w-full rounded-lg border p-2"><option value="all">Todos</option>{Object.entries(labels).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label className="text-sm font-medium">Buscar<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Paciente, médico, centro..." className="mt-1 w-full rounded-lg border p-2" /></label></div>
    <div className="mt-5 rounded-xl border bg-white shadow-sm"><div className="border-b p-4"><h3 className="font-bold">Resumen</h3><p className="text-sm text-slate-500">{filtered.length} cita{filtered.length === 1 ? "" : "s"} encontrada{filtered.length === 1 ? "" : "s"}.</p></div><div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Fecha</th><th className="px-4 py-3">Hora</th><th className="px-4 py-3">Paciente</th><th className="px-4 py-3">Médico</th><th className="px-4 py-3">Centro</th><th className="px-4 py-3">Estado</th><th className="px-4 py-3">Motivo</th></tr></thead><tbody className="divide-y">{filtered.map(a => <tr key={a.id}><td className="px-4 py-3">{a.appointment_date}</td><td className="px-4 py-3">{a.appointment_time.slice(0,5)}</td><td className="px-4 py-3 font-medium">{a.patient_name}</td><td className="px-4 py-3">{a.doctor_name}</td><td className="px-4 py-3">{a.center_name ? `${a.center_name} (${a.center_city})` : "—"}</td><td className="px-4 py-3">{labels[a.status] || a.status}</td><td className="px-4 py-3">{a.reason || "—"}</td></tr>)}</tbody></table></div></div>
  </section>;
}
