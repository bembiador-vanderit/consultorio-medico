import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";
import ClinicalFormDesigner from "./ClinicalFormDesigner";
import "./documentPersonalization.css";

type Kind = "invoice" | "receipt" | "cash_close";
type Definition = {
  page_format: "LETTER" | "A4"; orientation: "portrait" | "landscape";
  print_mode: "color" | "bw"; ink_saver: boolean;
  typography: "Helvetica" | "Times-Roman" | "Courier";
  show_logo: boolean; show_organization: boolean; show_center: boolean; show_professional: boolean;
  margin_mm: number; header_style: "plain" | "soft" | "medium";
  section_style: "plain" | "soft" | "medium"; accent_color: string; footer_note: string;
};
const defaults: Definition = {
  page_format: "LETTER", orientation: "portrait", print_mode: "color", ink_saver: true,
  typography: "Helvetica", show_logo: true, show_organization: true, show_center: true,
  show_professional: false, margin_mm: 18, header_style: "plain", section_style: "soft",
  accent_color: "#087f83", footer_note: "Documento interno. No es comprobante fiscal.",
};
const documents: { kind: Kind; label: string; icon: string }[] = [
  { kind: "invoice", label: "Factura interna", icon: "▤" },
  { kind: "receipt", label: "Recibo de pago", icon: "▣" },
  { kind: "cash_close", label: "Cierre de Caja", icon: "▥" },
];
function errorText(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "No se pudo completar la acción documental.";
}

