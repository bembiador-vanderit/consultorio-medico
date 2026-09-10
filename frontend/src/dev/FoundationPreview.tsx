import { useState } from "react";
import { AtlasAppShell } from "../layouts/AtlasAppShell";
import type { AppView } from "../navigation/navigation";
import { ActionCard, Alert, Button, Card, CardGrid, Checkbox, Divider, Drawer, Dropdown, EmptyState, FormField, FormSection, IconButton, Input, LoadingState, Modal, PageContainer, PageHeader, Radio, SectionHeader, Select, Skeleton, Stack, StatusBadge, Table, Tabs, Textarea, Tooltip, type Tone } from "../ui";

const palette = [
  ["Primary", "primary"], ["Sage", "sage"], ["Sky", "sky"], ["Mint", "mint"], ["Amber", "amber"],
  ["Coral", "coral"], ["Fondo", "surface"], ["Superficie", "surface-secondary"], ["Texto", "text-primary"], ["Texto secundario decorativo", "text-secondary"],
];
const tones: Tone[] = ["neutral", "success", "warning", "danger", "info"];
const toneLabels = ["Sin iniciar", "Completada", "Pendiente", "Requiere revisión", "Información"];
const sampleRows = [
  { id: "M-001", name: "Módulo de ejemplo A", tone: "success" as Tone, state: "Disponible" },
  { id: "M-002", name: "Módulo de ejemplo B", tone: "warning" as Tone, state: "Pendiente" },
];

