# Entrega y validación — UI V2 fase 0

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
