# ConsultationWorkspace — Phase 6B7B

## Arquitectura

`Consultation.tsx` recibe `appointment` y `onBack` y delega el episodio al workspace.

```text
Consultation
└── ConsultationWorkspace
    ├── ConsultationHeader
    ├── AnamnesisModule
    ├── VitalSignsModule
    ├── DiagnosesModule
    ├── PrescriptionsModule
    ├── ClinicalOrdersSection (structured LaboratoryOrder / StudyOrder)
    ├── requested tests legacy (Estudios y análisis)
    ├── contexto de atención e historial previo
    └── modal de historial previo
```

Se conserva el orden real de la pantalla, incluidos los estudios solicitados después de las órdenes estructuradas. No cambian etiquetas, campos, clases, botones ni condiciones de solo lectura.

## Límites de propiedad

- **Workspace:** contexto activo, `ClinicalHistory` canónica, listas canónicas de diagnósticos, recetas y `RequestedTest`, bootstrap, guardado y finalización de historia, errores de episodio, coordinación, documentos y contexto histórico. `RequestedTest` se presenta solo como compatibilidad/historial y PDF cuando existen registros.
- **AnamnesisModule:** formulario local; el workspace guarda con `expected_revision` y adopta la revisión del servidor.
- **VitalSignsModule:** formulario y mutación de signos vitales, con resultado canónico comunicado al workspace.
- **DiagnosesModule:** descripción, CIE-10, indicador principal y estado local de guardado; creación y eliminación por `clinicalApi`. Recibe `episodeId`, `historyId`, lista canónica, `completed`, callback funcional `onChange` y `onError`.
- **PrescriptionsModule:** los ocho campos de receta, ID en edición, cancelación y estado local de guardado; creación, actualización y eliminación por `clinicalApi`. Recibe el mismo contexto explícito, lista canónica y callbacks, más acción/estado de descarga PDF del workspace.
- **ClinicalOrdersSection:** listas, catálogos, resumen compacto, chooser y editores progresivos de `LaboratoryOrder` y `StudyOrder`; conserva su carga local por episodio. Se reinicia y protege publicaciones tardías por `historyId`/`specialtyId`. `RequestedTest` no forma parte de este componente ni de la creación de órdenes nuevas.

Los módulos no duplican las listas en estado local. Entregan al workspace actualizaciones funcionales basadas en las respuestas canónicas para conservar otras mutaciones de la misma lista. Los errores siguen en el aviso de episodio existente: crear/guardar limpia el aviso al iniciar, eliminar no lo limpia, y los fallos muestran el detalle normalizado del servidor. No se introduce un segundo canal de errores ni se ocultan errores de episodio.

## Contrato preservado, caracterizado antes de extraer

**Diagnósticos:** descripción obligatoria con `trim`, CIE-10 con `trim` o `null`, e `is_primary`. La selección inicial es verdadera si la lista del bootstrap carece de principal. POST `/clinical-history/{historyId}/diagnoses` devuelve el diagnóstico canónico: si la solicitud era principal se inserta primero y se desmarcan los anteriores; si no, se añade al final. Tras éxito se vacían ambos textos y se desmarca principal. DELETE `/clinical-history/{historyId}/diagnoses/{id}` quita solo el elemento, sin promover otro principal. La UI actual no ofrece edición de diagnósticos, aunque el backend tenga otros métodos.

**Recetas:** `medication`, `presentation`, `dose`, `route`, `frequency`, `duration`, `quantity`, `instructions`. Medicamento obligatorio con `trim`; los seis textos opcionales se envían con `trim` o `null`. Cantidad vacía pasa a `null`; cualquier valor no vacío usa `Number`, incluido cero, sin validación nueva del frontend. POST `/clinical-history/{historyId}/prescriptions` añade la respuesta canónica; PUT a `/{id}` reemplaza por el ID devuelto. Editar copia los ocho campos; cancelar vacía el formulario sin petición. El éxito vacía formulario e ID. DELETE quita el elemento sin cancelar una edición ya abierta, conservando ese comportamiento previo. Los errores conservan formulario/lista y no simulan éxito.

