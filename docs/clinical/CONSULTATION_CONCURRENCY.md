# Integridad y concurrencia de consultas

## Invariantes

Cada cita puede estar vinculada como máximo a una `ClinicalHistory`. La base de datos lo garantiza con `uq_clinical_histories_appointment_id`. Se eligió una restricción `UNIQUE` normal porque PostgreSQL permite múltiples valores `NULL`: las historias legacy sin cita siguen siendo compatibles, mientras dos historias con el mismo `appointment_id` no pueden confirmarse.

La migración `0029_clinical_concurrency` inspecciona duplicados antes de crear la restricción. Si encuentra alguno, falla con los identificadores de cita afectados y exige reconciliación manual. No elimina, combina ni escoge historias clínicas.

## Revisiones y contrato de actualización

`ClinicalHistory.revision` empieza en `1`, es obligatorio y solo lo incrementa el servidor. El `PUT /clinical-history/{id}` recibe `expected_revision`; no acepta una revisión nueva elegida por el cliente. La actualización se limita por `id`, `revision` y estado `in_progress`, e incrementa la revisión en la misma sentencia.

Si `expected_revision` ya no coincide, el servidor responde `409` con un mensaje estable para que el médico recargue cuando decida. No reintenta, fusiona ni recarga automáticamente, por lo que el texto local permanece visible y no sobrescribe la versión confirmada por otra sesión.

## Finalización y escrituras hijas

`require_history_access(write=True)` adquiere un bloqueo `SELECT FOR UPDATE` sobre una sola fila de `clinical_histories`, después de validar el alcance clínico. Diagnósticos, recetas, solicitudes legacy, órdenes clínicas normales y signos vitales usan esa primitiva. El bloqueo dura únicamente hasta el commit o rollback de la petición; nunca permanece abierto durante interacción humana.

Finalizar usa el mismo bloqueo y una transición condicional `in_progress -> completed` ligada a la revisión actual. La historia, su nueva revisión, la cita completada y el evento de auditoría se confirman en una sola transacción. Una escritura hija y un cierre concurrentes quedan en un orden total: una escritura que confirma primero pertenece a la consulta abierta; si el cierre confirma primero, la escritura recibe `409` y no se aplica.

El orden de bloqueo es siempre historia y después cita o recurso hijo. Solo se bloquea una historia por petición, lo que mantiene reducido el alcance y el riesgo de interbloqueo. Las operaciones append-only posteriores al cierre (`ClinicalAddendum` y órdenes clínicas adicionales) conservan su autorización específica y no solicitan el bloqueo de escritura normal.

## Signos vitales

El primer upsert de signos vitales queda serializado por el bloqueo de su historia. La segunda transacción consulta después de que la primera confirma: actualiza la fila existente en vez de competir con otro `INSERT`. La restricción `uq_vital_signs_clinical_history_id` continúa siendo la garantía final de una sola fila.

## Auditoría

Los conflictos de creación, revisión y ciclo de vida registran actor, acción, resultado `conflict`, identificadores de historia/cita y revisiones esperada/actual cuando aplican. El contexto no incluye anamnesis, notas, recetas ni otro texto clínico.

## Pruebas PostgreSQL

`test_clinical_concurrency.py` usa una base PostgreSQL desechable llamada `clinical_concurrency_test`. Barreras y eventos coordinan transacciones reales sin retardos arbitrarios. Cubre creación doble por cita, revisión obsoleta, actualización contra cierre, diagnóstico contra cierre y primer upsert concurrente de signos vitales.

## Límites y trabajo posterior

Este cambio no implementa autosave, resolución visual de diferencias, reapertura, caché de consultas ni módulos por especialidad. El usuario debe decidir cuándo recargar después de un conflicto. La migración se detiene si existen duplicados y requiere que una persona los reconcilie sin pérdida de información antes de volver a ejecutarla.
