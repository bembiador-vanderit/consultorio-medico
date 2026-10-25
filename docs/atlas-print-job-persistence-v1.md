# Persistencia de trabajos de impresión V1 — preparación 0068

Nota posterior: la revisión `0068_print_job_persistence` requiere activación
controlada por instalación. Las referencias a base/target 0067 en este documento
son el cierre histórico de preparación, anterior a esa activación.

RESULT=PASS

MIGRATION_READY=YES

SERVER_PRINTJOB_PERSISTENCE=YES

AGENT_DURABLE_STORE=YES

DURABLE_IDEMPOTENCY=YES

## Límite de esta microfase

Workspace `<WORKSPACE>`, rama `feat/complete-care-context`, HEAD
`3646b6bd7689d7f49941a8254ec327c3eda5682e`.
Current/head inicial: `0067_local_agent_registry`.
Nueva única head del código: `0068_print_job_persistence`.
**La base oficial y su target de arranque siguen en 0067.**

Implementación de persistencia, servicios internos y pruebas con metadatos
sintéticos. No se expone una nueva API HTTP, no se conecta el executor real,
no se activa entrega/polling ni routing Web/mobile/tablet. Tampoco se modifica
el journal JSON de la prueba física histórica. Antes de habilitar routing será
necesario integrar estos servicios con autenticación/autorización explícita y
entrega segura de artefactos; no basta conocer un agente o una impresora.

## PostgreSQL: tres responsabilidades

| Tabla | Responsabilidad |
| --- | --- |
| `print_jobs` | UUID global lógico e intención inmutable: organización, centro, agente, impresora, referencia opaca, SHA256, formato, copias, expiración y estado. |
| `print_deliveries` | Intentos numerados por job, UUID de entrega, lease, recepción del resultado. No es otro trabajo imprimible. |
| `print_results` | Un resultado durable por job, entrega original, outcome, ID del spooler opcional y código de error sanitizado. |

No contiene bytes de documentos, URLs, pacientes, tokens ni información financiera.
No usa auditorías o tablas financieras como cola. El resultado no afirma que
`submitted` equivale a papel impreso: solo registra la entrega al spooler.

0068 crea estas tres tablas y dos constraints únicos en el registro de agentes e
impresoras. Estos permiten FKs compuestas que fijan organización/centro/agente y
organización/agente/impresora en la propia base. No modifica filas históricas,
permisos, seeds, finanzas ni esquema clínico. No crea secuencias nuevas.
Downgrade retira únicamente estas estructuras; **nunca ejecutarlo oficialmente
en esta microfase**. Un downgrade futuro perdería los trabajos creados en 0068 y
necesita su propio procedimiento de respaldo, no es limpieza operacional.

## Servicio e idempotencia

`services/print_jobs.py` no concede permisos: el caller debe autenticar, comprobar
la autorización sobre documento/centro/estación/impresora y después invocarlo.
El servicio exige una sesión tenant-bound, comprueba destino no revocado y
pertenencia de impresora. No existe endpoint nuevo que permita saltar ese paso.

- Register usa UUID único global e INSERT ON CONFLICT. Misma intención devuelve
  el mismo job incluso si la impresora deja de estar disponible o vence su TTL;
  esto recupera un recibo, no autoriza otra impresión. Intención distinta con el
  mismo ID devuelve conflicto 409. Jobs nuevos expirados se rechazan.
- La transacción bloquea la fila del job al entregar, cancelar o registrar el
  resultado. El caller es dueño de commit/rollback.
- Mientras el lease de 60 segundos siga vigente, un poll concurrente o respuesta
  perdida devuelve la misma entrega. Tras expirar puede haber otra entrega,
  **siempre del mismo PrintJobId**. No genera otra impresión lógica.
- El agente responde con su recibo durable. La primera respuesta persiste un
  resultado; ACKs repetidos coherentes no lo duplican. La única progresión de
  resultado admitida es submitted → printed, mismo spool ID no nulo y sin error.
  Un ACK submitted posterior no hace retroceder printed. Otro resultado
  contradictorio devuelve 409. Se admite ACK tardío de una entrega previa legítima.
