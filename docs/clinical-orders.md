# Órdenes clínicas estructuradas

Atlas conserva las solicitudes libres existentes en `requested_tests` como formato legado. Las órdenes estructuradas se almacenan independientemente; no convierten, reinterpretan ni sobrescriben registros anteriores.

## Implementado ahora

### Modelo y contexto

- `laboratory_tests` es el catálogo global de pruebas activas agrupadas por categoría.
- `laboratory_orders`/`laboratory_order_items` y `study_orders`/`study_order_items` conservan órdenes e ítems persistentes.
- El backend deriva `appointment_id`, paciente, médico, centro y especialidad de la historia clínica. Esos identificadores no forman parte del payload aceptado.
- La orden guarda snapshots de paciente, médico, centro, especialidad e ítems para que su lectura y PDF no cambien si los catálogos o nombres se actualizan posteriormente.
- `is_additional` distingue una orden emitida después del cierre sin alterar la consulta ni las órdenes originales.

### Ciclo de vida y permisos

- Durante `in_progress`, solo el médico responsable con acceso clínico normal puede crear o modificar órdenes.
- Al completar la consulta, las órdenes existentes quedan en modo histórico: no se editan, eliminan ni sustituyen.
- El médico responsable puede emitir una orden nueva mediante **Nueva orden adicional**. Es append-only, tiene autor y fecha propios, no reabre la consulta y aparece cronológicamente junto a las anteriores.
- Secretaria, administrador puramente administrativo, médico ajeno y acceso delegado de solo lectura no pueden crear órdenes adicionales.
- Catálogos inactivos no se ofrecen para órdenes nuevas, pero sus snapshots siguen visibles históricamente.
- Los PDFs se descargan y pueden regenerarse desde datos persistidos mientras el usuario mantenga acceso de lectura.

### API

- `GET /laboratory-tests?q={texto}`
- `GET|POST /clinical-history/{history_id}/laboratory-orders`
- `POST /clinical-history/{history_id}/laboratory-orders/additional`
- `PUT /clinical-history/{history_id}/laboratory-orders/{order_id}`
- `GET /laboratory-orders/{order_id}/pdf`
- `GET|POST /clinical-history/{history_id}/study-orders`
- `POST /clinical-history/{history_id}/study-orders/additional`
- `PUT /clinical-history/{history_id}/study-orders/{order_id}`
- `GET /study-orders/{order_id}/pdf`

### Catálogo y migraciones

`0026_clinical_orders` crea las tablas y carga las 57 pruebas iniciales. `0027_expand_laboratory_catalog` añade las pruebas legibles del formulario físico suministrado, hasta un total esperado de 321 pruebas en 16 categorías, y añade las marcas persistentes de órdenes adicionales.

La migración `0027` usa `laboratory_tests.seed_key` únicamente para sus inserciones y compara nombres normalizados sin distinguir mayúsculas. Su downgrade elimina solamente seeds sin referencias clínicas; una prueba ya usada se preserva. Los nombres equivalentes se mantienen en un único registro canónico, por ejemplo: VSG/eritrosedimentación, TPT-aPTT/TTP, HbA1c/hemoglobina glicosilada, PCR ultrasensible/PCR de alta sensibilidad y examen general de orina/uroanálisis.

Una línea entre “Hematocrito” y “Hemograma completo” no fue suficientemente legible para transcribirla sin inventar un nombre. Los renglones libres “Alérgenos” y “Otros” no representan pruebas nombradas; se conservan las pruebas concretas existentes de esas categorías.

## Preparado arquitectónicamente

`ClinicalOrdersSection` concentra carga, búsqueda, selección, guardado e impresión sin depender de la posición del módulo dentro de `Consultation.tsx`. Puede envolverse posteriormente en un modal, drawer, panel lateral o workspace expandible. El historial usa un componente separado de lectura y reimpresión.

La búsqueda es case-insensitive en backend y frontend, admite fragmentos de nombre, categoría o código y conserva selección múltiple por categorías.

La generación PDF está centralizada en un builder que recibe el contexto documental como parámetros. Las órdenes ya conservan snapshots de nombres de médico y centro, permitiendo evolucionar hacia una resolución explícita de identidad `médico + centro` sin cambiar autoría clínica.

## Futuro / fuera de alcance de PR #24

- Workspace clínico con módulos reordenables, tamaños configurables, visibilidad y preferencias por usuario/especialidad.
- Favoritos, plantillas clínicas, selección rápida y administración avanzada del catálogo.
- Perfiles documentales configurables de centro y médico: logo, dirección, teléfonos, RNC, exequátur/CMD, firma y sello.
- Diseñador de documentos por bloques con campos obligatorios, opcionales y restricciones por tipo documental.
- Snapshot o versión completa de la plantilla visual utilizada al emitir. Actualmente se preservan datos clínicos y nombres contextuales, pero no logos, firmas, datos profesionales o layout versionado.

Hasta implementar identidad configurable, “Atlas Consultorio” sigue siendo una marca provisional del generador. No representa ni sustituye la identidad legal/profesional del médico o centro y no se ha hardcodeado ninguna identidad particular.
