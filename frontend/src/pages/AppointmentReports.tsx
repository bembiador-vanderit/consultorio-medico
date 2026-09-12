import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import type { Appointment } from "../types/appointment";
import { sortAppointments, type AppointmentSortKey, type SortDirection } from "../utils/appointmentSort";

type Props = { onBack: () => void };
const statuses: Record<string, string> = { scheduled: "Programada", confirmed: "Confirmada", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió" };

type ReportFilters = { from: string; to: string; status: string; search: string; doctorId: string; centerId: string };
type ReportDoctor = { id: number; full_name: string; center_ids: number[] };
type ReportCenter = { id: number; name: string; city?: string | null };
type ScopeOptions = { doctors: ReportDoctor[]; centers: ReportCenter[] };

function formatDate(value: string) {
  if (!value) return "—";
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function AppointmentReports({ onBack }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [items, setItems] = useState<Appointment[]>([]);
  const [doctors, setDoctors] = useState<ReportDoctor[]>([]);
  const [centers, setCenters] = useState<ReportCenter[]>([]);
  const [filters, setFilters] = useState<ReportFilters>({ from: today, to: today, status: "", search: "", doctorId: "", centerId: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);
  const [sort, setSort] = useState<{ key: AppointmentSortKey; direction: SortDirection }>({ key: "dateTime", direction: "desc" });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [appointments, options] = await Promise.all([
        api.get<Appointment[]>("/appointments"),
        api.get<ScopeOptions>("/appointments/scope-options"),
      ]);
      setItems(appointments.data);
      setDoctors(options.data.doctors);
      setCenters(options.data.centers);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "No fue posible cargar el reporte.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtered = useMemo(() => sortAppointments(items.filter((item) => {
    if (filters.from && item.appointment_date < filters.from) return false;
    if (filters.to && item.appointment_date > filters.to) return false;
    if (filters.status && item.status !== filters.status) return false;
    if (filters.doctorId && String(item.doctor_id) !== filters.doctorId) return false;
    if (filters.centerId && String(item.center_id) !== filters.centerId) return false;
    const q = filters.search.trim().toLowerCase();
    if (q && !`${item.patient_name} ${item.doctor_name} ${item.center_name || ""} ${item.reason || ""}`.toLowerCase().includes(q)) return false;
    return true;
  }), sort.key, sort.direction, statuses), [items, filters, sort]);

  const summary = useMemo(() => filtered.reduce((acc, item) => {
    acc.total += 1;
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, { total: 0 } as Record<string, number>), [filtered]);

  const visibleDoctors = useMemo(
    () => doctors.filter((doctor) => !filters.centerId || doctor.center_ids.includes(Number(filters.centerId))),
    [doctors, filters.centerId],
  );

  const reportText = `Reporte de citas\nPeriodo: ${formatDate(filters.from)} - ${formatDate(filters.to)}\nTotal: ${filtered.length}\n\n${filtered.map((a) => `${formatDate(a.appointment_date)} ${a.appointment_time.slice(0, 5)} — ${a.patient_name} — ${a.doctor_name} — ${a.center_name || "Sin centro"} — ${statuses[a.status] || a.status}`).join("\n")}`;

  function print() { window.print(); }

  async function downloadPdf() {
    if (!filtered.length) return;
    setPdfLoading(true);
    setError("");
    try {
      const response = await api.get<Blob>("/reports/appointments/pdf", {
        params: {
          start: filters.from || undefined,
          end: filters.to || undefined,
          status: filters.status || undefined,
          doctor_id: filters.doctorId || undefined,
          center_id: filters.centerId || undefined,
          search: filters.search.trim() || undefined,
        },
        responseType: "blob",
      });
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reporte-citas-${filters.from || "inicio"}-${filters.to || "fin"}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "No fue posible generar el PDF.");
    } finally {
      setPdfLoading(false);
    }
  }

  function shareWhatsApp() {
    window.open(`https://wa.me/?text=${encodeURIComponent(reportText)}`, "_blank", "noopener,noreferrer");
  }

  async function shareEmail() {
    if (!filtered.length) return;
    const to = window.prompt("Correo electrónico del destinatario:");
    if (!to) return;
    setEmailLoading(true);
    setError("");
    try {
      await api.post("/reports/appointments/email", null, {
        params: {
          to,
          start: filters.from || undefined,
          end: filters.to || undefined,
          appointment_status: filters.status || undefined,
          doctor_id: filters.doctorId || undefined,
          center_id: filters.centerId || undefined,
          search: filters.search.trim() || undefined,
        },
      });
      window.alert("Reporte PDF enviado por correo correctamente.");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "No fue posible enviar el reporte por correo.");
    } finally {
      setEmailLoading(false);
    }
  }

  function clearFilters() {
    setFilters({ from: today, to: today, status: "", search: "", doctorId: "", centerId: "" });
  }

  function toggleSort(key: AppointmentSortKey) {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
      : { key, direction: "asc" });
  }

  function sortableHeader(label: string, key: AppointmentSortKey, colSpan?: number) {
    const active = sort.key === key;
    return <th colSpan={colSpan} aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} className="px-4 py-3"><button type="button" onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 font-semibold hover:text-teal-700 print:text-inherit">{label}<span aria-hidden="true" className="print:hidden">{active ? (sort.direction === "asc" ? "↑" : "↓") : ""}</span></button></th>;
  }

  return <section>
    <div className="print:hidden">
      <button onClick={onBack} className="text-sm font-medium text-teal-700 hover:underline">← Volver al dashboard</button>
      <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div><h2 className="text-2xl font-bold">Reportes de citas</h2><p className="mt-1 text-sm text-slate-500">Consulta, filtra, descarga PDF, imprime o comparte el resumen de la agenda.</p></div>
        <div className="flex flex-wrap gap-2"><button onClick={downloadPdf} disabled={!filtered.length || pdfLoading} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{pdfLoading ? "Generando…" : "⬇️ Descargar PDF"}</button><button onClick={print} disabled={!filtered.length} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">🖨️ Imprimir</button><button onClick={shareWhatsApp} disabled={!filtered.length} className="rounded-lg bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">WhatsApp</button><button onClick={shareEmail} disabled={!filtered.length || emailLoading} className="rounded-lg border px-4 py-2 text-sm font-medium disabled:opacity-40">{emailLoading ? "Enviando…" : "Correo con PDF"}</button></div>
      </div>
      <div className="mt-6 grid gap-4 rounded-xl border bg-white p-4 shadow-sm md:grid-cols-3">
        <label className="text-sm font-medium">Desde<input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label>
        <label className="text-sm font-medium">Hasta<input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label>
        <label className="text-sm font-medium">Estado<select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="mt-1 w-full rounded-lg border p-2"><option value="">Todos</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="text-sm font-medium">Médico<select value={filters.doctorId} onChange={(e) => setFilters({ ...filters, doctorId: e.target.value })} className="mt-1 w-full rounded-lg border p-2"><option value="">Todos los médicos</option>{visibleDoctors.map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.full_name}</option>)}</select></label>
        <label className="text-sm font-medium">Centro<select value={filters.centerId} onChange={(e) => { const centerId = e.target.value; const selectedDoctor = doctors.find((doctor) => String(doctor.id) === filters.doctorId); setFilters({ ...filters, centerId, doctorId: selectedDoctor && centerId && !selectedDoctor.center_ids.includes(Number(centerId)) ? "" : filters.doctorId }); }} className="mt-1 w-full rounded-lg border p-2"><option value="">Todos los centros</option>{centers.map((center) => <option key={center.id} value={center.id}>{center.name}{center.city ? ` — ${center.city}` : ""}</option>)}</select></label>
        <label className="text-sm font-medium">Buscar<input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="Paciente, médico, centro o motivo" className="mt-1 w-full rounded-lg border p-2" /></label>
        <div className="flex items-end"><button onClick={clearFilters} className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-slate-50">Limpiar filtros</button></div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-4"><div className="rounded-xl border bg-white p-4"><p className="text-xs uppercase text-slate-500">Total</p><p className="mt-1 text-2xl font-bold">{summary.total || 0}</p></div>{Object.entries(statuses).slice(0, 3).map(([key, label]) => <div key={key} className="rounded-xl border bg-white p-4"><p className="text-xs uppercase text-slate-500">{label}</p><p className="mt-1 text-2xl font-bold">{summary[key] || 0}</p></div>)}</div>
    </div>

    <div className="mt-6 rounded-xl border bg-white shadow-sm print:mt-0 print:border-0 print:shadow-none">
      <div className="hidden border-b pb-4 print:block"><h1 className="text-2xl font-bold">Reporte de citas</h1><p className="text-sm text-slate-600">Periodo: {formatDate(filters.from)} - {formatDate(filters.to)}</p><p className="text-sm text-slate-600">Total de citas: {filtered.length}</p></div>
      {loading ? <p className="p-6 text-slate-500">Cargando reporte...</p> : error ? <p className="p-6 text-red-700">{error}</p> : filtered.length === 0 ? <p className="p-10 text-center text-slate-500">No hay citas para los filtros seleccionados.</p> : <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 print:bg-white"><tr>{sortableHeader("Fecha / Hora", "dateTime", 2)}{sortableHeader("Paciente", "patient")}{sortableHeader("Médico", "doctor")}{sortableHeader("Centro", "center")}{sortableHeader("Estado", "status")}<th className="px-4 py-3">Motivo</th></tr></thead><tbody className="divide-y divide-slate-100">{filtered.map((a) => <tr key={a.id}><td className="px-4 py-3">{formatDate(a.appointment_date)}</td><td className="px-4 py-3">{a.appointment_time.slice(0, 5)}</td><td className="px-4 py-3 font-medium">{a.patient_name}</td><td className="px-4 py-3">{a.doctor_name}</td><td className="px-4 py-3">{a.center_name ? `${a.center_name} (${a.center_city})` : "—"}</td><td className="px-4 py-3">{statuses[a.status] || a.status}</td><td className="px-4 py-3">{a.reason || "—"}</td></tr>)}</tbody></table></div>}
    </div>
  </section>;
}