Ambos requieren historia guardada y consulta abierta para mutar. La carga inicial pertenece al bootstrap, sin GET inicial de módulo ni cascadas nuevas. `completed` oculta controles de mutación y conserva datos legibles. El backend sigue imponiendo autoridad de paciente, médico, historia y especialidad, validación y restricciones de ciclo de vida.

## PDF de receta

El workspace mantiene la petición, estado de descarga, historia activa, errores y descarga del documento completo del episodio. El módulo presenta el botón en su posición original y delega la acción. Se conserva GET `/clinical-history/{historyId}/prescriptions/pdf`, respuesta blob, autenticación del cliente existente, nombre `receta-{historyId}.pdf`, click del enlace y liberación de URL. No cambian contenido ni impresión. La descarga sigue disponible con recetas después del cierre.

## Sincronización de episodio y concurrencia

`useConsultationBootstrap` sigue siendo el único propietario de la carga inicial desde el workspace. Conserva AbortController, guard de generación, protección A → B → respuesta tardía de A y cancelación al desmontar. La caché de catálogos no PHI queda intacta.

Cada módulo delimita su editor mediante una clave de cita e historia. Un cambio de esa identidad desmonta el editor anterior, vacía su formulario y carga la lista que entrega el workspace para el nuevo episodio. Nuevas identidades de arrays, callbacks o revisiones de la misma historia no destruyen ediciones. El guard de actividad de cada editor impide que una respuesta o error pendiente de un editor desmontado modifique la lista o aviso del episodio nuevo. No se cancela ni reintenta una escritura HTTP ya enviada; el servidor puede haberla aplicado a su episodio original.

`ClinicalHistory.revision`, `expected_revision`, finalización y errores 409 permanecen iguales. Estos recursos hijos no usan revisión en su payload actual y no se inventa una. No hay recarga automática, reintentos automáticos, autosave, dirty global ni resolución nueva de conflictos. Los otros handlers del workspace quedan fuera de esta extracción.

## Privacidad y seguridad

Datos clínicos solo en memoria del árbol React. Sin localStorage, sessionStorage, IndexedDB, stores persistentes/globales, logs, analítica ni cachés de diagnósticos/recetas. La UI no sustituye autorización del backend. Pruebas con fixtures ficticios; sin cambios de backend, migraciones, endpoints ni CI.

## Validación

`consultation-diagnoses-prescriptions.test.mjs` cubre render canónico, contratos HTTP completos, principal/CIE-10, CRUD de recetas, cancelación, null/cantidad, errores 409, ausencia de GET de módulo, rerender, cambio de cita/historia, respuestas tardías de creación/edición/eliminación, unmount y solo lectura con PDF. Las pruebas existentes de workspace, caracterización, API y bootstrap siguen siendo obligatorias, incluida su comprobación del número de GET iniciales.

## Órdenes clínicas

Las solicitudes libres `RequestedTest` y las órdenes estructuradas son recursos distintos y permanecen compatibles. `RequestedTest` sigue cargándose desde el bootstrap del workspace y conservando PDF/solo lectura cuando hay registros, sin creador nuevo en la consulta normal. Las órdenes estructuradas son el flujo preferido y usan `ClinicalOrdersSection` con resumen compacto, chooser y catálogos bajo demanda. Se conservan los únicos flujos append-only post-cierre autorizados para el médico responsable. La caracterización completa está en [CLINICAL_ORDERS_BOUNDARY.md](CLINICAL_ORDERS_BOUNDARY.md).

## Roadmap

- 6B5 Anamnesis + Vital Signs — DONE
- 6B6 Diagnoses + Prescriptions — DONE
- 6B7 Requested tests / structured orders UX boundary — CURRENT
- 6B8 historical/post-close unification
- 6B9 performance/accessibility/dirty/conflict/responsive
- 6C1 registry/versioned model
- 6C2 Cardiology pilot generic
- 6C3 Pediatrics
- 6D devices/results Holter/MAPA
