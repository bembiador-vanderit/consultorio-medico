# Official Physical Execution Bridge V1 — gate de un solo trabajo

Fecha: 21/10/2026. Workspace `<WORKSPACE>`, rama `feat/complete-care-context`, HEAD `3646b6bd7689d7f49941a8254ec327c3eda5682e`.

## Alcance y límite

Implementación y pruebas exclusivamente no físicas. No se ha autorizado ningún UUID, creado un trabajo físico oficial, enviado contenido al spooler, impreso papel ni instalado un servicio. La revisión oficial continúa en `0069_print_job_contract`; esta fase no crea 0070.

Se retomaron los cambios parciales de la sesión que quedó read-only, sin reset ni descarte de trabajo ajeno. La nueva instrucción adjunta confirma 0069 y sustituye la referencia 0068 de la reanudación anterior. Se verificó escritura mediante archivo temporal creado/leído/eliminado; Windows/WMI y SQLite son accesibles de nuevo.

## Diseño

Se conserva **un consumidor oficial**, un flujo de estados y el backend nativo GDI existente:

`OfficialPrintConsumer → PrintRoutingWorker → SQLite → IPrintExecutionPolicy → FakePrintExecutor / IPhysicalPrintExecutor → WindowsGdiPrintBackend`.

`FakePrintRoutingWorker` queda como wrapper de compatibilidad de los harness anteriores, sin ejecutor físico. No es otro consumidor ni otra cola. Se conservan el lock por directorio del proceso, HTTPS estricto, DPAPI y el registro existente.

### Política local independiente

Tres decisiones explícitas: `SafeValidation`, `PhysicalDenied`, `PhysicalAllowed`.

- `synthetic_test` conserva SafeValidation: nunca se reinterpreta un recibo simulado como impresión física.
- Una intención física usa **otro UUID**, `document_type=physical_routing_qa`, referencia `physical-routing-qa`, GENERAL, plain_text, WEB_DESKTOP y sin source_agent.
- Default: autorización deshabilitada, UUID/estación/impresora no definidos. Estar Online, tener HTTPS, pertenecer al tenant o ver la impresora NO autoriza ejecución.
- La autorización liga UUID exacto, GUID del Agent, organización/centro, identidad estable de impresora, huella de capabilities/driver, hash de intención y contenido, una copia y ventana temporal.
- `ValidFrom` y `ExpiresAt` deben delimitar una ventana positiva de máximo cinco minutos; job y autorización deben seguir vigentes. Estados terminales, receipt-only y UNKNOWN no son elegibles.
- Se vuelve a evaluar al preparar, inmediatamente antes de la barrera durable y antes de StartDoc. No hay fallback de impresora.

Configuración operativa del Agent: argumento explícito `--physical-authorization-file RUTA_ABSOLUTA_LOCAL`, solo junto al routing seguro. No hay endpoint HTTP, comando del pipe ni botón Web para establecerla. El lector rechaza rutas de red, archivo reparse, tamaño >8 KiB y campos desconocidos. Se considera configuración del operador local confiable, no un mecanismo de defensa contra un administrador que pueda modificar el propio programa.

Campos del modelo: Enabled=false; AllowedJobId=null; AllowedAgentId=null; AllowedPrinterId=null; ExpectedPrinterName opcional; PrinterFingerprint; OrganizationId; CenterId; MaxCopies=1; IntentHash; ContentSha256; ExecutionMode=Disabled; ValidFrom=null; ExpiresAt=null; PageFormat=A4. No contiene secretos. **No se creó un archivo de autorización habilitada en el runtime oficial.**

`--allow-physical-print` no se combina con routing seguro y no es una solución para esta fase. El coordinador local de pruebas sigue deshabilitado. Tampoco se permiten fault-injection flags de simulación al cargar una autorización física habilitada.

### Adaptador y huella local

`PhysicalPrintExecutor` implementa `IPhysicalPrintExecutor`, reutilizando `ILocalPrintBackend`. La implementación nativa continúa siendo `WindowsGdiPrintBackend`; no hay shell print ni navegador automatizado.

La enumeración fresca resuelve la impresora por `RegistryId` (no solo nombre). La huella incluye identidad, driver, conexión, virtualidad, color, dúplex, máximo de copias y tamaños/papers ordenados. Nombre esperado puede verificarse adicionalmente. Se rechazan identidad/driver/papel cambiado, dispositivo virtual, estados de error, estación distinta y runtime no conectado/revocado.