export default function DocumentPersonalization({ user }: { user: User }) {
  const [advanced, setAdvanced] = useState(false);
  const [kind, setKind] = useState<Kind>("invoice");
  const [definition, setDefinition] = useState<Definition>(defaults);
  const [centerId, setCenterId] = useState(0);
  const [centers, setCenters] = useState<{ id: number; name: string }[]>([]);
  const [zoom, setZoom] = useState(100);
  const [compare, setCompare] = useState(true);
  const [draft, setDraft] = useState<{ template_id: number; version_id: number; version: number } | null>(null);
  const [source, setSource] = useState("Predeterminada Atlas");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const canManage = !!user.permissions?.includes("documents:manage");
  const canPublish = !!user.permissions?.includes("documents:publish");
  const clinicalDesigner = import.meta.env.VITE_CLINICAL_FORM_DESIGNER_ENABLED === "true" && !!user.permissions?.includes("clinical_forms:view");

  function update<K extends keyof Definition>(key: K, value: Definition[K]) {
    setDefinition(old => ({ ...old, [key]: value })); setMessage("");
  }
  useEffect(() => {
    if (!user.permissions?.includes("finance:read")) return;
    api.get<{ id: number; name: string }[]>("/finance/centers").then(({ data }) => setCenters(data)).catch(() => undefined);
  }, [user.permissions]);
  useEffect(() => {
    let active = true;
    setDraft(null); setError("");
    api.get<{ definition: Definition; source: string; version: number | null }>(`/documents/effective/${kind}`, {
      params: centerId ? { center_id: centerId } : {},
    }).then(({ data }) => {
      if (active) { setDefinition({ ...defaults, ...data.definition }); setSource(data.source === "atlas_default" ? "Predeterminada Atlas" : `${data.source} · versión ${data.version}`); }
    }).catch(error => { if (active && error?.response?.status !== 403) setError(errorText(error)); });
    return () => { active = false; };
  }, [kind, centerId]);

  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      const { data } = await api.post("/documents/drafts", {
        document_type: kind, name: documents.find(item => item.kind === kind)?.label,
        center_id: centerId || null, definition,
      });
      setDraft(data); setMessage(`Borrador v${data.version} guardado. Publíquelo para aplicarlo a nuevos PDF.`);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function publish() {
    if (!draft) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.post(`/documents/templates/${draft.template_id}/versions/${draft.version_id}/publish`);
      setMessage(`Versión ${draft.version} publicada.`); setSource(`Versión publicada ${draft.version}`); setDraft(null);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function previewPdf(action: "view" | "download" | "print") {
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/documents/preview/pdf", { document_type: kind, definition }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      if (action === "download") {
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = `atlas-muestra-${kind}.pdf`; anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        const opened = window.open(url, "_blank");
        if (!opened) { setError("Permita ventanas emergentes para abrir el PDF."); URL.revokeObjectURL(url); }
        else { opened.opener = null; if (action === "print") window.setTimeout(() => opened.print(), 900); window.setTimeout(() => URL.revokeObjectURL(url), 120_000); }
      }
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  return <section className="doc-design-page" aria-label="Personalización de documentos">
    <div className="doc-design-heading">
      <div className="doc-design-title"><span className="doc-design-title-icon" aria-hidden="true">▤</span><div><p className="doc-design-crumb">Herramientas › Documentos</p><h1>Personalización de documentos</h1><p>Personalice el diseño y la impresión de los documentos generados en Atlas Pérgamo.</p></div></div>
      <button className="doc-design-advanced" type="button" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}><span aria-hidden="true">▣</span><span><strong>{advanced ? "Personalización normal" : "Diseñador avanzado"}</strong><small>{advanced ? "Volver a los ajustes habituales" : "Plantillas y composición avanzada"}</small></span><span aria-hidden="true">›</span></button>
    </div>
    {advanced ? <div className="doc-design-advanced-body"><div className="doc-design-card"><h2>Diseñador avanzado</h2><p>Las plantillas financieras comparten el motor de presentación y versiones publicadas. Las zonas, columnas y variantes POS quedan preparadas para una fase posterior; no alteran datos contables.</p><button type="button" onClick={() => setAdvanced(false)}>Volver a documentos financieros</button></div>{clinicalDesigner && <div className="doc-design-card"><h2>Formularios clínicos existentes</h2><ClinicalFormDesigner /></div>}</div> :
    <div className="doc-design-layout">
      <div className="doc-design-controls">
        <div className="doc-design-card"><h2>Documento</h2><p>Seleccione el tipo de documento a personalizar.</p><label className="doc-design-field">Tipo de documento<select value={kind} onChange={event => setKind(event.target.value as Kind)}>{documents.map(item => <option key={item.kind} value={item.kind}>{item.label}</option>)}</select></label><div className="doc-design-document-tiles">{documents.map(item => <button type="button" key={item.kind} className={kind === item.kind ? "selected" : ""} onClick={() => setKind(item.kind)} aria-pressed={kind === item.kind}><span aria-hidden="true">{item.icon}</span>{item.label}</button>)}</div></div>
        <div className="doc-design-card"><h2>Plantilla</h2><p>La versión publicada define los PDF. Los cambios se guardan como borrador.</p><span className="doc-design-template-pill">▤ &nbsp; Plantilla estándar (Atlas) · {source}</span><label className="doc-design-field">Alcance<select value={centerId} onChange={event => setCenterId(Number(event.target.value))}><option value={0}>Organización</option>{centers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
        <div className="doc-design-card"><h2>Modo de impresión</h2><p>Configure cómo se verá el documento al imprimir.</p><div className="doc-design-choices"><button type="button" className={definition.print_mode === "color" ? "selected" : ""} onClick={() => update("print_mode", "color")} aria-pressed={definition.print_mode === "color"}><span aria-hidden="true">▣</span><strong>Color</strong><small>Versión full color de Atlas</small></button><button type="button" className={definition.print_mode === "bw" ? "selected" : ""} onClick={() => update("print_mode", "bw")} aria-pressed={definition.print_mode === "bw"}><span aria-hidden="true">▤</span><strong>Solo negro</strong><small>Optimizada para impresión B/N</small></button></div><label className="doc-design-check"><input type="checkbox" checked={definition.ink_saver} onChange={event => update("ink_saver", event.target.checked)} /> Optimizar tinta</label><p className="doc-design-note">En blanco y negro, los fondos de color se convierten en grises suaves; nunca en bloques negros.</p></div>
        <div className="doc-design-card"><h2>Encabezados y fondos</h2><p>Seleccione el estilo visual del encabezado.</p><div className="doc-design-choices doc-design-three">{(["plain", "soft", "medium"] as const).map((style, index) => <button type="button" key={style} className={definition.header_style === style ? "selected" : ""} onClick={() => update("header_style", style)} aria-pressed={definition.header_style === style}><span className={`doc-design-swatch doc-design-swatch--${style}`} aria-hidden="true" /><strong>{["Sin fondo", "Gris suave", "Gris medio"][index]}</strong></button>)}</div><label className="doc-design-field">Estilo de secciones<select value={definition.section_style} onChange={event => update("section_style", event.target.value as Definition["section_style"])}><option value="plain">Sin fondo</option><option value="soft">Fondo suave</option><option value="medium">Fondo medio</option></select></label></div>
        <div className="doc-design-card doc-design-short"><label className="doc-design-field">Tipografía<select value={definition.typography} onChange={event => update("typography", event.target.value as Definition["typography"])}><option value="Helvetica">Helvetica (recomendada)</option><option value="Times-Roman">Times</option><option value="Courier">Courier</option></select></label><label className="doc-design-field">Formato de página<select value={definition.page_format} onChange={event => update("page_format", event.target.value as Definition["page_format"])}><option value="LETTER">Carta</option><option value="A4">A4</option></select></label><label className="doc-design-field">Márgenes ({definition.margin_mm} mm)<input type="range" min="10" max="25" value={definition.margin_mm} onChange={event => update("margin_mm", Number(event.target.value))} /></label></div>
        <div className="doc-design-card doc-design-short"><h2>Identidad y datos</h2><label className="doc-design-check"><input type="checkbox" checked={definition.show_logo} onChange={event => update("show_logo", event.target.checked)} /> Mostrar marca Atlas</label><label className="doc-design-check"><input type="checkbox" checked={definition.show_organization} onChange={event => update("show_organization", event.target.checked)} /> Organización</label><label className="doc-design-check"><input type="checkbox" checked={definition.show_center} onChange={event => update("show_center", event.target.checked)} /> Centro</label><label className="doc-design-check"><input type="checkbox" checked={definition.show_professional} onChange={event => update("show_professional", event.target.checked)} /> Profesional, si aplica</label></div>
        <div className="doc-design-bottom"><button type="button" onClick={() => { setDefinition(defaults); setMessage("Configuración predeterminada en vista previa; guarde para conservarla."); }}>↶ &nbsp; Restablecer</button><button type="button" disabled={!canManage || busy} onClick={() => void save()}>▣ &nbsp; Guardar borrador</button>{draft && <button type="button" disabled={!canPublish || busy} onClick={() => void publish()}>Publicar versión</button>}</div>
      </div>
      <div className="doc-design-preview-panel"><div className="doc-design-preview-heading"><div><h2>Vista previa del documento</h2><p>Compare la pantalla a color con la salida B/N antes de publicar.</p></div><span>▤ &nbsp; {definition.print_mode === "bw" ? "Impresión en negro" : "Vista en color"}</span></div><div className="doc-design-preview-toolbar"><div><button type="button" onClick={() => setZoom(Math.max(70, zoom - 10))} aria-label="Reducir zoom">−</button><strong>{zoom}%</strong><button type="button" onClick={() => setZoom(Math.min(130, zoom + 10))} aria-label="Aumentar zoom">+</button></div><button type="button" onClick={() => setCompare(!compare)} aria-pressed={compare}>{compare ? "Vista única" : "Comparar color / B/N"}</button><button type="button" onClick={() => setZoom(100)}>Página completa</button></div>
      <div className={`doc-design-previews ${compare ? "doc-design-previews--compare" : ""}`}>
        {compare ? <><Preview kind={kind} definition={{ ...definition, print_mode: "color" }} label="Vista en pantalla / color" zoom={zoom} /><Preview kind={kind} definition={{ ...definition, print_mode: "bw" }} label="Vista para impresión B/N" zoom={zoom} /></> : <Preview kind={kind} definition={definition} label={definition.print_mode === "bw" ? "Vista para impresión B/N" : "Vista en pantalla / color"} zoom={zoom} />}
      </div><div className="doc-design-preview-actions"><button type="button" disabled={busy || !canManage} onClick={() => void previewPdf("view")}>Ver PDF de muestra</button><button type="button" disabled={busy || !canManage} onClick={() => void previewPdf("download")}>Descargar PDF</button><button type="button" disabled={busy || !canManage} onClick={() => void previewPdf("print")}>Imprimir</button></div><p className="doc-design-sample-note">Vista con datos ficticios. El PDF final usa importes del registro financiero existente.</p></div>
    </div>}
    {message && <p role="status" className="doc-design-message">{message}</p>}{error && <p role="alert" className="doc-design-error">{error}</p>}
  </section>;
}

function Preview({ kind, definition, label, zoom }: { kind: Kind; definition: Definition; label: string; zoom: number }) {
  const bw = definition.print_mode === "bw";
  const rows = kind === "invoice" ? [["Total", "DOP 2,000.00"], ["Parte ARS", "DOP 500.00"], ["Parte paciente", "DOP 1,500.00"], ["Pagado neto por paciente", "DOP 1,000.00"], ["Saldo paciente", "DOP 500.00"]]
    : kind === "receipt" ? [["Monto recibido", "DOP 1,000.00"], ["Saldo posterior a este cobro", "DOP 500.00"]]
    : [["Fondo inicial", "DOP 2,000.00"], ["Cobrado efectivo", "DOP 600.00"], ["Cobrado transferencia", "DOP 500.00"], ["Efectivo esperado", "DOP 2,600.00"], ["Efectivo contado", "DOP 2,600.00"], ["Diferencia", "DOP 0.00"]];
  return <div className="doc-design-preview-unit"><div className="doc-design-mode-label"><strong>{label}</strong><small>{bw ? "Grises suaves y poco tóner" : "Paleta de Atlas"}</small></div><div className="doc-design-paper-viewport"><article className={`doc-design-paper ${bw ? "doc-design-paper--bw" : ""} doc-design-paper--${definition.header_style}`} style={{ "--doc-accent": definition.accent_color, "--doc-zoom": zoom / 100, padding: `${definition.margin_mm + 7}px`, fontFamily: definition.typography === "Times-Roman" ? "Georgia, serif" : definition.typography === "Courier" ? "monospace" : "Arial, sans-serif" } as React.CSSProperties}>
    <header>{definition.show_logo && <span className="doc-design-paper-mark" aria-hidden="true">◇</span>}<div>{definition.show_logo && <strong>Atlas Pérgamo</strong>}{definition.show_organization && <small>Organización de muestra</small>}{definition.show_center && <small>Centro de muestra</small>}</div><div className="doc-design-paper-address">Documento de muestra<br />18/10/2026 10:00</div></header>
    <div className="doc-design-paper-title"><h3>{documents.find(item => item.kind === kind)?.label.toUpperCase()}</h3><strong>{kind === "invoice" ? "INT-1-00000001" : kind === "receipt" ? "PAGO-00000001" : "CAJA-00000001"}</strong></div>
    <div className={`doc-design-paper-section doc-design-paper-section--${definition.section_style}`}><strong>{kind === "cash_close" ? "Datos de la Caja" : "Datos del paciente"}</strong><p>{kind === "cash_close" ? "Responsable: Cajero de muestra" : "Paciente: Paciente de muestra"}</p><p>{kind === "invoice" ? "Concepto: Consulta de muestra" : kind === "receipt" ? "Factura: INT-1-00000001" : "Cierre: 18/10/2026 18:00"}</p></div>
    <div className={`doc-design-paper-section doc-design-paper-section--${definition.section_style}`}><strong>{kind === "receipt" ? "Pago recibido" : "Importes y desglose"}</strong>{rows.map(([title, value]) => <p key={title} className="doc-design-paper-row"><span>{title}</span><b>{value}</b></p>)}</div>
    <div className={`doc-design-paper-section doc-design-paper-section--${definition.section_style}`}><strong>{kind === "cash_close" ? "Movimientos" : "Detalles"}</strong><p>{kind === "cash_close" ? "#1 Efectivo · #2 Transferencia" : kind === "receipt" ? "Método: Efectivo · Caja #1" : "Métodos registrados: Efectivo"}</p></div>
    {definition.show_professional && <div className="doc-design-paper-signature">Usuario de muestra</div>}
    <footer>{definition.footer_note}<br /><strong>VISTA PREVIA · DATOS FICTICIOS</strong></footer>
  </article></div></div>;
}
