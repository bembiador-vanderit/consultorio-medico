# 0057 — Identidad de borradores clínicos

Esta migración está preparada, pero **no se aplica a la base oficial** en esta microfase. El punto de partida oficial sigue siendo `0056_clinical_forms`.

## Causa y regla nueva

0055 creó, por cada tabla (evaluación preoperatoria y examen físico), un índice único parcial sobre organización, paciente, médico, centro y fecha cuando el estado es `draft` o `pending_evaluation`. El servicio buscaba por la misma combinación. No incluía `appointment_id` ni `clinical_history_id`: dos consultas del mismo día podían reutilizar el documento incorrecto. Los valores `NULL` de estas columnas no distinguían casos porque ni siquiera participaban en el índice.

0057 reemplaza ese índice con tres índices parciales por tipo de documento:

- Con cita: organización + `appointment_id`, solo documentos abiertos con cita no nula. La cita es el contexto canónico, aun si después se vincula una historia clínica.
- Sin cita pero con historia: organización + `clinical_history_id`, solo documentos abiertos en ese caso.
- Sin cita ni historia: organización + paciente + médico + centro + fecha operativa, solo documentos abiertos sin ambos vínculos.

Los estados `completed` y `signed` quedan fuera de la protección; no se reescriben snapshots ni se bloquean nuevas evaluaciones históricas. El servicio usa las mismas tres condiciones que la base. Antes de cambiar índices, la migración comprueba colisiones y se detiene sin fusionar ni borrar registros. Un downgrade se rechaza si documentos ahora distintos colisionarían con el índice de 0055.

Un borrador preparado desde Paciente no se vincula automáticamente a Consulta. La pantalla ofrece uno o varios candidatos abiertos compatibles; el médico elige explícitamente cuál continuar. La API de vinculación comprueba paciente, médico, centro, tenant, revisión, estado, cita y consulta. Si otro documento ya ocupa ese contexto, rechaza la operación.

El médico autenticado queda fijado como responsable. Sin centro contextual, Atlas resuelve su único centro autorizado o exige elegir uno entre varios. No existe aún un centro activo global de sesión. Para secretaría, se reutilizan las opciones de agenda filtradas por sus centros y médicos autorizados; el servidor vuelve a comprobar el alcance. Desde Paciente se confirma visualmente la identidad con datos enmascarados antes de crear; después `patient_id` no figura en la operación de actualización.

## Fuera de alcance / deuda

- Contexto global de sesión `Usuario + Organización + Centro activo`.
- Reportes ARS multi-centro: operación diaria por centro activo; reportes financieros del médico por centro actual, todos sus centros o selección múltiple, siempre según permisos. No se implementan aquí.
- Enmiendas auditadas posteriores a la firma.
- No usar la funcionalidad nueva contra la base oficial hasta una activación controlada de 0057.