Se genera solo un layout sintético acotado con UUID, estación, impresora, origen, ejecución QA y timestamp. No se renderizan bytes clínicos ni archivos arbitrarios descargados. La descarga oficial sigue validando SHA-256; no se persisten sus bytes. El driver recibe una copia privada de DEVMODE para una sola página/copia, sin modificar impresora predeterminada ni settings globales.

### Persistencia antes de ejecución

Se reutilizan jobs, deliveries, results e identidad/scope SQLite v2. Se añade localmente `physical_executions` (sin migración PostgreSQL):

- PK por job; FK a job y delivery.
- delivery/attempt exacto, impresora, formato de papel, huella del driver/capabilities, copies=1 y started_at.
- spool_id y accepted_at cuando Windows acepta.
- estado final en jobs/results, intención/format/hash en metadata inmutable y estación/tenant en store_identity.

La transición Ready → Printing y el INSERT de evidencia física se confirman **en la misma transacción SQLite antes del callback nativo**. Otra conexión no puede reclamar otra ejecución. Un semáforo compartido por los workers del proceso evita interpretar una ejecución en curso como crash recovery; la protección durable y el process lock siguen siendo necesarios, no se sustituyen por ese semáforo.

El callback de aceptación conserva spool ID incluso si luego falla el driver. SQLite no guarda bytes del documento, credenciales ni PHI. Los tombstones no se borran al reiniciar.

### Resultados y recovery

- Validación/preflight fallida: Failed antes de spool, sin evidencia física ni llamada de envío.
- Después de la barrera irreversible, una excepción es conservadoramente Unknown, con spool ID si se conoció. No hay retry físico automático.
- EndDoc correcto es Submitted, no Printed. Una cola vacía/entrada desaparecida tampoco prueba salida física.
- Solo una observación `ReportedPrinted` compatible permite Printed. Redelivery de Submitted puede observar el recibo, nunca reenviar.
- Printed, Submitted, Unknown, Cancelled, Expired y Failed se recuperan desde SQLite sin llamar Execute otra vez. Pérdida de ACK no borra el resultado local.
- Si el driver elimina la entrada sin informar Printed, se conserva Submitted/revisión; no se inventa éxito ni se imprime una copia para verificarlo. La certificación física y cualquier confirmación humana posterior están fuera de esta fase.

## Backend mínimo, sin nueva DB

La API oficial conserva `physical_execution_enabled=false` como capacidad **global**. Se añade `physical_execution_authorized` por job; no autoriza al Agent por sí sola.

El servidor puede cargar un grant temporal desde `ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE`, inexistente/no configurado en la instancia oficial. Archivo local acotado, sin campos desconocidos; no se acepta configuración del cuerpo HTTP. La creación física requiere además los permisos existentes documents:print, local_agents:view/manage y todos los scopes actuales. El fingerprint vincula también actor y expiración exacta. No se añade rol, permiso ni migración.

Para `physical-routing-qa`, solo un UUID/destino/copia/origen exactos con hash esperado se puede registrar. Se vuelve a comprobar el grant al descargar; retirarlo bloquea la descarga. El Agent conserva su gate local independiente. El estado histórico y los recibos pueden leerse sin reactivar la autorización.

Una creación válida añade `print_job.physical_authorized` a la auditoría existente, junto con actor, contexto, UUID/fingerprint y execution_mode físico QA. Consultar no crea eventos falsos de modificación. El Agent registra decisión/mode/reason allowlisted en `execution-decisions.jsonl`, sin contenido, tokens ni excepciones del driver.

No cambia frontend, su botón sigue siendo «Validar sin imprimir» y no ofrece intención física. La futura prueba será técnica y por un solo UUID autorizado explícitamente, no un toggle público.

El Agent carga la autorización local al arrancar; la ventana de cinco minutos sí se reevalúa en ejecución. Para retirar anticipadamente ese grant local se detiene/reinicia el proceso sin el argumento de autorización (no basta con borrar un archivo ya leído). El servidor relee su archivo por solicitud; retirarlo impide nuevas creaciones/descargas. No se promete revocación transaccional de papel ya entregado al driver.

## Archivos de esta microfase

Se preservan todos los cambios anteriores ajenos a la fase. Solo se continúa/modifica:

