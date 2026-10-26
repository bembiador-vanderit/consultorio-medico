# Protección de doble reserva Por hora — V1

## Regla y alcance

Solo `timed` en estados `scheduled` y `confirmed` ocupa horario. La clave es
organización + centro + médico + fecha local de cita + hora de inicio exacta.
Paciente y especialidad no participan. No se introduce duración de consulta,
solapamiento de intervalos ni prohibición entre centros distintos.

`cancelled`, `no_show` y `completed` no ocupan ese horario. Editar excluye el ID
actual; reactivar y reprogramar vuelven a validar. La agenda `queue`, su hora
nula, sus contadores monotónicos y la emisión del turno al llegar no cambian.

## Implementación

`appointment_slots.ensure_slot_available` se ejecuta después de autorización y
validación de contexto, bajo el bloqueo de centro ya existente. Alta, edición,
reactivación, Seguimientos → Agenda, transferencia y restauración por cobertura
clínica usan la misma regla. No amplía permisos ni alcance organizacional.

La revocación de cobertura bloquea primero las citas afectadas, ordenadas por ID,
y después el centro: conserva el mismo orden que editar/transferir y evita una
inversión de bloqueos entre operaciones concurrentes.

El conflicto devuelve 409: «El médico ya tiene una cita activa en ese horario.»
No se crea cita parcial ni se vincula/audita un seguimiento exitoso rechazado.
Las transferencias/restauraciones rechazadas tampoco dejan auditoría exitosa.

La revisión `0063_appointment_slot_guard`, hija de `0062_feature_visibility`,
añade únicamente `uq_appointments_active_timed_slot`, índice único parcial con
`NULLS NOT DISTINCT` (PostgreSQL 15+, validado en PostgreSQL 16). Incluye centros
nulos históricos sin dejar una vía de duplicación. Si ya hay colisiones, aborta
sin borrar, fusionar o modificar ninguna cita. Downgrade solo retira el índice.

El índice resuelve carreras incluso fuera del guard de dominio. Solo su nombre
de constraint se traduce a 409; otros errores de integridad no se ocultan.
La API conserva el bloqueo existente de centro y protege también las escrituras
HTTP sobre 0062 mientras la nueva migración está pendiente. La defensa de base
para escritores externos requiere activar 0063 en otra tarea autorizada.

## Frontend

No fue necesario cambiar producción: `AppointmentForm` ya conserva estado y
selección cuando el backend rechaza guardar. Las nuevas pruebas verifican el
mensaje, preservación de campos, reprogramación y reintento de Seguimientos.

## Validación local controlada

- Inicial: rama `feat/complete-care-context`, HEAD
  `3646b6bd7689d7f49941a8254ec327c3eda5682e`; current/head 0062.
- Solo pacientes QA 19 y 20; citas iniciales 0.
- Antes del fix, UI aceptó citas 51 y 52: médico 3, centro 1, 20/10/2026 08:00,
  pacientes diferentes. Ambas se retiraron mediante el servicio existente.
- Después: cita 53 QA A 08:00 aceptada; QA B 08:00 rechazada con mensaje visible;
  cambiando solo hora, cita 54 QA B 08:30 aceptada. Cancelar 53 permitió mover 54
  a 08:00. Se retiraron exclusivamente 53 y 54 al terminar el smoke.
  Los IDs consumidos 51–54 no se reutilizan: no se reinició la secuencia técnica.
- Final oficial: current 0062, dos pacientes QA, cero citas; las 91 huellas de
  tablas coinciden exactamente con el precheck, incluida auditoría estructural.
- PostgreSQL temporal: roundtrip 0062→0063→0062→0063, 91 huellas preservadas,
  rechazo de migración con colisiones y protección del centro nulo.
- Carreras HTTP con/sin índice: una 201 y una 409; carrera directa del índice:
  una 201 y una 409, una sola cita persistida. Transferencia/restauración con
  conflicto: 409, sin modificación ni auditoría exitosa parcial.

El validador `backend/tests/validate_appointment_slots_postgres.py` rechaza
cualquier host que no empiece por `atlas-slot-guard-qa-` y cualquier base distinta
de `atlas_slot_qa`. Usa credenciales e identidades sintéticas, no datos oficiales.

No se activó 0063 oficialmente, ni se cambió configuración de visibilidad,
Safety, Sharing, finanzas o permisos. Sin commit, push ni deploy.

## Archivos de esta microtarea

- `backend/app/services/appointment_slots.py` (nuevo).
- `backend/app/models/appointment.py`.
- `backend/app/api/routes/appointments.py`.
- `backend/app/api/routes/clinical_coverages.py`.
- `backend/alembic/versions/0063_appointment_slot_guard.py` (nueva).
- `backend/tests/test_appointment_slots.py` (nuevo).
- `backend/tests/validate_appointment_slots_postgres.py` (nuevo).
- `backend/tests/test_cardiology_workspace.py`.
- `frontend/tests/agenda-ui.test.mjs`.
- `frontend/tests/cardiology-workspace.test.mjs`.
- Este informe (nuevo).