/** Loaded only behind import.meta.env.DEV. No API, session or patient data. */
export default function FoundationPreview() {
  const [role, setRole] = useState("doctor");
  const [view, setView] = useState<AppView>("dashboard");
  const [modal, setModal] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState("tokens");
  const [message, setMessage] = useState("");
  const [tableState, setTableState] = useState("ready");
  const user = { full_name: "Usuario de demostración", roles: role === "combined" ? ["doctor", "admin"] : [role] };
  return <AtlasAppShell user={user} activeView={view} pageTitle="Fundación UI V2" onNavigate={(next) => { setView(next); setMessage(`Vista de ejemplo seleccionada: ${next}`); }}
    onSignOut={() => setMessage("Demostración: aquí se conectará el cierre de sesión existente.")}>
    <PageContainer><Stack>
      <PageHeader eyebrow="ATLAS CONSULTORIO · UI V2 / FASE 0" title="Una base para cada flujo" description="Catálogo de desarrollo con datos ficticios. Los módulos operativos conservan su comportamiento."
        actions={<StatusBadge tone="info">Vista de desarrollo</StatusBadge>} />
      <Card compact><FormField label="Contexto de navegación de ejemplo" description="Cambia solo esta demostración; no modifica una cuenta ni sus permisos."><Select value={role} onChange={(event) => { setRole(event.target.value); setView("dashboard"); }}>
        <option value="doctor">Médico</option><option value="secretary">Secretaría</option><option value="admin">Administrador</option><option value="combined">Médico + administrador</option><option value="unknown">Rol desconocido (paridad actual)</option>
      </Select></FormField></Card>
      {message && <Alert title="Acción de demostración">{message}</Alert>}
      <Tabs label="Catálogo de la fundación" value={tab} onChange={setTab} items={[
        { id: "tokens", label: "Colores y tipografía", content: <Stack>
          <SectionHeader title="Paleta oficial" description="Los colores decorativos se complementan con tonos de texto y acciones de mayor contraste." />
          <div className="atlas-palette">{palette.map(([label, token]) => <div className="atlas-swatch" key={token}><div className="atlas-swatch-color" style={{ backgroundColor: `var(--atlas-${token})` }} /><p className="atlas-swatch-label">{label}<br />{`--atlas-${token}`}</p></div>)}</div>
          <Card><Stack><h2 className="atlas-page-title">Título de página</h2><h3 className="atlas-section-title">Título de sección</h3><p className="atlas-card-title">Título de tarjeta</p><p>Texto de lectura para el trabajo diario.</p><p className="atlas-help">Texto secundario con contraste reforzado.</p><p className="atlas-label">Etiqueta de formulario</p><p className="atlas-caption">Leyenda breve</p></Stack></Card>
        </Stack> },
        { id: "components", label: "Componentes", content: <Stack>
          <SectionHeader title="Acciones y estados" />
          <Card><Stack><div className="atlas-actions">{(["primary", "secondary", "outline", "ghost", "danger"] as const).map((variant, index) => <Button key={variant} variant={variant} onClick={() => setMessage(`Acción ${variant} revisada.`)}>{["Guardar", "Continuar", "Cancelar", "Ver detalles", "Eliminar ejemplo"][index]}</Button>)}</div>
            <div className="atlas-actions"><Button size="sm">Pequeño</Button><Button size="lg">Grande</Button><Button loading>Guardar</Button><Button disabled>Deshabilitado</Button><IconButton label="Agregar ejemplo" variant="outline" onClick={() => setMessage("Ejemplo agregado.")}>+</IconButton><Tooltip label="Ayuda complementaria visible con foco o puntero.">Ayuda</Tooltip></div>
            <div className="atlas-actions">{tones.map((tone, index) => <StatusBadge key={tone} tone={tone}>{toneLabels[index]}</StatusBadge>)}</div>
          </Stack></Card>
          <CardGrid><Card><h3 className="atlas-card-title">Tarjeta estándar</h3><p className="atlas-muted">Contenido agrupado con una jerarquía clara.</p></Card><ActionCard onClick={() => setModal(true)}><span className="atlas-card-title">Tarjeta interactiva</span><br /><span>Abrir el detalle de ejemplo</span></ActionCard></CardGrid>
          <CardGrid><Alert tone="danger" title="No se pudo completar la acción">Inténtalo de nuevo. No se muestra información técnica.</Alert><Alert tone="warning" title="Acceso restringido">Esta es una presentación visual; el servidor decide el acceso.</Alert></CardGrid>
          <CardGrid><Card><LoadingState /><Skeleton /><Divider /><p className="atlas-help">El esqueleto es decorativo; el estado de carga tiene una etiqueta accesible.</p></Card><Card><EmptyState title="Todavía no hay elementos" description="Los registros aparecerán aquí cuando estén disponibles." action={<Button variant="outline" onClick={() => setMessage("Acción del estado vacío revisada.")}>Crear ejemplo</Button>} /></Card></CardGrid>
          <div className="atlas-actions"><Button onClick={() => setModal(true)}>Abrir modal</Button><Button variant="outline" onClick={() => setDrawer(true)}>Abrir panel lateral</Button><Dropdown label="Más acciones" actions={[{ id: "details", label: "Ver detalle de ejemplo", onSelect: () => setModal(true) }, { id: "disabled", label: "Acción no disponible", disabled: true, onSelect: () => undefined }]} /></div>
        </Stack> },
        { id: "forms", label: "Formularios y tabla", content: <Stack>
          <form onSubmit={(event) => { event.preventDefault(); setMessage("Validación nativa completada. No se envió ningún dato."); }}><Stack><FormSection title="Campos de ejemplo" description="No introduzcas datos de pacientes.">
            <FormField label="Nombre del ejemplo" required description="Etiqueta vinculada automáticamente al control."><Input placeholder="Escribe un nombre ficticio" /></FormField>
            <FormField label="Campo con error" error="Revisa el valor de ejemplo."><Input defaultValue="Valor de demostración" /></FormField>
            <FormField label="Solo lectura"><Input readOnly value="Información de ejemplo" /></FormField><FormField label="Deshabilitado"><Input disabled value="No disponible" /></FormField>
            <FormField label="Categoría"><Select defaultValue="a"><option value="a">Ejemplo A</option><option value="b">Ejemplo B</option></Select></FormField>
            <FormField label="Descripción"><Textarea placeholder="Descripción del ejemplo" /></FormField>
          </FormSection><FormSection title="Opciones"><Checkbox label="Mostrar información complementaria" /><Checkbox disabled label="Opción no disponible" /><Radio name="density" value="standard" defaultChecked label="Densidad estándar" /><Radio name="density" value="compact" label="Densidad compacta" /></FormSection><div><Button type="submit">Validar ejemplo</Button></div></Stack></form>
          <SectionHeader title="Tabla base" description="El componente recibe datos y acciones; no consulta la API." />
          <FormField label="Estado de tabla"><Select value={tableState} onChange={(event) => setTableState(event.target.value)}><option value="ready">Con registros</option><option value="empty">Vacía</option><option value="loading">Cargando</option></Select></FormField>
          <Table caption="Módulos ficticios para revisión" rows={tableState === "empty" ? [] : sampleRows} rowKey={(row) => row.id} loading={tableState === "loading"} emptyDescription="No hay módulos de ejemplo en esta vista." columns={[
            { id: "id", header: "Código", render: (row) => row.id }, { id: "name", header: "Nombre del módulo", render: (row) => row.name },
            { id: "state", header: "Estado", render: (row) => <StatusBadge tone={row.tone}>{row.state}</StatusBadge> },
            { id: "actions", header: "Acciones", action: true, render: (row) => <Button variant="ghost" aria-label={`Ver ${row.name}`} onClick={() => setModal(true)}>Ver detalle</Button> },
          ]} />
        </Stack> },
      ]} />
    </Stack></PageContainer>
    <Modal open={modal} onClose={() => setModal(false)} title="Detalle de ejemplo" description="El foco permanece dentro del diálogo. Escape permite cerrarlo."
      footer={<Button variant="outline" onClick={() => setModal(false)}>Cerrar</Button>}><Stack><FormField label="Nombre del detalle"><Input defaultValue="Ejemplo de revisión" /></FormField><Alert title="Sin cambios operativos">Esta vista no guarda información.</Alert></Stack></Modal>
    <Drawer open={drawer} onClose={() => setDrawer(false)} title="Panel de ejemplo" description="Contenido contextual con desplazamiento independiente."
      footer={<Button variant="outline" onClick={() => setDrawer(false)}>Cerrar</Button>}><Stack><Button onClick={() => setModal(true)}>Abrir modal sobre el panel</Button>{Array.from({ length: 8 }, (_, index) => <Card compact key={index}><h3 className="atlas-card-title">Sección {index + 1}</h3><p>Contenido ficticio para comprobar el desplazamiento y la adaptación a pantallas pequeñas.</p></Card>)}</Stack></Drawer>
  </AtlasAppShell>;
}