- `agent/Atlas.LocalAgent.Core/SyntheticPrinting.cs`: layout sintético QA oficial.
- `agent/Atlas.LocalAgent.Service/PhysicalExecutionPolicy.cs`: política/configuración/default-deny e interfaz común.
- `agent/Atlas.LocalAgent.Service/PhysicalPrintExecutor.cs`: adaptador físico y fingerprint, sin otro motor.
- `agent/Atlas.LocalAgent.Service/FakePrintRouting.cs`: workflow compartido; fake sigue como default.
- `agent/Atlas.LocalAgent.Service/OfficialPrintConsumer.cs`: composición de la política local y log sanitizado.
- `agent/Atlas.LocalAgent.Service/DurablePrintJobStore.cs`: evidencia previa y aceptación de spool.
- `agent/Atlas.LocalAgent.Service/WindowsGdiPrintBackend.cs`: referencia QA oficial sobre el motor existente.
- `agent/Atlas.LocalAgent.Service/Program.cs`: argumento operativo y diagnóstico read-only.
- `agent/Atlas.LocalAgent.Tests/PhysicalBridgeTests.cs`: pruebas nuevas con mocks.
- `backend/app/services/physical_print_authorization.py`: grant operativo server-side.
- `backend/app/services/print_routing.py`: resolver/preparación de intención física QA y capacidad por job.
- `backend/app/api/routes/print_routing.py`: delegación de preparación al policy existente.
- `backend/app/services/print_jobs.py`: etiqueta de auditoría física QA, sin otra cola/auditoría.
- `backend/tests/test_official_print_routing.py`: regresión/gates server-side.
- Este documento.

No se modifican frontend, migraciones, Compose, .env ni permisos. Muchos de estos archivos ya eran untracked antes; `git diff` por sí solo no representa su cambio incremental. El inventario de entrada fue 405 líneas de status (sin el probe temporal); el resto del ruido del workspace no se limpió ni se sobrescribió.

## Preparación de impresora (NO autorización)

- Seleccionada: **<PRINTER_NAME>**.
- Driver: <PRINTER_NAME>; predeterminada ya existente, no modificada.
- RegistryId: `<PRINTER_FINGERPRINT>`.
- Fingerprint local: `<SHA256>`.
- Formato preparado: A4, 210×297 mm, driver paper ID 9; límite físico V1: 1 copia. Carta también anunciada, no seleccionada. POS no se asume para esta <PRINTER_NAME>.
- Windows anuncia sin alertas, WorkOffline=false; spooler Running.
- El inventario local puede incluir impresoras físicas, virtuales y PDF. No se modifica ninguna.

`--inspect-bridge-printer NOMBRE` permite inspección nativa read-only sin abrir identidad/DPAPI, empezar consumidor ni enviar trabajo. En esta fase devolvió PhysicalExecutionAuthorized=false y PhysicalPrintsSent=0.

## Verificación y entrega

```text
RESULT=PASS
PHYSICAL_BRIDGE_READY=YES
STRICT_SINGLE_JOB_GATE=YES
SAFEVALIDATION_DEFAULT_PRESERVED=YES
DURABLE_PHYSICAL_IDEMPOTENCY_READY=YES
REAL_SPOOLER_DELTA=0
PHYSICAL_PRINTS_SENT=0
```

PASS de implementación/gates, **no certificación física**. Cero UUID autorizados en el runtime oficial. No se considera haber impreso por obtener un recibo del mock.

| Comprobación final | Resultado |
|---|---|
| Agent focal PhysicalBridgeTests | 33 passed / 0 failed |
| Agent completo | 149 passed / 1 skipped / 0 failed; 150 total |
| Backend focal ampliado con PostgreSQL opt-in | 153 passed / 0 failed; 3185 warnings; 70.00 s |
| Backend completo, PostgreSQL temporal | 789 passed / 29 skipped / 0 failed; 17412 warnings; 1081.25 s |
| Concurrencia HTTP PostgreSQL temporal | 2×200, 1 job, 1 creación auditada, 2 claims/1 lease; cero físico |
| Frontend regresión existente | 29 passed / 0 failed; ningún archivo frontend modificado |
| Frontend completo/build | N/A en esta fase: frontend/contrato de su UI no se modifican |
| dotnet restore | PASS |
| dotnet build/analyzers | 0 errores / 0 advertencias; analyzers habilitados y warnings-as-errors |
| Python compile / Compose config | PASS |
| git diff --check | PASS; aviso LF/CRLF heredado en AgendaMonthPanel |
| CLI de seguridad, combinación global físico + routing | Rechazo código 2 antes de arrancar |
| CLI, grant sin routing seguro | Rechazo código 2 antes de arrancar |

