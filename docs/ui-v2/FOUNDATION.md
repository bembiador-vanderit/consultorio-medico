# Atlas Consultorio UI V2 — Fundación, fase 0

## Alcance y base aprobada

Base: `feat/complete-care-context`, SHA `44824b70fd8b6ececf79a5db44f8f77436b0b71b`.
Rama de trabajo: `frontend/ui-v2-foundation`. No fusionar sin revisión.
No se incorporó código de `frontend/design-system-phase-1`.

Esta fase entrega tokens, primitivas, shell y contratos. El shell se demuestra en
un catálogo de desarrollo; no reemplaza todavía el contenedor de `App.tsx`.
Login, páginas operativas, servicios, autenticación, reglas clínicas y backend
conservan su implementación. No hay migraciones ni persistencia de layouts.

## Inspección de la arquitectura existente

- React 18.3.1, TypeScript 5.6, Vite 6 y Tailwind 4 con `@tailwindcss/vite`.
  La instalación revisada resolvió Tailwind y su plugin a 4.3.3.
- No hay `tailwind.config.js`: la integración es CSS-first. No agregar configuración de Tailwind 3.
- `react-router-dom` está declarado, pero `App.tsx` navega con estado `view` y callbacks.
  Esta fase respeta ese mecanismo; no introduce un router paralelo.
- La sesión se restaura con `/auth/refresh` y `/auth/me`. El token de acceso vive
  en la configuración Axios, y las cookies se envían con `withCredentials`.
- `User.roles` contiene cadenas: `doctor`, `secretary`, `admin`, incluso combinaciones.
  El perfil incluye nombre y especialidades, pero no un centro activo ni capacidades granulares.
- Los componentes existentes (`NotificationBell`, formularios de pacientes,
  historial y órdenes clínicas) mezclan presentación con operaciones de dominio.
  Se conservan; no son sustituidos por componentes visuales sin sus reglas.
- Las pantallas usan utilidades Tailwind, formularios/modal inline y navegación
  vertical/horizontal adaptada mediante `sm`/`md`. La migración será progresiva.
- No había biblioteca de UI/iconos, tokens propios ni runner de pruebas frontend.
  Ahora `npm test` usa Node, Vite y React DOM ya instalados. No se agregaron paquetes.
- El repositorio no tiene lockfile. Las versiones resueltas pueden variar dentro
  de los rangos existentes; esta fase no cambia la política de dependencias.

## Principios visuales

Interfaz clínica, profesional y tranquila, con información legible y espacio eficiente.
Sin gradientes decorativos, fuentes externas, animación innecesaria ni modo oscuro.
Se conserva la pila `Inter, ui-sans-serif, system-ui, sans-serif`; Inter no se descarga.
Si no está instalada, se usa la fuente del sistema.

La paleta oficial vive exclusivamente en `frontend/src/ui/tokens.css`:

| Token | Valor |
| --- | --- |
| `--atlas-primary` | `#6FA8B8` |
| `--atlas-sage` | `#82B5A5` |
| `--atlas-sky` | `#A8C9D6` |
| `--atlas-mint` | `#D9EEE7` |
| `--atlas-amber` | `#F3D9A4` |
| `--atlas-coral` | `#E7A09A` |
| `--atlas-surface` | `#FCFDFD` |
| `--atlas-surface-secondary` | `#F1F5F6` |
| `--atlas-text-primary` | `#334E5A` |
| `--atlas-text-secondary` | `#75868D` |

El texto secundario oficial es decorativo: para texto pequeño se usa el derivado
`--atlas-text-muted`. Las acciones usan `--atlas-action`, texto inverso
`--atlas-on-action` y foco `--atlas-focus`. Los tonos success/warning/danger/info
emplean pares de primer plano/fondo contrastados. No usar blanco sobre Primary
para etiquetas pequeñas. Las pruebas calculan contraste mínimo 4.5:1 para los
pares de texto y 3:1 para límites de controles/foco sobre las superficies probadas.
Esto no equivale a certificar todas las combinaciones posibles ni toda la aplicación.

`@theme inline` publica aliases Tailwind 4 (`bg-atlas-surface`, `text-atlas-text`,
etc.). `foundation.css` contiene clases `atlas-*`; no se redefinen utilidades
ni estilos generales de las páginas existentes. Los componentes se usan bajo
`atlas-root` (incluido en el shell); los diálogos portados al body tienen su propio alcance.