- Job expirado no se vuelve a entregar. Cancelar antes de entregar lo deja
  `cancelled`; después queda `cancel_requested`, no promete cancelar Windows.
- Outcomes: submitted, printed, failed, unknown, cancelled, expired. Estados
  iniciales/de tránsito: queued, delivering, cancel_requested.

## SQLite local del agente

`DurablePrintJobStore` reutiliza el contrato Core `PrintJob` y lo envuelve con
organización, centro, expiry y SHA256. Dependencia: `Microsoft.Data.Sqlite 10.0.13`.
El almacén queda fijado a una estación/organización/centro; reabrirlo con otro
contexto falla. Referencias de artefacto e impresora son opacas.

Tablas locales separadas: identidad del store, jobs/intención, deliveries y
results. Se usa WAL, `synchronous=FULL`, FKs y transacciones IMMEDIATE; el bloqueo
lo resuelve SQLite, no un lock de UI o un diccionario en memoria. Cada operación
usa su propia conexión y no depende de un singleton del proceso.

Se conserva la intención serializada sin documento, su hash, TTL y tombstone.
`Pending` y `Load` permiten recuperar metadatos listos tras reinicio sin otra
entrega. Distintas entregas conservan un único job y un único resultado.
Los IDs no se eliminan ni se reciclan automáticamente. No mover, borrar o
recrear el almacén para intentar reimprimir: invalidaría la evidencia local.

### Frontera inevitable con Windows

Se confirma durablemente `printing` **antes** de invocar el executor. Una vez
reclamado, ningún retry vuelve a invocarlo. Si hay respuesta perdida después de
guardar el resultado, se devuelve el recibo anterior. Si el proceso muere después
de reclamarlo y antes de guardar el resultado, se devuelve `unknown` /
`OUTCOME_UNKNOWN`, sin re-spool automático. Incluso una excepción del driver
puede ocurrir después de aceptar el papel: no se asume que reintentar sea seguro.

Esta estrategia garantiza **at-most-once dispatch lógico con el store preservado**,
no una transacción exactly-once física entre SQLite y Windows. Puede requerir
conciliación humana de un trabajo desconocido y puede sacrificar disponibilidad
antes que duplicar papel. Una reimpresión deliberada requiere un nuevo ID y su
autorización futura. No se afirma impresión física ni cancelación física.

Las pruebas usan callbacks falsos. El almacén nuevo no está conectado a la
instancia real ni reemplaza el journal sintético existente. No se importan ni
reenvían trabajos históricos; la integración futura deberá asegurar un único
coordinador y no dos rutas ejecutoras paralelas para el mismo ID.

## Validación temporal

Contenedor PostgreSQL 16 efímero `atlas-print68-qa-pg`, sin puertos publicados,
datos en tmpfs y URL comprobada por el harness antes de ejecutar Alembic.
No comparte volumen de datos con Atlas oficial.

- Roundtrip: **0067 → 0068 → 0067 → 0068 PASS**.
- Tablas: 102 → 105; secuencias nuevas: 0.
- Huellas de 101 tablas históricas (excluye alembic_version): idénticas en cada paso.
- Tres tablas nuevas inicialmente vacías.
- 8 creates concurrentes: un job.
- 8 deliveries concurrentes: una entrega vigente.
- Reconnect/lease vencido: segundo intento, mismo job.
- 8 ACKs concurrentes: un resultado.
- FKs PostgreSQL rechazan centro/impresora fuera de scope, tenant aislado.
- Conflicto de intención 409 y rollback sin estado parcial: PASS.

## Suites y tooling

- Backend focal final: **64 PASS / 0 FAIL** (14 pruebas propias de persistencia y
  50 de registro, comunicación segura y proxy).
- Python optimizado `-O`: **14 PASS / 0 FAIL**; las validaciones y el guard de DB
  temporal no usan assertions.
