# Entrega y validación — UI V2

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
