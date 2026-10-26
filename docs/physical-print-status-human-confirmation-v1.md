# Physical print status + human confirmation V1

## Alcance y estado

Microfase sin impresión física. Workspace `<WORKSPACE>`, rama
`feat/complete-care-context`, HEAD `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
Current, head y target oficiales permanecen en `0069_print_job_contract`.
No se necesita migración PostgreSQL ni se crea 0070.

Se reutilizan PrintJob, PrintResult, estados, scopes y ClinicalAuditLog existentes.
La auditoría conserva procedencia/actor/fecha; no se usa como cola ni como permiso.
No se implementa Print Management, routing general ni un selector de impresión física.

## Semántica de evidencia

| Evidencia | Estado / presentación | Consecuencia |
| --- | --- | --- |
| SIMULATED_PRINTED | SafeValidation Printed: «Validación completada (sin impresión física)» | No acredita papel. |
| SUBMITTED_TO_SPOOLER | Recibo durable local con spool ID positivo | Windows aceptó el trabajo, no demuestra salida. |
| AWAITING_HUMAN_CONFIRMATION | Physical Submitted: «Enviado a la impresora · confirmar resultado» | Espera evidencia final o confirmación autorizada. |
| OS_REPORTED_PRINTED | Printed: «Impresión completada» | El adaptador recibió confirmación final de Windows; no es una inferencia por ausencia de excepción. |
| HUMAN_CONFIRMED_PRINTED | Printed: «Impresión confirmada» | Usuario autorizado confirmó YES, con actor y fecha. |
| UNKNOWN_AFTER_SPOOL | Unknown: «Resultado de impresión incierto» | No reimpresión automática. |

`Submitted != Printed`. La confirmación negativa deja Unknown con código
`HUMAN_REPORTED_PROBLEM`; conserva el spool ID y la evidencia previa. La política
V1 no permite promover manualmente un Unknown a Printed. Una intención futura
requerirá un proceso explícito separado, no un retry automático.

## API, autorización e idempotencia

`POST /api/v1/print-routing/{job_id}/confirm-physical`

Payload: `confirmed` booleano estricto y motivo opcional controlado
(`not_printed`, `damaged`, `other`). Una confirmación positiva no acepta motivo
de fallo. Campos adicionales, incluido `confirmed_by`, se rechazan.

El servidor resuelve actor autenticado, tenant, centro, estación, impresora y job.
Reutiliza `documents:print` + `local_agents:view`; para un job de otro solicitante
requiere además `local_agents:manage`. Se aplican los scopes existentes y el
bloqueo de fila PostgreSQL del job. No se crean permisos ni roles nuevos.

Solo admite el contrato físico QA V2 existente, referencia `physical-routing-qa`,
en Submitted con recibo físico coherente y spool ID positivo. Su creación ya
requiere la autorización estricta previa del puente físico. La expiración o
retirada posterior del grant no invalida el derecho a registrar qué ocurrió con
un trabajo ya enviado: confirmar un recibo nunca autoriza otra ejecución.

SafeValidation, falta de spool, estado incompatible, destino revocado/no accesible,
otro tenant o falta de permiso no permiten confirmar. Repetir la misma respuesta
es idempotente; una respuesta contradictoria devuelve 409. Ambas operaciones
concurrentes se serializan sobre el job. Un recibo tardío del agente con el mismo
spool ID no revierte una decisión humana; uno distinto devuelve 409.

## Auditoría

Se conservan los eventos existentes de resultado/transición y se añaden:

- `print_job.awaiting_human_confirmation`: Submitted físico aceptado y confirmación disponible.
- `print_job.os_reported_printed`: resultado final reportado por Windows.
- `print_job.human_confirmed_yes` / `print_job.human_confirmed_no`: decisión humana funcional única.

Incluyen organización, centro, job, hash de intención, estación/impresora destino,
actor, timestamp, origen y spool ID cuando corresponde. La decisión humana guarda
el actor real autenticado, no un identificador aportado por el navegador. No se
guardan documentos, bytes, tokens, contraseñas ni texto libre clínico. Consultar
estado no genera auditoría de modificación. Un retry de recibo conserva su evento
técnico existente, sin duplicar la auditoría funcional de confirmación.

## Agent y SQLite

El recibo durable conserva Submitted/Printed/Unknown. La tabla local aditiva
`physical_observations` distingue `OS_REPORTED_PRINTED`,
`HUMAN_CONFIRMED_PRINTED` y `HUMAN_REPORTED_PROBLEM`, con spool ID y timestamp.
No cambia el envelope ni su huella de intención. Actor/fecha autenticados son
responsabilidad del backend, no del Agent.

Al recibir una redelivery de recibo, el consumidor acepta la confirmación humana
solo si coincide con su Submitted durable, spool ID, modo receipt-only y resultado
del servidor. La guarda sin llamar al ejecutor. Un reinicio/retry conserva ese
resultado; un Unknown no se ejecuta otra vez. La sincronización se valida por
redelivery/replay del recibo existente; no se añade un nuevo worker de sincronía
de confirmaciones terminales.

La base SQLite real no recibió jobs nuevos en esta microfase. Su SHA256, identidad
y secreto DPAPI permanecieron idénticos; el cambio aditivo local se verificó con
bases SQLite temporales.

## UI y evidencia visual

Se reutiliza el modal oficial. «Consultar trabajo existente» hace GET autorizado
por UUID y permite revisar un recibo sin crear una intención nueva. La acción
«Confirmar impresión» solo aparece para un recibo físico Submitted autorizado con
spool ID. YES/NO requiere elección explícita y guardado; la UI espera la respuesta
autoritativa, sin marcar Printed de forma optimista. No hay toggle físico global.

Se usó la habilidad de control del navegador para revisar la UI oficial con la
sesión Administrador y el job SafeValidation preexistente
`<QA_JOB_ID>`. Desktop 1440, móvil 390 y tablet 820:
etiqueta no física correcta, sin CTA humana y sin overflow horizontal en móvil/tablet.

Evidencia: `<LOCAL_EVIDENCE_DIR>`,
`mobile-safe.jpg`, `tablet-safe.jpg`. Se restauró el viewport al terminar.

Los flujos físicos YES/NO en esos tres anchos se probaron con recibos mock en
tests React, no con un job físico oficial ni con papel. No se presenta esa prueba
como aceptación física real. Esta separación es obligatoria porque la microfase
prohíbe crear jobs físicos autorizados o imprimir.

## Archivos de esta microfase

- `backend/app/services/physical_print_evidence.py` (nuevo).
- `backend/app/services/print_jobs.py`.
- `backend/app/services/print_routing.py`.
- `backend/app/api/routes/print_routing.py`.
- `backend/app/api/routes/official_print_routing.py`.
- `backend/tests/test_physical_print_confirmation.py` (nuevo).
- `backend/tests/validate_physical_confirmation_pg.py` (nuevo, PostgreSQL desechable obligatorio).
- `agent/Atlas.LocalAgent.Service/FakePrintRouting.cs`.
- `agent/Atlas.LocalAgent.Service/DurablePrintJobStore.cs`.
- `agent/Atlas.LocalAgent.Tests/PhysicalBridgeTests.cs`.
- `frontend/src/services/printRouting.ts`.
- `frontend/src/components/FakePrintAction.tsx`.
- `frontend/src/components/fakePrintAction.css`.
- `frontend/tests/print-routing.test.mjs`.
- Este informe.

El workspace ya tenía numerosos cambios de fases anteriores: se preservan y no
se atribuyen a esta microfase. `.env`, Compose, identidad y credencial no cambiaron.

## Validación ejecutada

| Verificación | Resultado |
| --- | --- |
| Backend nuevo focal | 6 passed, 0 failed |
| Backend focal ampliado | 159 passed, 0 failed |
| Backend completo | 795 passed, 29 skipped, 0 failed; 1312.26 s |
| Confirmación concurrente PostgreSQL temporal | 2 respuestas 200, 1 job Printed, 1 auditoría humana funcional, 0 ejecuciones físicas |
| Agent focal | 37 passed, 0 failed |
| Agent completo | 153 passed, 1 skipped, 0 failed |
| Frontend focal | 39 passed, 0 failed |
| Frontend completo | 544 passed, 0 failed |
| .NET build/analyzers | 0 errores, 0 warnings |
| TypeScript / Vite build | PASS; warning de chunk mayor de 500 kB |
| Python compile / Compose config / git diff --check | PASS |

Backend completo emitió 17710 warnings, principalmente deprecaciones de fechas UTC
naive y dependencias. El focal ampliado emitió 3483 warnings. No se ocultan ni se
corrigen de forma ajena al alcance. Los 29 skips del backend corresponden a pruebas
opt-in no habilitadas por esta ejecución. El skip del Agent es
`RealHttpTemporaryRegistryOnlyWhenOptedIn`, una
integración HTTP temporal que requiere opt-in; no es una impresión omitida.

## Integridad oficial y runtime

Snapshot de solo lectura: `<LOCAL_EVIDENCE_DIR>`,
comparado con `<LOCAL_EVIDENCE_DIR>`.

- 105 tablas, 92 secuencias; esquema y secuencias idénticos.
- Datos idénticos salvo disponibilidad/heartbeat de `local_agents` y `agent_printers`.
- 2 pacientes, 4 citas, 3 PrintJobs, 3 entregas, 3 resultados; 90 auditorías clínicas.
- No nuevo job físico, confirmación humana ni fixture en DB oficial.
- 11 trabajos antiguos Windows sin cambios; 0 <PRINTER_NAME> nuevos; spooler Running.
- Se reinició solo el gateway HTTPS para cargar el endpoint; su command no ejecuta Alembic.
- Agent manual `SafeValidation`, sin archivo de autorización física: `AllowedJobId=none`, physical disabled.
- Sin cambio de configuración, migración, pairing, impresión, servicio permanente, commit, push o deploy.
- PostgreSQL oficial healthy; backend health, /docs, frontend y HTTPS: HTTP 200.
- Agent Connected/En línea, 10 impresoras, sin error; archivo de autorización física oficial no configurado.
- PostgreSQL temporal retirado tras terminar las suites, previa comprobación de nombre,
  label exclusivo de esta fase y almacenamiento tmpfs sin mounts persistentes. No
  quedan fixtures oficiales ni contenedores QA de esta fase.

## Resultado final

```text
RESULT=PASS
PHYSICAL_STATUS_UI_READY=YES
HUMAN_PRINT_CONFIRMATION_READY=YES
SUBMITTED_NOT_FALSELY_PRINTED=YES
HUMAN_CONFIRMATION_AUDITED=YES
UNKNOWN_NO_AUTOREPRINT=YES
REAL_SPOOLER_DELTA=0
PHYSICAL_PRINTS_SENT=0
```

Builds y tooling PASS. `git diff --check` conserva únicamente el aviso previo de
conversión LF/CRLF en AgendaMonthPanel, sin error. Ningún archivo de Agenda fue
modificado por esta microfase. 407 entradas Git preexistentes; 411 al cierre,
incluidos los cuatro archivos nuevos de esta fase. No se descartan cambios previos.

## Siguiente microfase

Aceptación física separada: una única intención sintética, una copia, UUID y
huellas explícitamente autorizados, comprobación del papel y confirmación humana
auditada. Requiere una nueva autorización expresa. No iniciarla desde esta fase.