- Backend completo: **696 PASS / 29 SKIP / 0 FAIL**, 954.55 segundos. La suite se
  lanzó antes de las últimas ampliaciones de casos/estados; después se ejecutó
  de nuevo toda la regresión focal final (64 PASS), que cubre los 14 casos propios
  y el código final. No se representa esa ejecución larga como una segunda suite
  completa posterior a los últimos cambios.
- Agente completo, excluyendo exclusivamente el opt-in HTTP externo no solicitado:
  **85 PASS / 0 FAIL / 0 SKIP**. Incluye 11 pruebas SQLite nuevas y 74 anteriores.
- Frontend completo, sin cambios de fuentes frontend: **513 PASS / 0 FAIL**.
- Build solución Agent con analyzers y warnings-as-errors: **0 errores / 0 warnings**.
- NuGet audit de dependencias directas y transitivas del Service: sin paquetes
  vulnerables reportados por los orígenes consultados.
- Frontend build: PASS; aviso de bundle >500 kB. La suite muestra avisos de keys
  repetidas en AgendaMiniCalendar, componente no modificado aquí.
- Backend focal muestra warnings de deprecación (incluido datetime.utcnow del
  patrón UTC-naive existente); no se ocultan como errores ni se modifica el
  esquema temporal/UTC del registro de agentes durante esta fase.
- Python compile, Compose config y git diff --check: PASS. Git avisa conversión
  LF/CRLF en AgendaMonthPanel, archivo ajeno a esta microfase; no se reformatea.

Los 29 skips corresponden a suites opt-in del workspace; no se habilitan fixtures
que puedan comunicarse con instancias externas. PostgreSQL real de esta fase se
valida mediante el harness explícito descrito arriba. La suite completa reportó
14794 warnings de deprecación; no hubo fallos.

El contenedor temporal y sus dos bases tmpfs sintéticas se retiraron al finalizar
las pruebas. No se conservan jobs o credenciales QA en la base oficial.

## Cierre oficial, solo lectura

- Current oficial: `0067_local_agent_registry`; head código preparada: 0068.
- Oficial: 102 tablas / 92 secuencias, sin las tres tablas print_* nuevas.
- `ALEMBIC_TARGET_REVISION` oficial continúa en 0067.
- SHA256 de .env sin cambios:
  `<SHA256>`.
- SHA256 de Compose sin cambios:
  `<SHA256>`.
- PostgreSQL healthy, backend health 200, docs 200, frontend 200.
- No se reiniciaron ni recrearon servicios oficiales ni el stack paralelo.
- No se activa 0068 ni routing remoto en este cierre. Requiere otra autorización.

## Archivos de la microfase

- `backend/alembic/versions/0068_print_job_persistence.py`
- `backend/app/models/print_job.py`, import en `models/__init__.py`
- `backend/app/models/local_agent.py`: dos claves únicas de scope
- `backend/app/services/print_jobs.py`
- `backend/tests/test_print_job_persistence.py`
- `backend/tests/validate_print_job_postgres.py`
- `agent/Atlas.LocalAgent.Service/Atlas.LocalAgent.Service.csproj`: SQLite
- `agent/Atlas.LocalAgent.Service/DurablePrintJobStore.cs`
- `agent/Atlas.LocalAgent.Tests/DurablePrintingTests.cs`
- README y este documento.

El workspace tenía 374 entradas pendientes antes de empezar; se preservaron.
Al cierre de implementación hay 380 entradas (incluyen los directorios agent/
y otros cambios históricos aún sin versionar); no equivalen a 380 cambios propios.
HEAD se conserva. No se hizo limpieza de cambios previos.

No hay cambio de configuración oficial, pairing, credencial DPAPI, identidad,
servicio permanente, impresión física, 0069, commit, push ni deploy.

Referencias técnicas:
[transacciones Microsoft.Data.Sqlite](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions),
[errores y bloqueo](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/database-errors),
[paquete Microsoft.Data.Sqlite](https://www.nuget.org/packages/Microsoft.Data.Sqlite/10.0.13).