## Tipografía, espaciado y geometría

| Nivel | Token | Tamaño |
| --- | --- | --- |
| Título de página | `--atlas-type-display` | 1.75rem |
| Sección | `--atlas-type-section` | 1.25rem |
| Tarjeta | `--atlas-type-card` | 1.0625rem |
| Cuerpo | `--atlas-type-body` | 1rem |
| Secundario / etiqueta | `--atlas-type-secondary`, `--atlas-type-label` | .875rem |
| Leyenda | `--atlas-type-caption` | .75rem |

Interlineado base: 1.5. Escala de espacio: .25, .5, .75, 1, 1.5 y 2rem.
Aliases de intención: `page-space`, `section-space`, `card-space`, `form-space`,
`table-space`, `module-space`. Radios: 6px para controles, 12px para tarjetas y
14px para modal. Bordes sutiles, sombras pequeñas y transición de 120ms solamente
en botones; spinner sin animación al solicitar movimiento reducido.

## Componentes y contratos de uso

Importar desde `frontend/src/ui/index.ts`.

| Familia | Componentes |
| --- | --- |
| Acciones | `Button`, `IconButton`, `ActionCard` |
| Contenedores | `Card` (estándar/compacta), `PageContainer`, `Stack`, `CardGrid` |
| Títulos | `PageHeader`, `SectionHeader` |
| Formularios | `FormField`, `FormSection`, `Input`, `Textarea`, `Select`, `Checkbox`, `Radio` |
| Estados | `StatusBadge`, `Alert`, `EmptyState`, `LoadingState`, `Spinner`, `Skeleton` |
| Interacción | `Modal`, `Drawer`, `Dropdown`, `Tooltip`, `Tabs` |
| Datos | `Table`, `TableColumn` |
| Separación | `Divider` |

Button: variantes primary/secondary/outline/ghost/danger; tamaños sm/md/lg.
Por defecto es `type="button"`; para enviar formularios declarar `type="submit"`.
Loading deshabilita la acción y presenta una etiqueta de progreso. La prevención
de duplicados a nivel negocio/servidor sigue siendo responsabilidad del consumidor.
IconButton exige `label`; los iconos decorativos se ocultan de lectores de pantalla.
ActionCard admite una sola acción y contenido de frase (span/texto), sin controles anidados.

```tsx
<FormField label="Nombre" required description="Ayuda breve" error={error}>
  <Input value={name} onChange={(event) => setName(event.target.value)} />
</FormField>
<StatusBadge tone="success">Completada</StatusBadge>
```

FormField genera ID y asocia etiqueta, ayuda, error y required mediante contexto.
Usar exactamente un Input/Textarea/Select de la fundación por campo. Si se proporciona
ID, hacerlo en FormField; este tiene prioridad sobre el ID del control.
Controles aislados necesitan su propia etiqueta. Checkbox/Radio incluyen etiqueta propia:
agrupar con FormSection/fieldset, no envolverlos en FormField. Los radio de un mismo
grupo comparten `name`. Validación y mensajes de negocio se reciben desde el consumidor;
`aria-invalid` no impide por sí mismo enviar un formulario.

Los textos genéricos predeterminados en español pueden reemplazarse mediante
`loadingLabel`, `requiredLabel`, `closeLabel`, `emptyTitle` y `emptyDescription`.

Modal/Drawer: API controlada `open`, `onClose`, `title`, `description`, `children`,
`footer`. Usan `dialog.showModal()`; fondo inerte, título enfocado al abrir, ciclo
de Tab explícito, Escape, cierre visible y restauración del foco al disparador.
Bloqueo de scroll compartido para overlays anidados. El body del panel desplaza;
cabecera y pie permanecen disponibles. No se cierra al pulsar el fondo para evitar
descartar formularios accidentalmente. El consumidor decide si puede cerrar mientras guarda.
Requiere navegador moderno con HTMLDialogElement; sin polyfill en esta fase.

