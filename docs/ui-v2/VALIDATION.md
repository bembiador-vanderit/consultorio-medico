# Entrega y validación — UI V2

## PR #31 — Agenda unificada y aprovechamiento del viewport

Día, Semana, Mes y Médicos usan la misma semántica de color y tarjeta de cita:
hora, paciente, motivo resumido, especialidad y estado textual. Día es una agenda
`Hora | Cita`; Semana conserva su cuadrícula con eje de horas registradas; Mes
mantiene celdas uniformes y `+N más`; Médicos agrupa filas compactas por profesional.
Las listas de Semana y Mes, las citas directas de esas vistas y Médicos usan el
panel contextual para el detalle. Día mantiene un modal con botón Cerrar, botón X,
Escape, retorno de foco y cierre al pulsar el backdrop; un clic dentro del contenido
no lo cierra. El shell deja que Agenda use el ancho restante después de la barra
lateral; el calendario recupera espacio al cerrar el panel.

| Validación | Resultado |
| --- | --- |
| Pruebas específicas de Agenda en Docker Node 22/Linux | 53 aprobadas, 0 fallidas |
| Suite frontend completa en Docker Node 22/Linux | 94 aprobadas, 0 fallidas |
| TypeScript `tsc -b` | Correcto |
| Vite producción | Correcto |
| Navegador aislado — Semana | 1920×1200, 1440×1000, 1366×900, 1280×800, 1024×900, 768×900, 375×812 y 320×700 sin overflow horizontal; panel con scroll local |
| Interacción Día | Cierre por backdrop, botón Cerrar y Escape; clic interno no cierra, foco vuelve a la cita y no se recarga la Agenda |
| Navegador aislado — Día y Médicos | 1920×1200 y 1280×800 sin overflow horizontal; Día usa modal y Médicos panel local |

En 1920×1200 el espacio útil de Semana fue 1664 px: la cuadrícula midió 1376 px
sin panel y 992 px con panel de 360 px; al cerrarlo volvió a 1376 px. En 1280×800
la cuadrícula permaneció dentro de 736 px y no introdujo barra horizontal de página.
El panel mantiene scroll local; en tablet/móvil se apila bajo el calendario.

No se modificaron backend, contratos, migraciones ni datos clínicos.

## Fase 3 — Dashboards por rol

Rama `frontend/ui-v2-role-dashboards`; base exacta
`1e8ee60f5d3fe5833f711818b03e6b449d2adf3a` de `feat/complete-care-context`.
La composición, datos reales, límites y prueba local están documentados en
[DASHBOARDS.md](DASHBOARDS.md).

| Validación | Resultado |
| --- | --- |
| Frontend Node/Vite/jsdom | 41 aprobadas, 0 fallidas: App Shell 14, Dashboard 6, Login 12 y Foundation 9 |
| TypeScript `tsc -b` | Correcto |
| Vite producción | Correcto |
| Backend | Sin cambios; no corresponde ejecutar pruebas backend por esta fase |
| Docker Compose build frontend | Correcto, imagen `atlas-ui-v2-dashboard-validation-frontend` |

Las pruebas específicas cubren Médico, Secretaría, Administrador, Médico +
Administrador, especialidades múltiples, estados de carga/vacío/error y navegación
de acciones dentro del App Shell. Secretaría y Administrador no reciben bloques
clínicos por la mera visibilidad del Dashboard.

La validación frontend enumeró los cuatro archivos de prueba explícitamente por una
limitación de expansión de comodines del PowerShell actual. No se alteró el backend,
las migraciones, datos clínicos ni volúmenes. El build Compose usó variables efímeras
y un proyecto de validación aislado; no inició servicios ni ejecutó
`docker compose down -v`.

## Fase 2 — App Shell operativo

Rama `frontend/ui-v2-app-shell`; base exacta
`553af16c1ffab4c216defb0733035cb3f75c225c` de `feat/complete-care-context`.
Arquitectura, roles, accesibilidad, límites e instrucciones locales en
[APP_SHELL.md](APP_SHELL.md).

