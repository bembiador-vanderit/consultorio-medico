# Phase 6B9 — hardening de Consulta V2

## Alcance

Esta fase endurece el flujo existente de Consulta V2 sin agregar campos médicos, plantillas por especialidad ni persistencia local de borradores. Conserva `expected_revision`, la inmutabilidad posterior al cierre, el alcance clínico y las escrituras adicionales ya autorizadas.

## Auditoría inicial

| Módulo | Borrador local | Guardado | Conflicto o error | Riesgo encontrado |
| --- | --- | --- | --- | --- |
| Anamnesis | Formulario completo | `createHistory` / `updateHistory` | `expected_revision` puede devolver 409 | No informaba cambios pendientes al workspace |
| Signos vitales | Valores numéricos como texto | `saveVitalSigns` | Conservaba formulario ante error | El indicador “Guardados” no distinguía una edición posterior |
| Diagnósticos | Descripción, CIE-10 y principal | Creación explícita | Conservaba compositor ante error | El compositor podía perderse al navegar |
| Recetas | Alta o edición de ocho campos | Crear o actualizar | Conservaba editor ante error | Abrir edición y modificar no se registraba globalmente |
| Órdenes | Compositor, selecciones, detalles y notas | Crear o actualizar | Conservaba editor ante error | No participaba en navegación segura y repetía catálogos |
| Solicitudes heredadas | No tiene editor activo | Solo lectura/PDF | No aplica | No necesita dirty-state |

`ConsultationWorkspace` ya protegía la generación de lecturas históricas. `useConsultationBootstrap` protegía el cambio de cita, pero no exponía una recarga explícita del episodio. `App` tampoco ofrecía un guard temporal de navegación.

## Arquitectura de cambios pendientes

`useConsultationDirtyState` mantiene en memoria un `Set<DirtySection>` con `anamnesis`, `vital-signs`, `diagnoses`, `prescriptions` y `orders`. Cada editor informa su transición de forma explícita; no se inspecciona el DOM.

- Anamnesis y signos vitales comparan el borrador con la última versión cargada o guardada.
- Diagnósticos informa los cambios del compositor y queda limpio después de una creación confirmada.
- Recetas compara el formulario con el estado vacío o con la receta que comenzó a editarse.
- Órdenes permanece pendiente mientras un compositor está abierto; cancelar o guardar correctamente lo limpia.
- Un error de servidor conserva tanto el borrador como el estado pendiente.
- Cambiar de episodio reinicia el registro y los editores reciben únicamente los datos de la cita activa.

El estado no se guarda en `localStorage`, `sessionStorage`, URLs ni logs.

## Navegación segura

Consulta registra temporalmente un guard genérico en `App`. La navegación principal, las notificaciones y el cierre de sesión consultan ese guard sin conocer detalles clínicos. El botón **Volver a la agenda** usa la misma decisión.

Cuando existen cambios pendientes se ofrece permanecer o salir sin guardar mediante la confirmación del navegador. `beforeunload` se instala únicamente mientras el conjunto tenga elementos y se retira al quedar limpio o desmontarse la vista. **Finalizar consulta** permanece deshabilitado y explica que primero deben guardarse o descartarse los cambios.

## Conflicto de revisión

El backend sigue siendo la autoridad y mantiene `expected_revision`. Solo el 409 con el mensaje estable de revisión obsoleta activa el banner de conflicto; otros 409 conservan su mensaje clínico específico.

El banner informa que:

- el servidor no guardó el borrador;
- los valores locales continúan visibles;
- Atlas no reintentará automáticamente.

**Recargar versión del servidor** pide confirmación antes de descartar, vuelve a solicitar el contexto y los recursos activos, adopta la nueva revisión y reinicia los editores solo después de una carga exitosa. **Continuar revisando mis cambios** cierra el aviso sin tocar el borrador. No existe merge automático.

## Lifecycle y rendimiento

`useConsultationBootstrap` expone `reload()` y conserva un único `AbortController` y un número de generación. Una recarga o cambio de cita aborta la lectura anterior; una respuesta obsoleta no puede publicarse. Durante una recarga se mantiene visible el borrador hasta conocer el resultado, evitando perderlo si la lectura falla.

Órdenes reutiliza la caché de catálogos de `clinicalApi`; las listas propias del episodio siguen siendo lecturas cancelables. Los PDFs revocan su URL temporal inmediatamente después de iniciar la descarga. No se añadieron memoizaciones generales ni bloqueos globales para guardados independientes.

## Accesibilidad

- Errores y conflicto usan `role="alert"`.
- Guardados, recarga y conteo de secciones pendientes se anuncian con regiones de estado.
- Los módulos comunican `aria-busy` durante operaciones relevantes.
- El bloqueo de finalización dispone de explicación asociada mediante `aria-describedby`.
- El historial anterior reutiliza `Modal` de Atlas: nombre accesible, `dialog` nativo, Escape, foco inicial, contención de Tab, fondo inerte y restauración del foco.
- Inputs críticos de Diagnósticos tienen nombre accesible explícito y las acciones siguen disponibles por teclado.

## Responsive

La consulta conserva una columna principal y contexto lateral a partir del breakpoint amplio. Por debajo, el contexto baja después de los módulos clínicos para no comprimir formularios. Los contenedores usan `min-width: 0`, textos largos pueden envolver y las acciones se distribuyen en varias líneas.

En móvil se reduce el padding de tarjetas, los editores permanecen en una columna cuando no caben y no se usa `zoom` ni `transform: scale()`. Signos vitales usa dos columnas desde ancho pequeño y cuatro solo en viewport amplio. El editor de órdenes conserva su padding inferior seguro y scroll interno para catálogos largos.

## Backend

No se modifica. La auditoría confirmó que revisión optimista, bloqueos transaccionales, permisos, scope, inmutabilidad y concurrencia PostgreSQL ya ofrecen las garantías requeridas. 6B9 solo mejora la interpretación y recuperación en frontend.

## Diferido a 6C1+

- plantillas y configuración por especialidad;
- cardiología y pediatría;
- configuración no-code;
- integración con dispositivos;
- merge asistido de conflictos;
- autosave o persistencia local de borradores.