Dropdown usa un disclosure nativo `details/summary` con botones normales: Tab,
Escape, cierre al salir del foco o pulsar fuera. No anuncia un ARIA menu ni promete
navegación con flechas. Tooltip es ayuda breve suplementaria con trigger propio;
admite foco, hover persistente sobre el contenido y Escape. No poner controles en la ayuda.
Tabs usa roving tabindex, flechas izquierda/derecha, Home/End y paneles asociados.
El consumidor debe pasar IDs únicos y un valor que identifique una pestaña habilitada.

Table recibe filas, columnas, rowKey, loading y estado vacío. Usa tabla HTML,
caption, th/scope, overflow horizontal y región enfocables. Acepta encabezados
React y `sortDirection` para una futura integración; no ordena, filtra ni consulta
datos por sí misma. Se debe proporcionar al menos una columna e IDs/claves estables.
Los estados muestran texto, no solamente color; el código de negocio elige el tono.

## Shell y navegación

`AtlasAppShell` compone `Sidebar`, `Topbar`, contenido `main` y Drawer de navegación.
Recibe usuario, vista activa, onNavigate, onSignOut, título y slots opcionales de
notificaciones/centro. No carga sesiones ni inventa datos del servidor.
El slot `notifications` permite reutilizar NotificationBell cuando se integre el shell.
`activeCenterName` solo debe pasarse desde un contexto real, no deducido de un rol.

`navigation/navigation.ts` centraliza IDs, etiqueta, vista, icono, grupo, orden y
visibilidad. `NavigationIcon` es un conjunto mínimo de SVG locales coherentes.
No hay emojis ni biblioteca adicional para navegación. Se usan botones porque las
vistas actuales se cambian por estado; una migración real a URLs deberá usar enlaces.

| Contexto actual | Elementos adicionales a Dashboard/Agenda/Reportes/Pacientes |
| --- | --- |
| Doctor | Seguimientos, Mi disponibilidad, Cobertura clínica |
| Secretary | Cobertura clínica |
| Admin | Usuarios y roles, Localidades y centros |

Combinaciones de roles reciben la unión. Roles desconocidos conservan los cuatro
elementos generales, como en App.tsx; una sesión ausente no recibe elementos.
Consulta se abre desde una cita y no se incorpora como destino global.
La discrepancia existente entre el callback de atención (doctor/admin) y el guard
de renderizado (doctor) no se cambia: revisar esa política pertenece al dominio.

`NavigationVisibilityResolver` es el punto futuro de adaptación a capacidades
reales del backend. No contiene una lista de permisos ficticios ni otorga acceso.
El servidor ya aplica permisos en endpoints; el perfil actual no los expone a este shell.
No convertir el rol en autorización universal ni usar el resolver de navegación
para decidir el acceso a datos clínicos.

En una futura integración, el adaptador onNavigate de Agenda debe conservar la
limpieza de `selectedAppointmentPatient`, y se deben mantener todos los callbacks,
guards y estados seleccionados del App actual. No reemplazar App con el catálogo.

## Workspace y personalización futura

`workspaces/contracts.ts` define workspaceId, moduleId, zone, order, visible,
layoutVersion, source y roleContext. Son exclusivamente metadatos de presentación.

```text
Atlas Default
    ↓
Organization Default (futuro)
    ↓
Center / Role Default (futuro)
    ↓
User Personal Layout (futuro)
```

No se ejecuta todavía un algoritmo de combinación ni se guarda en localStorage,
API o base de datos. Al crear el primer workspace real se definirán registros de
módulos/zonas válidos, migraciones de versión, reglas de override, validación,
restauración de defaults y persistencia. Width/height/collapsed/preferred size son
posibles extensiones, no contratos implementados. La capacidad administrativa para
layouts organizacionales queda pendiente.

Antes de renderizar un módulo, resolver acceso real y datos autorizados. Después
aplicar preferencias visuales. Un módulo oculto/reordenado nunca modifica derechos,
propiedad de datos ni estado de consulta. No persistir datos clínicos en un layout.

## Responsive y accesibilidad

Prioridad escritorio: sidebar de 16rem y contenido flexible desde 1024px. Por debajo,
trigger de navegación y Drawer; al volver a escritorio se cierra el Drawer. Formularios
y grids conservan dos columnas hasta 640px, luego una. Tablas desplazan dentro de su
región. Overlays limitados por viewport dinámico; en móvil el panel ocupa todo el ancho.
El sidebar colapsable de escritorio queda diferido.