| Validación | Resultado |
| --- | --- |
| Frontend Node/Vite/jsdom | 35 aprobadas, 0 fallidas: 14 nuevas del shell, 12 login y 9 fundación |
| TypeScript `tsc -b` | Correcto |
| Vite producción | Correcto; 116 módulos, CSS 49.04 kB (10.14 kB gzip), JS 390.02 kB (108.42 kB gzip) |
| Backend autorización/auth | 19 aprobadas: security, user_management y clinical_permissions; backend sin cambios |
| Docker Compose build frontend | Correcto, imagen `atlas-ui-v2-shell-validation-frontend` |
| Navegador autenticado aislado | Doctor, Secretaría y Administrador; login, F5, logout, roles, notificaciones y destinos reales comprobados |
| Responsive | 320, 375, 768, 1024 y 1440px sin overflow horizontal del shell; drawer y panel de notificaciones comprobados |
| Catálogo | `/__dev/ui-v2` sigue disponible en desarrollo |

La prueba de navegador usa un backend FastAPI aislado con SQLite temporal, cuentas
y aviso ficticios creados solo para validación. Usa los endpoints reales de login,
refresh, perfil, notificaciones y logout; no tocó PostgreSQL ni las cuentas del
entorno existente. El shell fue revisado en el App autenticado, no en el catálogo.

Las pruebas frontend cubren Doctor, Secretaría, Administrador, todas las
combinaciones soportadas, rol inesperado, Login sin sesión, restauración, logout,
estado activo, cambio de vista, Pacientes → Agenda, NotificationBell y drawer
móvil. Se desactivó el WebSocket de los servidores Vite de prueba porque el runner
ejecuta varios servidores en el mismo proceso; no afecta el servidor de desarrollo
ni producción.

La construcción Compose se ejecutó con un nombre de proyecto de validación y
variables efímeras, sin iniciar el stack ni ejecutar `docker compose down -v`.
No se modificó backend, migraciones, datos clínicos o volúmenes. Los tests backend
registraron 87 warnings existentes de Starlette/SQLAlchemy y caché de pytest en
montaje de solo lectura, sin fallos.

## Fase 1 — Login real

### Corrección visual de PR #26

Tarjeta clínica dividida 40/60 desde 900px, banner compacto por debajo de ese
ancho. Visual CSS original sin imágenes externas. Autenticación y backend sin
cambios; en la prueba versionada solo cambia el título esperado.

- 21 pruebas aprobadas al reanudar: mismas aserciones y servicios, mediante copias
  temporales con `configFile: false` en el servidor Vite de tests. El cargador
  habitual encontró acceso denegado al recorrer directorios superiores en el
  entorno restringido; ese ajuste de ejecución no se incorpora al repositorio.
- TypeScript `tsc -b`: correcto.
- Vite producción con `--configLoader native`: correcto, 112 módulos;
  CSS 47.64 kB y JS 386.01 kB (106.46 kB gzip). Esta opción evita empaquetar la
  configuración con esbuild bajo las restricciones del entorno.
- Navegador: 320/375/768/1024/1440px sin overflow horizontal; capturas desktop y
  móvil de la entrada real. Se revisó el build conservado, cuyos nombres de
  assets coinciden con los de la nueva compilación.
- Docker: build iniciado antes de una interrupción; resultado no recuperable.
  La repetición quedó bloqueada por acceso denegado a Docker Engine. No se declara
  validación Docker aprobada para esta corrección. Los resultados anteriores de
  Docker que siguen abajo corresponden a la entrega funcional inicial.

### Validación de la entrega funcional inicial

Rama `frontend/ui-v2-login`; base exacta
`30f5efe429ed630da8a8806c5b67ce10ba00b48e` de `feat/complete-care-context`.
Diseño, contrato preservado, alcance y acceso local en [LOGIN.md](LOGIN.md).

| Validación | Resultado |
| --- | --- |
| Frontend Node/Vite/jsdom | 21 aprobadas, 0 fallidas: 12 nuevas de login y 9 de fundación |
| TypeScript `tsc -b` | Correcto |
| Vite producción | Correcto; 112 módulos, JS 385.49 kB (106.32 kB gzip) |
| Backend/auth | 19 aprobadas: security, user_management y clinical_permissions |
| Navegador | Ruta real `/`, contraseña, Enter y alerta de conexión revisados |
| Responsive | 320, 375, 768, 1024 y 1440px sin overflow horizontal; controles 44/48px |
| Catálogo | `/__dev/ui-v2` sigue accesible en desarrollo |
| Bundle de producción | Sin `FoundationPreview`, texto de catálogo ni `/__dev/ui-v2` en JS inspeccionado |
| Docker Compose build frontend | Correcto, imagen `atlas-ui-v2-login-validation-frontend` |
| Tests en Docker Node 22/Linux | 21 aprobadas, 0 fallidas |
| TypeScript y Vite en Docker | Correctos; mismos assets y tamaños que en Windows |

