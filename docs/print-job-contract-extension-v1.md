# Print Job Contract Extension V1 — candidato posterior a 0068

Fecha: 2026-10-20. Workspace: `<WORKSPACE>`.

Nota posterior: la revisión `0069_print_job_contract` requiere activación
controlada por instalación. Las referencias a base/target 0068 debajo son el
cierre histórico del candidato, anterior a esa activación.

## Alcance y estado operativo

Esta fase amplía las tablas existentes de 0068 y los contratos internos. No crea
otra cola, endpoints de impresión, polling, routing, transporte de documentos ni
una integración E2E con spooler real o falso. No inicia el agente real ni modifica
su identidad, pairing, credencial DPAPI o almacén local existente.

- Rama: `feat/complete-care-context`.
- HEAD: `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
- Estado inicial oficial: current/head/target `0068_print_job_persistence`.
- Jobs / deliveries / results oficiales iniciales: **0 / 0 / 0**.
- Candidato: **`0069_print_job_contract`**.
- `down_revision`: **`0068_print_job_persistence`**.
- El nombre propuesto de 33 caracteres no cabe en `alembic_version.version_num`
  (`VARCHAR(32)`); se eligió un identificador más corto sin cambiar esa columna.
- Current y target oficiales permanecen en **0068**. Head del código pasa a **0069**.
- No hay 0070. No ejecutar `upgrade head` en la instancia oficial.

El workspace ya tenía 381 entradas pendientes al comenzar. Se preservaron los
cambios ajenos a esta fase. No hubo commit, push, deploy ni reinicio operativo.

## Intención inmutable y límites de confianza

`PrintJob` sigue siendo la intención lógica; `PrintDelivery` representa entregas
con lease e intentos numerados, y `PrintResult` la evidencia/resultados. Crear una
entrega no significa que el agente haya recibido el trabajo: el job permanece
`queued` hasta un reconocimiento explícito. Estas tablas no almacenan bytes PDF,
contenido de pacientes, documentos financieros, tokens ni secretos.

El contrato v2 conserva:

- UUID del job, organización, centro, agente e impresora destino;
- `requested_by`, con FK a usuario y FK compuesta a su membership del tenant;
- `origin_type`, `source_agent_id` cuando corresponde;
- referencia opaca, SHA256, tipo y clasificación del documento;
- formato, copias, creación, expiración y fingerprint versionado.

El cliente no puede proporcionar `requested_by` en `PrintIntent`. `register`
exige un `User` activo y persistente en la misma sesión SQLAlchemy, con membership
activa en el tenant. El futuro adaptador autenticado debe obtenerlo de la sesión
de autenticación, no de un cuerpo HTTP. No se añade una API ni permisos nuevos.

También se exige un resolver documental **del servidor**. Este aplica los permisos
documentales existentes y devuelve metadatos de `ResolvedPrintDocument`, que deben
coincidir con organización, referencia, tipo, clasificación y SHA256 solicitados.
Este objeto no es una credencial ni debe deserializarse del cliente. Esta fase usa
resolvers sintéticos en tests; no implementa aún resolución/descarga de documentos
clínicos o financieros reales. Una relación entre estaciones o la misma LAN/grupo
no concede acceso ni sustituye la autorización del futuro punto de entrada.

Orígenes: `WEB_DESKTOP`, `WEB_MOBILE`, `WEB_TABLET`, `LOCAL_AGENT`, `SYSTEM`.
Móvil/tablet no necesitan `source_agent`; solo `LOCAL_AGENT` lo exige, dentro del
mismo tenant. `SYSTEM` también conserva un solicitante autenticado en esta versión;
no se inventa una cuenta de sistema ni una identidad de backfill.

Clasificaciones reutilizadas: `GENERAL`, `ADMINISTRATIVE`, `FINANCIAL`, `CLINICAL`,
`SENSITIVE_CLINICAL`. La clasificación queda inmutable con la intención autorizada;
no equivale por sí misma a una política avanzada de acceso.

## Estados y transiciones

La fila del job es autoritativa. El servicio, el guard ORM y un trigger PostgreSQL
protegen la intención y las transiciones incluso ante SQL directo.

| Estado v2 | Próximos estados permitidos |
| --- | --- |
| queued | received, cancelled, expired, failed, unknown |
| received | ready, cancelled, expired, failed, unknown |
| ready | printing, cancelled, expired, failed, unknown |
| printing | submitted, printed, unknown |
| submitted | printed, unknown |
| printed / failed / cancelled / expired / unknown | ninguno distinto del actual |

Repetir un estado no genera una transición falsa. `submitted` significa evidencia
de aceptación por el spooler, **no** papel impreso. `printed` requiere evidencia
compatible; el contrato no certifica aquí salida física. `Downloading` sigue siendo
un valor previo del enum del agente, no se introduce como estado server-side porque
esta fase no descarga documentos.

`printing` es la barrera irreversible conservadora. Después no se promete cancelar,
expirar ni convertir una excepción de driver en fallo seguro. Ante incertidumbre:

**UNKNOWN → sin auto-reprint, sin volver a Ready/Printing y sin convertirlo a Failed.**

Una decisión humana futura deberá representar una intención nueva y explícita;
no se implementa aquí ese flujo. Una respuesta tardía incompatible es conflicto.
`submitted → printed` es monotónico y exige spool ID consistente; un ACK tardío
`submitted` no degrada un resultado `printed`.

Cancelación y expiración solo afectan queued/received/ready. Un intento de cancelar
printing/submitted conserva el estado, sin afirmar cancelación física.

Los estados antiguos `delivering` y `cancel_requested` se conservan únicamente para
filas históricas v1. No se permiten en contratos v2. La matriz histórica admite
`queued → delivering`; `delivering → received/cancel_requested/expired/failed/unknown/
submitted/printed`; `cancel_requested → cancelled/expired/failed/unknown/submitted/
printed`. El servicio nuevo no entrega jobs v1 automáticamente.

## Fingerprint, concurrencia y auditoría

La identidad usa JSON canónico v2: claves ordenadas ordinalmente, referencias
opacas ASCII, UUID normalizado, tiempo UTC con milisegundos, SHA256 en minúsculas.
Incluye actor, origen, estación fuente opcional, tenant/centro, destino público
del agente e ID local de impresora, documento/tipo/clase/hash, formato/copias y
expiración. Cambiar cualquiera de esas dimensiones con el mismo job ID es 409.

Python y .NET consumen el mismo vector sintético:
`backend/tests/fixtures/print-intent-v2.json`. SHA256 esperado:
`<SHA256>`.

Se conservan PK/uniques de 0068. `ON CONFLICT`, bloqueo de fila y transacciones
serializan reintentos y entregas concurrentes: un job lógico, una entrega activa
por lease y un resultado lógico. La auditoría existente referencia UUID/hash y
transiciones del job; actor y metadatos inmutables se consultan en la fila original,
sin duplicarlos como una cola paralela. Retry idéntico no duplica creación ni
transición; audit no es estado autoritativo.

## Migración PostgreSQL e históricos

Se añaden seis columnas a `print_jobs`: `contract_version`, `requested_by`,
`origin_type`, `source_agent_id`, `document_type`, `document_security_class`.
Los registros existentes quedan explícitamente v1 y sin atribución nueva; sus
campos y hashes no cambian. Las nuevas inserciones deben ser v2 en `queued` y tener
metadatos completos. No se inventan actores, orígenes ni permisos históricos.

Se amplía el CHECK de estados, se añaden CHECKs de metadata/origen/clasificación/
source, tres FKs de actor/source, el unique `(id, organization_id)` en agentes y
el trigger `print_job_contract_guard`. No se añaden tablas ni secuencias.
No se modifica el cálculo financiero ni los datos clínicos.

Downgrade seguro: si solo existen contratos v1 y estados representables en 0068,
se revierte el esquema preservando filas/hashes/entregas/resultados. Si existen
contratos v2 o progreso no representable, se rechaza **antes de modificar nada**.
Nunca se degradan estados ni se eliminan metadatos silenciosamente. Revertir tras
uso v2 requerirá un procedimiento explícito de conservación/exportación fuera de
esta fase; no ejecutar downgrade oficial.

## Compatibilidad SQLite del agente

El inbox local sube de schema v1 a v2 en transacción, sin reset. Mantiene la
identidad estación/organización/centro y verifica el hash original antes de copiar.
Preserva JSON y fingerprint v1 exactos, deliveries, results y tombstones; añade un
checksum independiente de metadatos. Journal corrupto: falla cerrado y rollback.

Los enums previos mantienen sus ordinales; Unknown/Expired se añaden al final.
Nuevos contratos exigen actor/tipo/origen y entran en Received, luego Ready de
forma explícita. La tabla local y su trigger bloquean mutación de identidad y
reactivación de terminales. El fingerprint v1 mantiene su serialización histórica;
v2 comparte el canon Python. Una transacción durable fija Printing **antes** de
cualquier posible callback de ejecución, conservando la protección previa.
Restart con Printing sin recibo se presenta como Unknown y no ejecuta de nuevo.

Solo se usaron tests unitarios del almacén con callbacks controlados existentes;
no se conectaron esos callbacks con routing, transporte o Windows spooler.
No se publicó ni abrió el agente real; su journal real no fue migrado en esta fase.

## Validación temporal y resultados

PostgreSQL 16 desechable: `atlas-print69-qa-pg`, sin puertos publicados, almacenamiento
tmpfs, host/base exactos protegidos por guard en el harness. Sin acceso a DB oficial.

`backend/tests/validate_print_contract_postgres.py` validó:

- 0068 → 0069 → 0068 → 0069;
- huellas de **104 tablas históricas** preservadas, cero tablas/secuencias nuevas;
- dos jobs v1 no vacíos, una entrega y un resultado preservados;
- ocho creaciones concurrentes → un job;
- ocho entregas concurrentes → una entrega activa;
- ocho resultados concurrentes → un resultado, Unknown sin reejecución;
- mutación SQL y reactivación terminal rechazadas;
- FK actor/source cross-tenant rechazada;
- downgrade con v2 rechazado atómicamente.

Este es el harness vigente del candidato. El validator de 0068 se conserva como
evidencia histórica de aquella fase; no usar sus llamadas internas antiguas para
certificar el contrato v2.

Todos los casos del fixture de persistencia/contrato se ejecutaron tanto sobre
SQLite como sobre este PostgreSQL realmente migrado, no solo `create_all`.

- Backend focal: **114 passed, 0 failed**.
- Agent focal: **18 passed, 0 failed** (state model, durable store y extensión).
- Agent completo final: **91 passed, 1 skipped, 0 failed** (92 descubiertos); el
  opt-in de registry HTTP real quedó omitido, sin endpoint/código de pairing.
- Agent build: **0 errores, 0 advertencias**.
- Python compile, Compose config y `git diff --check`: PASS. Git informa solamente
  una advertencia de conversión LF/CRLF en Agenda, ajena a esta fase.
- Backend completo: **750 passed, 29 skipped, 0 failed**, 1115.88 segundos.
  Se habilitaron las variantes PostgreSQL del contrato; otras suites opt-in
  permanecieron omitidas. La ejecución emitió 15966 avisos, principalmente
  deprecaciones de dependencias/usos de fecha de la suite; no se interpretan como
  certificación de ausencia de deuda técnica. No se cambiaron dependencias en esta fase.
- Frontend: no se modificaron contratos/UI visibles; suite/build frontend no
  corresponden a esta fase, conforme al alcance solicitado.

## Archivos de esta fase

- `backend/alembic/versions/0069_print_job_contract.py`
- `backend/app/models/print_contract.py`, `print_job.py`, `local_agent.py`
- `backend/app/services/print_jobs.py`
- `backend/tests/test_print_job_persistence.py`, `test_print_job_contract.py`,
  `validate_print_contract_postgres.py`, `fixtures/print-intent-v2.json`
- `agent/Atlas.LocalAgent.Core/PrintJobs.cs`
- `agent/Atlas.LocalAgent.Service/DurablePrintJobStore.cs`, `PrintIntentFingerprint.cs`
- `agent/Atlas.LocalAgent.Tests/PrintContractTests.cs`, `DurablePrintingTests.cs`,
  `FoundationTests.cs`, `Atlas.LocalAgent.Tests.csproj`
- Este documento y enlace en `README.md`.

Las modificaciones anteriores del resto del workspace no pertenecen a esta fase.
`.env` y Compose conservaron sus hashes iniciales:

- `.env`: `<SHA256>`
- Compose: `<SHA256>`

El cierre de solo lectura confirmó cero jobs/deliveries/results y ausencia de la
columna candidata `requested_by` en la base oficial. PostgreSQL healthy;
health backend 8001, docs, frontend 5174 y health HTTPS Tailscale: HTTP 200.

## Cierre y siguiente paso

```text
RESULT=PASS
MIGRATION_READY=YES
PRINTJOB_STATE_MODEL_READY=YES
IMMUTABLE_INTENT_READY=YES
AGENT_STORE_COMPATIBLE=YES
```

El runner de pruebas terminó y se retiró exclusivamente `atlas-print69-qa-pg`,
verificando antes su etiqueta, nombre exacto y almacenamiento tmpfs. Sus datos QA
efímeros se descartaron; no hay contenedores de esta fase ni procesos Agent activos.
No se crearon fixtures en la base oficial. Estado Git final: 387 entradas pendientes,
incluyendo las 381 anteriores; HEAD sin cambios.

Verificación final: current oficial **0068_print_job_persistence**, head del código
**0069_print_job_contract**, target oficial **0068_print_job_persistence**. Jobs,
deliveries y results: **0/0/0**. Ninguna de las seis columnas candidatas existe en
la base oficial. `.env`/Compose idénticos a sus hashes iniciales; health final PASS.

Antes de activar: revisión controlada de este candidato, backup y autorización
separada para 0069. Después podrá plantearse una microfase de integración routing
con fakes; no se ejecuta aquí. Un resultado técnico favorable no valida routing,
impresión física ni entrega de documentos reales.

No activación oficial, target oficial 0068 sin cambios, no routing, no envío al spooler real,
no impresión, no segunda estación, no listener LAN, no 0070, no commit/push/deploy.

Trabajo detenido al entregar este candidato; no se continúa con su activación.