Mantener foco visible, orden DOM coherente, landmarks, títulos jerárquicos, skip link,
etiquetas asociadas y acciones con texto explícito. Targets normales de 44px y botones
compactos de 40px. No eliminar outlines, usar div clicables, colocar texto claro sobre
fondos pálidos ni comunicar estados solo por color. Spinner anuncia texto de estado y
Skeleton es decorativo. Respetar movimiento reducido. La accesibilidad de pantallas
legacy se revisará cuando se migren; esta fase no las certifica.

## Revisión visual de Junior

Desde la rama `frontend/ui-v2-foundation`:

```sh
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5184 --strictPort
```

Abrir `http://127.0.0.1:5184/__dev/ui-v2`. No requiere backend ni login y no envía
datos. No introducir información real. En Docker, usar el puerto configurado del
frontend y la misma ruta. `npm run build` elimina el import del catálogo mediante
`import.meta.env.DEV`; en producción esa ruta cae en App y su login normal, no muestra
el catálogo ni el simulador de roles. No habilitarla con una variable VITE pública.

1. Colores y tipografía: revisar paleta, títulos, cuerpo y leyendas.
2. Componentes: botones/variantes/tamaños, loading/disabled, icono con nombre, ayuda,
   tarjetas, badges, estado vacío, carga, error y acceso restringido.
3. Abrir modal: Tab/Shift+Tab deben permanecer dentro; Escape/cierre devuelve el
   foco. Abrir panel, desplazarlo y abrir modal anidado; el fondo sigue bloqueado.
4. Más acciones: abrir con Enter/Espacio; recorrer con Tab; Escape cierra y restaura
   foco. Ayuda: foco/hover muestra, Escape oculta. Flechas/Home/End cambian pestañas.
5. Formularios y tabla: pulsar etiquetas, comprobar required nativo, ayuda/error,
   readonly/disabled, checkbox/radio y cambios entre tabla normal/vacía/cargando.
6. Alternar doctor/secretary/admin/combinado. Comparar navegación con la matriz;
   las acciones de navegación solo muestran una selección ficticia.
7. Revisar a 1440, 1024, 768 y 375/320px; abrir el menú responsive y confirmar
   que tablas desplazan internamente sin cortar formularios o acciones de cierre.
8. Verificar zoom 200%, navegación solo teclado y movimiento reducido en el
   navegador de uso real antes de aprobar la migración operativa.

## Validación y límites

```sh
cd frontend
npm test
npx tsc -b
npm run build
```

Las pruebas cubren combinaciones de roles, adaptación de visibilidad, asociaciones
de formularios, IDs únicos, carga de botones, labels de choices, tabla, tabs y contraste.
Son pruebas de lógica/renderizado de servidor; la interacción real de overlays y
responsive requiere la revisión de navegador descrita arriba.

Docker: `docker compose config -q` con variables de prueba y build de imágenes.
Backend sin cambios: ejecutar pytest en contenedor desechable de la imagen construida
con DATABASE_URL de SQLite de pruebas y SECRET_KEY efímera. No iniciar ni migrar la
base clínica para revisar componentes. Nunca ejecutar `docker compose down -v`.
La configuración CI actual solo se dispara automáticamente para main; no modificar
el destino del PR a main para activar CI. Resultados de esta entrega: ver VALIDATION.md.

## Regla para próximas sesiones Codex/Copilot

Toda fase futura de UI MUST reutilizar estos tokens, componentes y contratos.
No crear paletas, botones, tarjetas, espaciados ni sistemas visuales independientes
por página sin una razón arquitectónica explícita y documentada. Extender primero
la fundación con cambios pequeños y verificables. Conservar autorización backend,
visibilidad de pacientes, contexto inmutable, finalización, órdenes, PDFs y auditoría.

Quedan diferidos los rediseños completos de Login/Dashboard/Agenda/Pacientes/Consulta/
Administración, dashboards por rol, facturación/ARS/caja/e-CF, drag/drop, layouts
personalizados persistentes, permisos granulares nuevos, branding, diseñadores de
documentos/firmas/sellos, especialidad visual, modo oscuro e integraciones de dispositivos.
