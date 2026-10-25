import { useMemo } from "react";
import { Button, Card, PageHeader } from "../ui";
import type { AccentTheme, NavigationItem } from "../navigation/navigation";
import { getDefaultGestionOrder, normalizeGestionOrder } from "../navigation/navigation";
import { normalizeDashboardWidgetOrder, type DashboardWidget } from "../components/dashboard/dashboardModel";
import "./workspacePersonalization.css";

const accentOptions: { id: AccentTheme; label: string }[] = [
  { id: "classic", label: "Atlas clásico" },
  { id: "blue", label: "Azul" },
  { id: "turquoise", label: "Turquesa" },
  { id: "clinical-green", label: "Verde clínico" },
  { id: "indigo", label: "Índigo" },
  { id: "violet", label: "Violeta" },
];

type Props = {
  modules: readonly NavigationItem[];
  gestionOrder: readonly string[];
  onGestionOrderChange: (order: string[]) => void;
  onResetGestionOrder: () => void;
  dashboardWidgets: readonly DashboardWidget[];
  dashboardOrder: readonly string[];
  onDashboardOrderChange: (order: string[]) => void;
  onResetDashboard: () => void;
  accentTheme: AccentTheme;
  onAccentThemeChange: (theme: AccentTheme) => void;
  onResetAll: () => void;
  onSave: () => void;
  loading: boolean;
  saving: boolean;
  error: string;
  saved: boolean;
};

