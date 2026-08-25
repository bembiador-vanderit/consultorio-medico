import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import type { Appointment } from "../types/appointment";

type Props = { onBack: () => void };
const statuses: Record<string, string> = { scheduled: "Programada", confirmed: "Confirmada", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió" };

type ReportFilters = { from: string; to: string; status: string; search: string };

function formatDate(value: string) {
  if (!value) return "—";
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function AppointmentReports({ onBack }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [items, setItems] = useState<Appointment[]>([]);
  const [filters, setFilters] = useState<ReportFilters>({ from: today, to: today, status: "", search: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get<Appointment[]>("/appointments");
      setItems(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "No fue posible cargar las citas.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtered = useMemo(() => items.filter((item) => {
    if (filters.from && item.appointment_date < filters.from) return false;
    if (filters.to && item.appointment_date > filters.to) return false;
    if (filters.status && item.status !== filters.status) return false;
    const q = filters.search.trim().toLowerCase();
    if (q && !`${item.patient_name} ${item.doctor_name} ${item.center_name || ""} ${item.reason || ""}`.toLowerCase().includes(q)) return false;
    return true;
  }).sort((a, b) => `${a.appointment_date} ${a.appointment_time}`.localeCompare(`${b.appointment_date} ${b.appointment_time}`)), [items, filters]);

  const summary = useMemo(() => filtered.reduce((acc, item) => {
    acc.total += 1;
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, { total: 0 } as Record<string, number>), [filtered]);

  const reportText = `Reporte de citas\nPeriodo: ${formatDate(filters.from)} - ${formatDate(filters.to)}\nTotal: ${filtered.length}\n\n${filtered.map((a) => `${formatDate(a.appointment_date)} ${a.appointment_time.slice(0, 5)} — ${a.patient_name} — ${a.doctor_name} — ${a.center_name || "Sin centro"} — ${statuses[a.status] || a.status}`).join("\n")}`;

  function print() {
    window.print();
  }

  function shareWhatsApp() {
    window.open(`https://wa.me/?text=${encodeURIComponent(reportText)}`, "_blank", "noopener,noreferrer");
  }

  function shareEmail() {
    const subject = `Reporte de citas ${filters.from} - ${filters.to}`;
    window.location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(reportText)}`;
  }

  return <section>
    <div className="print:hidden">
      <button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button>
      <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div><h2 className="text-2xl font-bold">Reportes de citas</h2><p className="mt-1 text-sm text-slate-500">Consulta, imprime o comparte el resumen de la agenda.</p></div>
        <div className="flex flex-wrap gap-2"><button onClick={print} disabled={!filtered.length} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">🖨️ Imprimir / PDF</button><button onClick={shareWhatsApp} disabled={!filtered.length} className="rounded-lg bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">WhatsApp</button><button onClick={shareEmail} disabled={!filtered.length} className="rounded-lg border px-4 py-2 text-sm font-medium disabled:opacity-40">Correo</button></div>
      </div>
      <div className="mt-6 grid gap-4 rounded-xl border bg-white p-4 shadow-sm md:grid-cols-4">
        <label className="text-sm font-medium">Desde<input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label>
        <label className="text-sm font-medium">Hasta<input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label>
        <label className="text-sm font-medium">Estado<select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="mt-1 w-full rounded-lg border p-2"><option value="">Todos</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="text-sm font-medium">Buscar<input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="Paciente, médico o centro" className="mt-1 w-full rounded-lg border p-2" /></label>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-4"><div className="rounded-xl border bg-white p-4"><p className="text-xs uppercase text-slate-500">Total</p><p className="mt-1 text-2xl font-bold">{summary.total || 0}</p></div>{Object.entries(statuses).slice(0, 3).map(([key, label]) => <div key={key} className="rounded-xl border bg-white p-4"><p className="text-xs uppercase text-slate-500">{label}</p><p className="mt-1 text-2xl font-bold">{summary[key] || 0}</p></div>)}</div>
    </div>

    <div className="mt-6 rounded-xl border bg-white shadow-sm print:mt-0 print:border-0 print:shadow-none">
      <div className="hidden border-b pb-4 print:block"><h1 className="text-2xl font-bold">Reporte de citas</h1><p className="text-sm text-slate-600">Periodo: {formatDate(filters.from)} - {formatDate(filters.to)}</p><p className="text-sm text-slate-600">Total de citas: {filtered.length}</p></div>
      {loading ? <p className="p-6 text-slate-500">Cargando reporte...</p> : error ? <p className="p-6 text-red-700">{error}</p> : filtered.length === 0 ? <p className="p-10 text-center text-slate-500">No hay citas para los filtros seleccionados.</p> : <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 print:bg-white"><tr><th className="px-4 py-3">Fecha</th><th className="px-4 py-3">Hora</th><th className="px-4 py-3">Paciente</th><th className="px-4 py-3">Médico</th><th className="px-4 py-3">Centro</th><th className="px-4 py-3">Estado</th><th className="px-4 py-3">Motivo</th></tr></thead><tbody className="divide-y divide-slate-100">{filtered.map((a) => <tr key={a.id}><td className="px-4 py-3">{formatDate(a.appointment_date)}</td><td className="px-4 py-3">{a.appointment_time.slice(0, 5)}</td><td className="px-4 py-3 font-medium">{a.patient_name}</td><td className="px-4 py-3">{a.doctor_name}</td><td className="px-4 py-3">{a.center_name ? `${a.center_name} (${a.center_city})` : "—"}</td><td className="px-4 py-3">{statuses[a.status] || a.status}</td><td className="px-4 py-3">{a.reason || "—"}</td></tr>)}</tbody></table></div>}
    </div>
  </section>;
}
