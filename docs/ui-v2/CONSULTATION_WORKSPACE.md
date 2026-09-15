# ConsultationWorkspace — Phase 6B4

## Arquitectura

`Consultation.tsx` es el adaptador de página: recibe `appointment` y `onBack`, y delega todo el episodio a `ConsultationWorkspace`.

```text
Consultation
└── ConsultationWorkspace
    ├── ConsultationHeader
    │   └── identidad de cita y vuelta a Agenda
    ├── estado de la consulta
    ├── AnamnesisModule
    ├── VitalSignsModule
    ├── diagnósticos, recetas y solicitudes
    ├── ClinicalOrdersSection existente
    ├── contexto de atención e historial previo
    └── modal de historial previo
```

`ConsultationHeader` es presentación sin estado: recibe la cita, especialidad ya resuelta y acción de vuelta. El workspace conserva el DOM, orden de secciones, etiquetas y condiciones de visibilidad de la pantalla anterior. No incorpora navegación visual ni módulos vacíos: la estructura existente ya tiene una responsabilidad clínica concreta y el siguiente corte puede extraerla sin devolver coordinación al adaptador de página.

## Límites de propiedad

El workspace posee el contexto de la cita, historia activa, estado de carga y error de nivel episodio, ciclo de vida de consulta y coordinación entre secciones. `AnamnesisModule` posee su formulario local; se reinicializa solo cuando cambia el episodio, la historia activa o su revisión canónica. Un 409 no cambia esa revisión y, por ello, conserva las ediciones locales. `VitalSignsModule` posee su formulario y mutación; comunica exclusivamente el objeto canónico devuelto al workspace. Diagnósticos, recetas y solicitudes siguen locales al workspace.

No hay estado dirty global, autosave, almacenamiento persistente de episodio ni librería de estado global.

## Datos y mutaciones

El workspace reutiliza `useConsultationBootstrap` y `clinicalApi`; no agrega una segunda carga inicial. Se preservan AbortController, guard de generación, protección A → B → respuesta tardía de A, cancelación en unmount y la caché no PHI de catálogos.

La actualización de historia conserva `revision` y envía `expected_revision`. Un 409 muestra el detalle del servidor, no reintenta, no recarga ni descarta cambios locales. La mutación de vitales conserva endpoint, payload nullable y upsert, y adopta la respuesta canónica del servidor. La finalización, solo lectura y reglas post-cierre siguen siendo decisión del backend.

## Privacidad y seguridad

Los datos del episodio viven en el árbol del workspace. No se añade PHI a localStorage, sessionStorage, IndexedDB, consola ni stores globales. La visibilidad del frontend no reemplaza las decisiones de autorización del backend.

## Validación

Las pruebas de caracterización de `Consultation` siguen cubriendo flujos nuevos, existentes, completados y mutaciones. `consultation-workspace.test.mjs` comprueba el adaptador de página, el render directo del workspace con bootstrap y la ausencia de persistencia en browser storage. Las pruebas 6B3 de cliente clínico y carreras siguen siendo la red de seguridad del contrato de datos.

## Diferido

Phase 6B5 extrae anamnesis y signos vitales. Phase 6B6 puede extraer Diagnósticos y Recetas con contratos y pruebas propias. Las solicitudes, órdenes, host de módulos, navegación clínica y límites de dirty/conflicto pertenecen a fases posteriores deliberadas.

## Limitaciones conocidas

El workspace aún contiene los formularios y handlers del episodio para preservar exactamente el comportamiento caracterizado. Las órdenes estructuradas conservan su componente existente. No hay cambios de backend, migraciones ni nuevos endpoints.