export default function WorkspacePersonalization({ modules, gestionOrder, onGestionOrderChange, onResetGestionOrder, dashboardWidgets, dashboardOrder, onDashboardOrderChange, onResetDashboard, accentTheme, onAccentThemeChange, onResetAll, onSave, loading, saving, error, saved }: Props) {
  const orderedModules = useMemo(() => {
    const byId = new Map(modules.filter(item => item.group === "general").map(item => [item.id, item]));
    return normalizeGestionOrder(modules, gestionOrder).flatMap(id => byId.has(id) ? [byId.get(id)!] : []);
  }, [modules, gestionOrder]);
  const activeLabel = orderedModules[0]?.label ?? "Sin módulos disponibles";
  const orderedWidgets = useMemo(() => {
    const byId = new Map(dashboardWidgets.map(widget => [widget.id, widget]));
    return normalizeDashboardWidgetOrder(dashboardWidgets.map(widget => widget.id), dashboardOrder)
      .flatMap(id => byId.has(id) ? [byId.get(id)!] : []);
  }, [dashboardWidgets, dashboardOrder]);

  function move(index: number, direction: -1 | 1) {
    const next = [...orderedModules];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onGestionOrderChange(next.map(item => item.id));
  }

  function moveWidget(id: string, direction: -1 | 1) {
    const current = orderedWidgets.find(widget => widget.id === id);
    if (!current) return;
    const peers = orderedWidgets.filter(widget => widget.group === current.group);
    const index = peers.findIndex(widget => widget.id === id);
    const adjacent = peers[index + direction];
    if (!adjacent) return;
    const next = orderedWidgets.map(widget => widget.id);
    const first = next.indexOf(id), second = next.indexOf(adjacent.id);
    [next[first], next[second]] = [next[second], next[first]];
    onDashboardOrderChange(next);
  }

  return <section className="workspace-personalization" aria-label="Personalización del espacio de trabajo">
    <PageHeader eyebrow="Herramientas" title="Mi espacio de trabajo" description="Ordena tu navegación y Dashboard; elige un acento para tu cuenta." />
    {loading && <p role="status" className="workspace-personalization-notice">Cargando preferencias de tu cuenta…</p>}
    {error && <p role="alert" className="workspace-personalization-error">{error}</p>}
    {saved && !error && <p role="status" className="workspace-personalization-saved">Preferencias guardadas en tu cuenta.</p>}

    <Card className="workspace-personalization-card">
      <div className="workspace-personalization-section-heading"><div><h2>Navegación · orden de Gestión</h2><p>Solo aparecen los módulos que tu cuenta puede utilizar.</p></div>
        <Button type="button" variant="outline" onClick={onResetGestionOrder}>Restablecer orden predeterminado</Button>
      </div>
      {orderedModules.length ? <ol className="workspace-module-order" aria-label="Orden actual de módulos de Gestión">{orderedModules.map((item, index) => <li key={item.id} className="workspace-module-row">
        <span className="workspace-module-position" aria-label={`Posición ${index + 1}`}>{index + 1}</span><span className="workspace-module-name">{item.label}</span>
        <div className="workspace-module-controls"><Button type="button" variant="outline" aria-label={`Subir ${item.label}`} disabled={index === 0} onClick={() => move(index, -1)}>↑ Subir</Button><Button type="button" variant="outline" aria-label={`Bajar ${item.label}`} disabled={index === orderedModules.length - 1} onClick={() => move(index, 1)}>↓ Bajar</Button></div>
      </li>)}</ol> : <p>No hay módulos de Gestión disponibles para esta cuenta.</p>}
    </Card>

    <Card className="workspace-personalization-card">
      <div className="workspace-personalization-section-heading"><div><h2>Dashboard</h2><p>Ordena las tarjetas disponibles dentro de cada grupo. Los permisos deciden cuáles se muestran.</p></div>
        <Button type="button" variant="outline" onClick={onResetDashboard}>Restablecer Dashboard</Button>
      </div>
      {([['actions', 'Acciones rápidas'], ['metrics', 'Indicadores'], ['summary', 'Paneles']] as const).map(([group, label]) => {
        const widgets = orderedWidgets.filter(widget => widget.group === group);
        return widgets.length > 0 && <div className="workspace-widget-group" key={group}><h3>{label}</h3><ol className="workspace-module-order" aria-label={`Orden de ${label}`}>{widgets.map((widget, index) => <li key={widget.id} className="workspace-module-row" data-dashboard-widget-id={widget.id}>
          <span className="workspace-module-position" aria-label={`Posición ${index + 1}`}>{index + 1}</span><span className="workspace-module-name">{widget.label}</span>
          <div className="workspace-module-controls"><Button type="button" variant="outline" aria-label={`Subir ${widget.label}`} disabled={index === 0} onClick={() => moveWidget(widget.id, -1)}>↑ Subir</Button><Button type="button" variant="outline" aria-label={`Bajar ${widget.label}`} disabled={index === widgets.length - 1} onClick={() => moveWidget(widget.id, 1)}>↓ Bajar</Button></div>
        </li>)}</ol></div>;
      })}
    </Card>

    <Card className="workspace-personalization-card">
      <div className="workspace-personalization-section-heading"><div><h2>Apariencia</h2><p>Elige un acento Atlas. Los colores de error, alerta, éxito y estados clínicos/financieros no cambian.</p></div><Button type="button" variant="outline" onClick={() => onAccentThemeChange("classic")}>Restablecer apariencia</Button></div>
      <fieldset className="workspace-accent-fieldset"><legend>Color de acento</legend><div className="workspace-accent-options">{accentOptions.map(option => <button key={option.id} type="button" className="workspace-accent-option" data-accent-option={option.id} aria-pressed={accentTheme === option.id} onClick={() => onAccentThemeChange(option.id)}><span className="workspace-accent-swatch" aria-hidden="true" /><span>{option.label}</span>{accentTheme === option.id && <span className="workspace-accent-selected">Seleccionado</span>}</button>)}</div></fieldset>
      <div className="workspace-theme-preview" aria-label={`Vista previa del tema ${accentOptions.find(option => option.id === accentTheme)?.label}`}>
        <p className="workspace-theme-preview-label">Vista previa</p><div className="workspace-theme-preview-sidebar"><span className="workspace-theme-preview-active" aria-current="page">{activeLabel}</span></div><div className="workspace-theme-preview-controls"><Button type="button">Botón primario</Button><Button type="button" variant="outline" aria-current="page">Pestaña activa</Button></div>
      </div>
    </Card>
    <div className="workspace-personalization-actions"><Button type="button" variant="outline" onClick={onResetAll}>Restablecer todo</Button><Button type="button" onClick={onSave} disabled={loading || saving}>{saving ? "Guardando…" : "Guardar preferencias"}</Button></div>
  </section>;
}

export { accentOptions, getDefaultGestionOrder };
