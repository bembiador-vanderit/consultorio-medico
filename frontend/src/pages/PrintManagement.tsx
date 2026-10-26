import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";
import "./printManagement.css";

type Printer = {
  id: number;
  local_id: string;
  display_name: string;
  driver: string | null;
  connection: "Local" | "Network" | "Unknown";
  available: boolean;
  is_virtual: boolean;
  last_seen_at: string;
};
type Station = {
  id: number;
  agent_uuid: string;
  station_name: string;
  center_id: number;
  status: "online" | "offline" | "degraded" | "revoked";
  last_seen_at: string;
  printers: Printer[];
};
type Registry = {
  organization: { id: number; name: string };
  centers: { id: number; name: string }[];
  agents: Station[];
};

const stationLabels: Record<Station["status"], string> = {
  online: "Conectada",
  offline: "Desconectada",
  degraded: "Conexión degradada",
  revoked: "Revocada",
};
const connectionLabels: Record<Printer["connection"], string> = {
  Local: "Local",
  Network: "De red",
  Unknown: "Conexión no informada",
};
const formatDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "No disponible" : date.toLocaleString();
};
const availableCount = (station: Station) => station.printers.filter((printer) => printer.available).length;
const availableLabel = (count: number) => `${count} ${count === 1 ? "impresora disponible" : "impresoras disponibles"}`;

export default function PrintManagement({ user }: { user: User }) {
  const canView = !!user.permissions?.includes("local_agents:view");
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [openStationId, setOpenStationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  async function load() {
    if (!canView) return;
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get<Registry>("/local-agents/registry");
      setRegistry(data);
      setOpenStationId((previous) => previous !== null && data.agents.some((station) => station.id === previous)
        ? previous : null);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [canView]);

  if (!canView) return <p role="alert">No tiene permiso para ver Gestión de impresión.</p>;

  return <section className="print-management" aria-label="Gestión de impresión">
    <header className="print-management-header">
      <div><p className="print-management-eyebrow">Administración · {registry?.organization.name ?? "Atlas"}</p>
        <h1>Gestión de impresión</h1>
        <p>Consulte las estaciones y sus impresoras disponibles.</p></div>
      <div className="print-management-actions"><button type="button" className="print-management-history-button" aria-expanded={historyOpen} onClick={() => setHistoryOpen((open) => !open)}>Historial de impresión</button>
        <button type="button" onClick={() => void load()} disabled={loading}>Actualizar inventario</button></div>
    </header>
    {historyOpen && <section className="print-management-history" aria-label="Historial de impresión"><h2>Historial de impresión</h2><p>El historial de impresión estará disponible en esta sección.</p></section>}
    <p className="print-management-note">Inventario operativo de solo lectura. La conexión de una estación y la disponibilidad de sus impresoras se muestran por separado; aquí no se envían trabajos.</p>
    {error && <p role="alert" className="print-management-alert">No pudimos cargar el inventario. Intente actualizarlo de nuevo.{registry ? " Se muestran los últimos datos cargados." : ""}</p>}
    {loading && !registry && <p role="status">Cargando estaciones…</p>}
    {registry && <>
      <div className="print-management-summary" aria-label="Resumen del inventario">
        <span><strong>{registry.agents.length}</strong> estaciones registradas</span>
        <span><strong>{registry.agents.filter((item) => item.status === "online").length}</strong> conectadas</span>
        <span><strong>{registry.agents.reduce((total, item) => total + availableCount(item), 0)}</strong> impresoras disponibles</span>
      </div>
      {registry.agents.length === 0 ? <div className="print-management-empty"><h2>Sin estaciones</h2><p>Esta organización todavía no tiene estaciones registradas.</p></div> :
        <section className="print-management-list" aria-label="Estaciones">
            <div className="print-management-section-heading"><h2>Estaciones</h2><span>{registry.agents.length}</span></div>
            {registry.agents.map((item) => {
              const itemCenter = registry.centers.find((candidate) => candidate.id === item.center_id);
              const isOpen = item.id === openStationId;
              const panelId = `print-management-station-panel-${item.id}`;
              const toggleId = `print-management-station-toggle-${item.id}`;
              const operationalPrinters = item.printers.filter((printer) => printer.available);
              return <article key={item.id} className="print-management-station-card">
                <button id={toggleId} type="button" className="print-management-station" aria-expanded={isOpen} aria-controls={panelId} onClick={() => setOpenStationId((current) => current === item.id ? null : item.id)}>
                  <span className="print-management-station-top"><strong>{item.station_name}</strong><span className={`print-management-status print-management-status--${item.status}`}>{stationLabels[item.status]}</span></span>
                  <span className="print-management-muted">{itemCenter?.name ?? "Centro no disponible"}</span>
                  <span className="print-management-station-meta"><strong className="print-management-station-count">{availableLabel(availableCount(item))}</strong><span className="print-management-muted">Última conexión: {formatDate(item.last_seen_at)}</span></span>
                  <span className="print-management-station-action"><span>{isOpen ? "Ocultar impresoras" : "Ver impresoras"}</span><span className="print-management-chevron" aria-hidden="true" /></span>
                </button>
                <section id={panelId} className="print-management-station-panel" aria-labelledby={toggleId} aria-label={`Impresoras de ${item.station_name}`} hidden={!isOpen}>
                  {isOpen && <div className="print-management-detail">
                    <div className="print-management-detail-head"><div><p className="print-management-eyebrow">{registry.organization.name} · {itemCenter?.name ?? "Centro no disponible"}</p><h3>{item.station_name}</h3></div><span className={`print-management-status print-management-status--${item.status}`}>{stationLabels[item.status]}</span></div>
                    <p className="print-management-muted">Última conexión: {formatDate(item.last_seen_at)}</p>
                    {item.status !== "online" && <p className="print-management-alert">La estación no está conectada normalmente. Su inventario puede reflejar la última sincronización.</p>}
                    <div className="print-management-detail-count"><strong>{availableLabel(operationalPrinters.length)}</strong></div>
                    <details className="print-management-technical"><summary>Datos técnicos de la estación</summary><dl><dt>UUID</dt><dd>{item.agent_uuid}</dd></dl></details>
                    <div className="print-management-section-heading"><h3>Impresoras</h3></div>
                    {item.printers.length === 0 ? <p className="print-management-empty">Esta estación todavía no ha sincronizado impresoras.</p> : operationalPrinters.length === 0 ? <p className="print-management-empty">No hay impresoras disponibles en esta estación.</p> :
                      <ul className="print-management-printers">{operationalPrinters.map((printer) => <li key={printer.id} className="print-management-printer">
                        <div className="print-management-printer-head"><strong>{printer.display_name}</strong><span className="print-management-availability print-management-availability--available">Disponible</span></div>
                        <p>{connectionLabels[printer.connection] ?? "Conexión no informada"}{printer.is_virtual ? " · Virtual" : ""}</p>
                        <p className="print-management-muted">Última sincronización: {formatDate(printer.last_seen_at)}</p>
                        <details className="print-management-technical"><summary>Datos técnicos</summary><dl><dt>ID estable</dt><dd>{printer.local_id}</dd><dt>Driver</dt><dd>{printer.driver ?? "No informado"}</dd></dl></details>
                      </li>)}</ul>
                    }
                  </div>}
                </section>
              </article>;
            })}
        </section>}
    </>}
  </section>;
}