Backend ejecutado en la imagen de validación de la base aprobada (backend sin
cambios), con SQLite y SECRET_KEY efímera, mediante `docker run --rm`. Se observaron
85 warnings de deprecación existentes (Starlette y datetime.utcnow); ningún fallo.
No se tocaron bases clínicas ni volúmenes persistentes.

Compose construyó únicamente frontend en un proyecto de validación separado, con
variables efímeras para resolver la configuración. No se levantó el stack ni se
ejecutó `docker compose down -v`. La instalación npm en la imagen informó cero
vulnerabilidades y una deprecación transitiva de `whatwg-encoding` de jsdom.
El workflow existente `Compose validation` solo se dispara automáticamente para
push/PR hacia `main`; esta PR apunta a `feat/complete-care-context`, por lo que no
se cambia su destino ni el workflow para activar CI.

La integración frontend usa un adaptador Axios de prueba; se comprueban JSON,
secuencia login/me, bearer, limpieza ante fallo, restauración y logout. La revisión
visual usa la entrada operativa, sin backend autenticado en ese puerto. No representa
una prueba E2E de cookies ni una auditoría de lector de pantalla/multinavegador.

## Registro histórico — fase 0

Fecha: 10 de septiembre de 2026. Rama: `frontend/ui-v2-foundation`.
Base confirmada por fetch y consulta remota:
`44824b70fd8b6ececf79a5db44f8f77436b0b71b` (`feat/complete-care-context`).
El SHA final y los commits se reportan en la entrega/PR; no se fusionó la rama.

## Resultados ejecutados

| Validación | Resultado |
| --- | --- |
| TypeScript 5.6 (`tsc -b`) | Correcto en Windows y dentro de Docker |
| Vite 6.4.3, producción | Correcto; 102 módulos, JS 381.53 kB (104.99 kB gzip) |
| Pruebas frontend Node/Vite | 9 aprobadas, 0 fallidas; también ejecutadas en Node 22/Linux de Docker |
| Contraste | Pares semánticos de texto ≥4.5:1 y controles/foco ≥3:1 comprobados por prueba |
| Catálogo en producción | No aparecen `FoundationPreview`, simulador de roles ni ruta de catálogo en los bundles JS inspeccionados |
| Pruebas backend | 168 aprobadas, 0 fallidas, en imagen construida desde esta base; 209.04 s |
| Docker Compose 5.3.1 `config -q` | Correcto con variables efímeras de prueba |
| Docker Compose build backend/frontend | Correcto; frontend validado con exclusión de dependencias locales |
| Navegador | Catálogo, formularios, roles, overlays y responsive revisados; sin errores/warnings en la consola consultada |
| Diff | Sin cambios en backend, App.tsx, páginas operativas ni servicios; `git diff --check` correcto |

La ejecución backend usó `docker run --rm`, `DATABASE_URL=sqlite://` y una SECRET_KEY
efímera enviada por entorno. Los tests existentes crean sus datos ficticios. Se
registraron 2814 advertencias de deprecación existentes (datetime.utcnow, ReportLab,
Starlette); no hubo fallos. No se modificó backend para silenciarlas.

La validación final del frontend en contenedor montó `src` y `tests` en solo lectura
sobre la imagen construida y ejecutó `npm test` y `npm run build`, comprobando las
fuentes finales con dependencias Linux. No se levantó un stack clínico, no se ejecutaron
migraciones contra una instalación real y no se tocaron volúmenes persistentes.
No se ejecutó `docker compose down -v`.

Hallazgos corregidos durante la validación:

- El primer par informativo sobre Sky daba 4.01:1; se oscureció `--atlas-info`
  conservando Sky oficial, y la prueba pasó.