El skip Agent es el test opt-in de registro real; las rutas y executor físicos se probaron únicamente con mocks. Los 29 skips backend son suites opt-in ajenas no habilitadas. Las suites focales de persistencia/contrato sí incluyeron PostgreSQL real temporal. Los warnings Python son deprecaciones existentes de datetime.utcnow, Starlette/AnyIO, ReportLab, WebSockets y avisos de Pydantic; no se suprimieron para obtener PASS.

### Integridad y estado operativo final

- Current/head/target: `0069_print_job_contract`; una sola head, sin 0070. Ninguna migración sobre la base oficial. La base temporal se preparó con las migraciones existentes exclusivamente para tests.
- 105 tablas y 92 secuencias oficiales: todos los schema hashes y secuencias iguales al snapshot anterior. Solo difieren las huellas de local_agents/agent_printers por disponibilidad/heartbeat/sincronización del registro existente. Clínica, finanzas, usuarios, membresías/permisos y auditorías históricas mantienen sus huellas.
- PrintJobs/deliveries/results oficiales siguen en **3/3/3**, los tres sintéticos anteriores. ClinicalAuditLog sigue en 90. No hay un job físico nuevo ni segunda estación; el registro mantiene una estación/diez impresoras.
- SQLite real conserva los tres jobs/resultados previos y `PRAGMA integrity_check=ok`. SHA256 antes/después: `<SHA256>`. La tabla de evidencia nueva se ejercitó en almacenes temporales de tests; no se insertó evidencia física en el SQLite oficial.
- Huellas preservadas: identity.json `<SHA256>`; station.json `<SHA256>`; archivo DPAPI `<SHA256>`.
- .env `<SHA256>` y Compose `<SHA256>` permanecen sin cambios. No se configura ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE.
- Spooler baseline/final: sin IDs nuevos para el trabajo QA; delta real=0, hojas enviadas=0. No se alteraron colas ajenas.
- PostgreSQL healthy; health 8001, docs 8001, frontend 5174 y health HTTPS Tailscale responden 200. No se reinició la DB ni el stack paralelo.
- El Agent actualizado queda manualmente Online en SafeValidation, con máximo de una hora desde su último arranque, sin argumento de autorización ni flag físico general. AllowedJobId=none; physical global disabled. El proceso anterior había vencido; no se creó otra identidad ni se cambió endpoint/pairing/credencial. No se instaló servicio/startup/installer.
- Se retiró el contenedor PostgreSQL temporal `atlas-print69-qa-pg` después de comprobar etiqueta physical-bridge69 y almacenamiento tmpfs sin mounts de datos oficiales. Los runners se eliminan al terminar. No quedan fixtures oficiales nuevos; se conserva toda trazabilidad anterior.
- Snapshot final: `<LOCAL_EVIDENCE_DIR>`. TRX: `agent/Atlas.LocalAgent.Tests/TestResults/physical-bridge-focal.trx` y `physical-bridge-full.trx`.
- Workspace: 405 entradas de status al inicio, 407 al final; los dos nuevos registros visibles son el módulo backend y este documento (el directorio agent ya figuraba untracked). No se limpió el resto del workspace. HEAD permanece igual; NO commit, push ni deploy.

Pruebas nuevas Agent: default-deny y coexistencia, cada mismatch del grant, llamada exacta al spy una vez, concurrencia, evidencia previa, restart, ACK perdido, barrera abandonada sin resultado, spool ID conservado tras excepción, cancelación, expiración durante preparación, fallo antes de spool, revalidación driver/paper/identidad/estación/revocación y lectura de configuración estricta. Las implementaciones físicas se inyectan con backend mock, nunca con Windows autorizado.

Pruebas backend nuevas: default-deny, extra fields/public toggle rechazados, grant técnico de un solo UUID, mismatch de destino/copia/origen/hash/centro/ventana/modo, retirada de grant y auditoría. Se ejecutan en fixtures SQLite y PostgreSQL temporal, nunca creando trabajos oficiales.

No se ha realizado validación física. Siguiente fase separada: preparar un UUID físico sintético nuevo, grants independientes acotados, verificar huellas vigentes, solicitar/recibir autorización humana para una sola hoja y luego restaurar el bloqueo. Nada de esto ocurre automáticamente al terminar esta implementación.