Se preservaron los cambios previos del workspace, que ya estaba sucio. No se
necesitaron cambios adicionales en componentes frontend de producción.

## Cierre de aceptación — 17/10/2026

**RESULT=PASS** (implementación y validación; no activación de migración).

1. Current/head inicial: `0062_feature_visibility` / `0062_feature_visibility`.
2. Inicial: pacientes 2 (19 y 20), citas 0.
3. Blocker reproducido antes del fix: citas 51/52 aceptadas en el mismo slot.
4. Ocupantes: `scheduled`, `confirmed`; ningún estado nuevo.
5. Unicidad: organización/centro/médico/fecha/hora; sin `patient_id`.
6. Guard central en alta/edición/reactivación; reutilizado por los otros escritores.
7. PostgreSQL: índice único parcial y traducción específica a HTTP 409.
8. Migración nueva: sí, aditiva y sin reescrituras de datos.
9. Revisión: `0063_appointment_slot_guard`; única head del código.
10. Cancelar libera: PASS, pruebas y smoke real.
11. Reactivación conflictiva `scheduled`/`confirmed`: 409, PASS.
12. Reprogramación ocupada: 409; libre: permitida; excluye ID propio, PASS.
13. Diferentes médicos en mismo horario: permitido, PASS.
14. Diferentes horas: permitido, PASS.
15. Diferentes centros autorizados: permitido; no se amplió scope, PASS.
16. Por turno: hora nula, orden monotónico y ausencia de ticket al agendar, PASS.
17. Seguimientos: misma protección; rechazo no vincula cita ni crea audit exitoso.
18. Concurrencia PostgreSQL: HTTP sobre 0062 y 0063, y escritura directa contra
    índice: `[201,409]`, una cita activa en cada carrera, PASS.
19. UI real: mensaje claro; paciente, centro, médico, fecha y demás datos
    conservados; cambiar solo hora permitió continuar, PASS.
20. Backend focal final: **128 passed, 0 skipped, 0 failed** (78.97 s).
21. Backend completo final: **611 passed, 29 skipped, 0 failed** (803.29 s).
    Ejecución final recuperable, sobre copia aislada idéntica al código actual.
    Una ejecución anterior se descartó para revisar el orden de bloqueos; no se
    usa como resultado final. PostgreSQL específico sí se ejecutó por separado.
22. Frontend focal: **75 passed, 0 skipped, 0 failed**.
23. Frontend completo: **477 passed, 0 skipped, 0 failed** (257.64 s).
24. Build frontend PASS (201 módulos); Python compile, Compose config y
    `git diff --check` PASS.
25. Roundtrip PostgreSQL 0062→0063→0062→0063 PASS; 91 huellas preservadas.
    Colisión previa aborta migración; centro nulo protegido; transferir/restaurar
    con conflicto no deja cambios ni auditoría exitosa parcial.
26. PostgreSQL healthy; health backend 200; docs 200; frontend 200.
    Logs recientes sin errores SQL, deadlocks ni respuestas 500.
27. Limpieza: se retiraron solo 51/52 y 53/54 por el servicio existente;
    contenedor y red PostgreSQL QA temporales eliminados.
28. Pacientes sintéticos QA preservados; sus identificadores dependen de la instalación.
29. Citas finales: **0**; Agenda vacía también verificada visualmente.
30. Base oficial final: **0062_feature_visibility**; 91 huellas de tablas
    idénticas al precheck, incluida auditoría estructural (32 registros clínicos).
31. NO se activó 0063; `.env` mantiene target 0062; no downgrade oficial.
32. NO commit; Git HEAD permanece `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
33. NO push.
34. NO deploy.
35. Trabajo detenido al cerrar esta microtarea, sin reanudar aceptación general.

### Evidencia y advertencias

Logs y verificación fuera del repositorio: carpeta local
`<LOCAL_EVIDENCE_DIR>`. Incluye backend completo/focal,
frontend completo/focal, PostgreSQL, eventos HTTP y verificación de datos.

El índice está **pendiente de activación oficial controlada** en otra tarea.
El build conserva el aviso de bundle principal >500 kB (693.59 kB). Backend
reporta advertencias de deprecación de fechas/API existentes. Git avisa de
conversión LF/CRLF en `AgendaMonthPanel.tsx`, archivo no modificado por esta tarea.
Ninguna de estas advertencias se ocultó ni se corrigió ampliando este alcance.

## Activación posterior

La activación oficial controlada se completó posteriormente el 17/10/2026:
base local en `0063_appointment_slot_guard`, con backup validado y pruebas PASS.
La evidencia de esa activación se conserva fuera del repositorio.
Las referencias anteriores a «pendiente de activación» describen el estado
histórico de la microfase de implementación, no el estado actual.