- Se reforzó Tab/Shift+Tab del diálogo para mantener el ciclo dentro de sus controles.
- El max-width predeterminado del navegador limitaba el panel móvil; se ajustó a 100vw.
- El primer build Docker intentó copiar node_modules de Windows sobre las dependencias
  Linux. `frontend/.dockerignore` lo evita; la repetición construyó correctamente.
- El runner SSR podía cerrar Vite durante un escaneo de dependencias del navegador.
  Se desactivó ese escaneo solo en tests; la ejecución final pasó sin ese error.

## Revisión en navegador ejecutada

- Paleta, tipografía, tarjetas, botones, estados, modal y formularios inspeccionados visualmente.
- Modal: título enfocado al abrir, Tab del último control al primero, Shift+Tab inverso,
  Escape, foco devuelto al botón de apertura y restauración del scroll.
- Panel con modal anidado: dos diálogos abiertos; cerrar el superior conserva bloqueo
  de scroll y devuelve foco al disparador dentro del panel.
- Formularios: todos los controles visibles tienen etiqueta asociada; error expone
  aria-invalid; envío ficticio mediante validación nativa, sin API.
- Tabla: estados con registros, vacío y cargando comprobados.
- Flecha izquierda cambia de pestaña; tooltip se muestra con foco y cierra con Escape;
  disclosure de acciones cierra con Escape y restaura foco.
- Contextos doctor, secretary y admin comparados con la matriz de navegación existente.
  Las ocho combinaciones de roles están cubiertas además por pruebas automáticas.
- Viewports 375×812, 768×1024, 1440×900 y 320×720; sin overflow horizontal de la página
  en las comprobaciones. Formularios a dos columnas en tablet/escritorio y una en móvil.
- Navegación móvil abre panel, seleccionar Agenda lo cierra, volver a escritorio lo
  cierra automáticamente. Panel de 320px ocupa exactamente el ancho de 320px.

No se ejecutó una auditoría con lector de pantalla, zoom 200% ni una matriz de
navegadores. Esas comprobaciones manuales quedan indicadas para Junior. Esta entrega
no certifica las páginas legacy ni representa pruebas E2E de los flujos clínicos.

## Inventario de archivos

Creado:

- `frontend/.dockerignore`
- `frontend/src/ui/tokens.css`
- `frontend/src/ui/foundation.css`
- `frontend/src/ui/primitives.tsx`
- `frontend/src/ui/forms.tsx`
- `frontend/src/ui/overlays.tsx`
- `frontend/src/ui/data.tsx`
- `frontend/src/ui/index.ts`
- `frontend/src/layouts/AtlasAppShell.tsx`
- `frontend/src/layouts/NavigationIcon.tsx`
- `frontend/src/navigation/navigation.ts`
- `frontend/src/workspaces/contracts.ts`
- `frontend/src/dev/FoundationPreview.tsx`
- `frontend/tests/foundation.test.mjs`
- `docs/ui-v2/FOUNDATION.md`
- `docs/ui-v2/VALIDATION.md`

Modificado:

- `frontend/src/index.css`: imports de tokens y clases aisladas.
- `frontend/src/main.tsx`: import lazy del catálogo únicamente en desarrollo.
- `frontend/package.json`: script `test`; dependencias intactas.
- `README.md`: enlace a la fundación.

Archivos versionados eliminados: ninguno. Dependencias añadidas/eliminadas: ninguna.
No se incluyeron lockfiles nuevos, paquetes de iconos, fuentes externas ni dnd-kit.

## Alcance entregado y diferido

La arquitectura de tokens, componentes, shell, navegación, accesibilidad, responsive
y contratos de personalización se detalla en [FOUNDATION.md](FOUNDATION.md).

El shell permanece en la demostración porque App.tsx concentra sesión, navegación,
selección de citas/pacientes y guards clínicos. Esa separación permite revisar la base
sin introducir una migración operativa antes de aprobarla. No hay navegación demo
expuesta en producción.

Se difieren la integración del shell en App, los rediseños operativos completos,
dashboard por rol, personalización persistente, drag/drop, permisos nuevos,
facturación/ARS y demás módulos fuera de alcance. El sidebar colapsable de escritorio
y la compatibilidad con navegadores sin dialog nativo no se implementan en esta fase.

## Acceso para Junior

```sh
git switch frontend/ui-v2-foundation
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5184 --strictPort
```

Abrir `http://127.0.0.1:5184/__dev/ui-v2` y seguir los ocho pasos de revisión visual
en [FOUNDATION.md](FOUNDATION.md#revisión-visual-de-junior). El catálogo funciona sin
cuenta ni backend y solo usa ejemplos ficticios. Su presencia no habilita permisos.

Esperar revisión. No fusionar ni cambiar el destino a main para activar CI.

## Fase 4A — Agenda profesional

Rama `frontend/ui-v2-agenda-phase-4a`; base exacta
`eda6d7bdfb593d590f5fa469f393ba3a0a6f2d4c` de `feat/complete-care-context`.
La arquitectura, alcance real y límites están documentados en [AGENDA.md](AGENDA.md).

| Validación | Resultado |
| --- | --- |
| Frontend Node/Vite/jsdom | 57 aprobadas, 0 fallidas: Agenda 16, App Shell 14, Dashboard 6, Login 12 y Foundation 9 |
| TypeScript `tsc -b` y Vite producción | Correctos |
| Backend | Sin cambios; no corresponde ejecutar pruebas backend |

La fase introduce las vistas Día, Semana y Médicos, navegación por mini calendario,
filtros sobre datos autorizados, drawer accesible, formulario existente integrado y
acciones que reutilizan endpoints existentes. No incluye vista Mes, duración,
intervalos, slots ni disponibilidad horaria.

## PR #31 — correcciones pre-merge

Validación ejecutada sobre la corrección, en una copia aislada de
`frontend/ui-v2-agenda-phase-4a`, con Node 22 en contenedor:

| Validación | Resultado |
| --- | --- |
| Agenda: `node --test tests/agenda.test.mjs tests/agenda-ui.test.mjs` | 42 passed / 0 failed |
| Suite frontend: `npm test` | 83 passed / 0 failed |
| TypeScript: `tsc -b` | PASS |
| Producción: `npm run build` (`tsc -b && vite build`) | PASS |
| `docker compose -p atlas-pr31-fixes config -q` | PASS, variables efímeras de validación, sin levantar backend/DB |
| `docker compose -p atlas-pr31-fixes build frontend` | PASS; imagen aislada, sin modificar servicios existentes |
| Edge headless, tres vistas a 320/375/768/1024/1440 px | 15 casos PASS: sin overflow de página/contenedor, estados visibles, Drawer dentro del viewport, Escape y retorno de foco |

Las pruebas nuevas verifican parámetros y cantidades de GET, crear/editar,
refresco en la misma semana, reprogramación en Médicos, respuestas/errores fuera
de orden, payloads de Confirmar/Cancelar/no_show, restricciones de historia,
cobertura, médico puro y multirol, errores dentro del Drawer, filtros combinados
y reconciliados, homónimos, especialidades por cita, cinco etiquetas de estado,
IDs y labels, DELETE y apertura/guardado de la nota adicional existente.
El test del Shell valida la limpieza del paciente también fuera de `main`, donde
vive el portal del formulario.

Los datos del navegador fueron ficticios, con API interceptada; esa comprobación
valida layout e interacción, no reemplaza una prueba integrada de permisos con
backend. La disponibilidad diaria y el intervalo de cobertura continúan siendo
validados por los endpoints existentes.

El workflow existente solo escucha push y pull_request hacia `main`, además de
workflow_dispatch. Un push de esta rama y este PR hacia
`feat/complete-care-context` no cumple esos disparadores. No se cambia el workflow
ni la base del PR para activar CI.

## Pacientes UI V2 — fase 5, misión 3

Base exacta: `feat/complete-care-context@5012dfce894b63710745246d6d634c15b75bb078`.

| Validación | Resultado |
| --- | --- |
| Suite frontend completa, Node 22 en Docker, ejecución secuencial | 129 passed / 0 failed / 0 skipped |
| Patients UI nuevos | 29 casos incluidos en la suite completa |
| patient-selection-contract | 2 casos incluidos; prueba firmada conservada y enviada a citas |
| api-routing nuevos | 4 passed específicos y en suite completa; ruta relativa, override, reenvío de query/auth/cookies |
| Agenda y App Shell | Incluidos en suite completa; selección en Patients antes de Agendar y navegación preservada |
| TypeScript + Vite build | PASS, 129 módulos, ejecutado dentro de la imagen frontend |
| Docker frontend | PASS, imagen aislada atlas-patients-v2-frontend |
| Compose config -q | PASS, archivo de variables ficticias; sin iniciar ni migrar backend/DB |
| Edge headless, ocho resoluciones | PASS, lista/ficha, seguro, historia y formulario; sin overflow horizontal de página o modal activo |
| Desktop/tablet desde 640px | PASS, altura de página igual al viewport, scroll local |
| 1920×1200 | Área master/detail de 1632px, a 16px del Sidebar; aprovecha ancho restante |
| 1280×800 | Master/detail de 992px; acciones visibles incluso con identidad/contacto extensos |
| Acceso localhost / IP local de la PC | PASS desde la misma PC en preview, llamadas al origen elegido |
| Selección / Seguro | Cero requests al seleccionar; una consulta de seguro al paciente elegido por apertura; sin N+1 |
| Cierres/foco | Escape y cierres accesibles; Seguro retorna foco a su botón, Drawer retorna a la fila |
| Backend y reglas de autorización | Sin diff respecto a la base; CORS permanece intacto |

Resoluciones: 1920×1200, 1440×1000, 1366×900, 1280×800, 1024×900,
768×900, 375×812 y 320×700. En móvil se permite desplazamiento vertical
natural de la lista; detalles/formularios tienen scroll interno y cierre disponible.

Las regresiones cubren render, loading/empty/error/no resultados, búsqueda/limpiar,
respuestas fuera de orden, selección/ficha/edad, roles simples y múltiples,
Historia solo por doctor, Seguro bajo demanda, alta/edición/agendar, prueba de
selección, 409 y campos conservados, omisión de seguro tras error de lectura,
false explícito, actualización explícita, guardando, labels/IDs, cierre/foco y
ordenamiento local sin requests adicionales.

Las capturas usan fixtures ficticios y API interceptada; la comprobación HTTP de
reenvío usa un backend ficticio en loopback y verifica Authorization y cookies.
No representa una certificación de permisos ni de conectividad/firewall desde
otro dispositivo. No se alteraron servicios operativos ni datos clínicos.

El bundle usa /api/v1 en el mismo origen; Vite dev/preview y la configuración del
frontend Docker reenvían al backend. Un servidor estático diferente debe configurar
ese reenvío. VITE_API_URL explícito mantiene el modo de API separada.

Diseño, roles y deuda futura: [PATIENTS.md](PATIENTS.md).

## Corrección visual conjunta — mismo PR #33

Dashboard, Pacientes, Agenda y App Shell revisados contra la composición Atlas
aprobada. No se añade una paleta, backend, permiso ni endpoint paralelo.

| Validación | Resultado |
| --- | --- |
| Frontend completo, Node 22 Docker, secuencial | 142 passed / 0 failed / 0 skipped |
| Dashboard | 14 casos: roles, prioridades, multi-role, especialidades, fuentes reales, vacíos/errores, acciones, Nueva cita, expansión móvil y ausencia de cargas extra |
| Shell | Navegación inferior, Inicio activo, Más según rol, vista única, cuenta/Escape/logout, foco y transición desktop |
| Agenda | Modal de Día y contexto preservados; Semana móvil sin duplicar citas, filtros desplegables, mismo Drawer Mes para lista/detalle/volver/Escape/foco |
| Pacientes/contrato/API | 29 casos Patients, 2 selection-contract y 4 routing, incluidos en suite completa |
| TypeScript + Vite | PASS, 130 módulos; CSS 90.22 kB y JS 421.47 kB antes de gzip |
| Docker build / Compose config -q | PASS, imagen preview aislada y variables ficticias |
| Edge headless, cuatro módulos × ocho tamaños | PASS, sin overflow horizontal de página o módulo activo |
| Topbar / bottom navigation | 64px desktop/tablet, 56px móvil; barra inferior visible y margen final reservado |
| Dashboard 320px | Cuatro accesos principales 2×2, métricas en dos columnas y resumen visible en viewport inicial |
| Agenda desktop | Semana completa visible con eje horario y tarjetas delimitadas; sin scroll horizontal ni vertical de página como mecanismo normal |
| Pacientes desktop/tablet | Altura de página igual al viewport, scroll local y cuatro acciones de médico visibles |
| Requests | Una carga principal Patients, cero al seleccionar; seguro bajo demanda; abrir cuenta/expandir accesos/filtros/cerrar modal no añade recargas |
| Datos/autorización/backend | Contratos y guards conservados, backend sin diff; pruebas UI con fixtures ficticios |

Tamaños: 1920×1200, 1440×1000, 1366×900, 1280×800, 1024×900,
768×900, 375×812 y 320×700. En móvil, listas principales permiten scroll
vertical natural; modales/Drawers usan scroll interno. El panel de lista/detalle
de Agenda queda en el mismo Drawer; Día sigue siendo Modal.

Se verificaron también los Dashboard de Secretaría y Admin a 375px. Las fuentes
de notificaciones de campana y Dashboard conservan sus dos cargas independientes
previas; no se añade polling ni N+1. No se reconstruyó ni reinició la instalación
operativa. La comprobación visual no certifica permisos contra una base real.

Documentación de presentación vigente: [Dashboard](DASHBOARDS.md),
[App Shell](APP_SHELL.md), [Pacientes](PATIENTS.md) y [Agenda](AGENDA.md).


## PR #33 — misión 3C, polish final

- Frontend completo en Node 22/Docker: **149 passed, 0 failed, 0 skipped**;
  conserva los 142 casos previos y agrega siete. La versión final también
  reutiliza el badge global en Reportes sin alterar filtros, exportaciones o API.
- TypeScript + Vite: **PASS**, 130 módulos. Docker frontend build: **PASS**.
  Compose config con variables ficticias: **PASS**.
- Edge headless con API interceptada: **PASS** en 1920×1200, 1440×1000,
  1366×900, 1280×800, 1024×900, 768×900, 375×812 y 320×700.
  Cero overflow horizontal de página/dialog activo. Estados reales visibles en
  Semana 1280; ancho de ficha 34–40% y correo inicialmente visible desde 1280;
  título móvil sin borde/outline y acciones visibles; navegación inferior,
  Más/retorno de foco, Modal de Día y Drawer de Mes conservados.
- Adicional: especialidad de nombre extenso en Dashboard en 1920, 1280, 375 y
  320px: **PASS**, sin overflow horizontal. Nombres/correos/motivos extensos,
  badges, formularios, Drawer y barra inferior se comprobaron en la matriz.
- Palette global única: Programada azul, Confirmada verde, Completada teal,
  Cancelada coral, No asistió slate fuerte; contraste texto/fondo >=4.5:1.
- Capturas nuevas fuera de Git: Dashboard 1920/320, Pacientes 1280/320,
  Semana 1280 con los cinco estados, Día 375 y leyenda específica de estados,
  además de las otras resoluciones y Reportes 1280.
- No modifica backend, API proxy/routing, Docker proxy, permisos, seguridad,
  patient selection proof, insurance omission semantics ni reglas de citas.
  Instalación operativa sin reconstrucción/reinicio; datos de QA ficticios.

## PR #33 — misión 3D, ajustes finales

- Frontend completo: **149 passed, 0 failed, 0 skipped**. Se actualiza el
  contrato visual existente para ancho/márgenes/columnas y tipografía; no se
  elimina ninguna prueba. TypeScript + Vite, Docker frontend y Compose: **PASS**.
- Chrome con perfil temporal aislado y API interceptada: Pacientes 320×700 y
  375×812; Agenda Día/Semana 1280×800 a 100%, 75% y 50%, y 1920×1080 a 100%:
  **PASS**. Zoom nativo del navegador, verificado mediante getDefaultZoom,
  devicePixelRatio y viewport CSS (2560×1600 a 50% para captura física 1280×800).
- Geometría comprobada con bounding boxes: primarias a ancho completo,
  secundarias en la misma fila/anchos iguales/gap 8px, cero márgenes accidentales,
  cuatro acciones visibles y alturas >=44px en los dos móviles.
- Etiquetas de Día/Semana: 13–14.4px CSS, peso 700; sin recorte horizontal ni
  vertical en los casos probados. Tarjetas semanales <=76px, sin aumentar altura.
  Cero overflow horizontal de página/dialog activo.
- Capturas nuevas exclusivamente de Pacientes y Agenda, fuera de Git. No se
  modifica Dashboard, navegación móvil, mapping/paleta, API, backend ni permisos.
