# Atlas Local Agent — Pairing & Station Registry V1

## Alcance y estado

RESULT=PASS

Nota posterior: la revisión `0067_local_agent_registry` requiere una activación
controlada por instalación. Los resultados y la base 0066
indicados a continuación corresponden al cierre histórico de implementación,
antes de esa activación; no autorizan pairing real.

Implementación de registro y vinculación validada en fixtures y PostgreSQL
temporal, **sin activar la base oficial** ni registrar la PC real en ella.

Base oficial inicial: `0066_document_designer`; única head inicial del código:
`0066_document_designer`. Rama `feat/complete-care-context`, HEAD
`3646b6bd7689d7f49941a8254ec327c3eda5682e`. Workspace `<WORKSPACE>`.
Instancia oficial: 5174 / 8001 / 5433. No se registra la PC real en esa base.

Se conserva la prueba física previa: <PRINTER_NAME>, A4, una hoja, un envío,
spool ID 6. **No se repite impresión física en esta fase**. Los tests automáticos
del motor de impresión siguen utilizando mocks y no envían trabajos Windows.

## Inventario reutilizado

Solución .NET 10: Core, Service, Tray, Tests; SDK 10.0.402, Windows 10 validado.
Se reutilizan `LocalIdentityStore`, GUID persistente, configuración de estación,
`WindowsSecretStore` (DPAPI CurrentUser + ACL), `IPrinterDiscovery`, PrintJob y su
journal, log tipado, IPC owner-only con rechazo remoto, estados y abstracciones
cloud/LAN. Foundation y impresión local no se reconstruyen.

Agente `1.2.0-dev`, protocolo local/registro `3`: actualizar Service y Tray juntos.
El host sigue ejecutándose manualmente; no se instala servicio Windows,
autoarranque, tarea programada ni instalador.

## Identidad y contexto

- `agent_uuid`: GUID global único; no editable ni reemplazado ante corrupción.
- `display_code`: código legible, no es secreto ni autoridad.
- `station_name`: nombre amigable; cambios del registro requieren permiso.
- `fingerprint`: SHA-256 de marcador de instalación (GUID + fecha de creación).
  No usa MAC, serial, IP, usuario Windows ni inventario invasivo. Detecta cambios
  del marcador; **no demuestra identidad de hardware** ni distingue una copia
  íntegra del directorio. DPAPI limita reutilización de secretos a usuario/máquina.
- Organización y centro/grupo vienen del código creado por un gestor autenticado
  en el host de tenant. El payload del agente **no acepta organization_id**.

Jerarquía: organización → centro → grupo → estación. `AgentWorkgroup` es un grupo
operativo, no un rol clínico, usuario, médico responsable o dependencia de red.
Dos PCs en redes locales distintas pueden compartir grupo mediante
Internet sin estar en la misma LAN, sin VPN, IP pública o port forwarding.

## Modelo y migración

Nueva revisión: `0067_local_agent_registry`, depende de `0066_document_designer`.
No existe 0068. Cinco tablas aditivas:

| Tabla | Función |
| --- | --- |
| agent_workgroups | Organización, centro, nombre y actor/fecha de creación. |
| local_agents | UUID global único, nombre/código, organización/centro/grupo, versión/protocolo, fingerprint, hash y revisión/expiración de credencial, salud, pairing, última conexión, revocación y timestamps. |
| agent_pairing_codes | Hash único del código, alcance fijado, emisor, creación, expiración y consumo. |
| agent_printers | Agente + ID local únicos, nombre, driver, conexión, virtual/default, estado, papeles, disponibilidad y last_seen. |
| authorized_station_scopes | Grant direccional explícito source → target, organización, actor/fecha; no auto-relación. |

FKs RESTRICT e índices de organización; UUID y hash de credencial globalmente
únicos; unicidad de grupo por organización/centro/nombre y de impresora por agente
e ID local. La validación de alcance y FKs se aplica también mediante el guard
multi-tenant SQLAlchemy existente. No se cambian tablas clínicas/financieras.

La migración agrega `local_agents:view` y `local_agents:manage`, inicialmente solo
al rol administrador. Bootstrap solo crea estos permisos cuando las tablas están
activadas y **no restaura una revocación posterior**. En 0066 no agrega permisos.
El downgrade temporal retira estas tablas y estos grants específicos; no se
ejecuta downgrade oficial.

## Pairing y credencial

Administración → Agentes y dispositivos → elegir centro/grupo → crear código.
El Tray incorpora «Vincular con Atlas»: dirección HTTPS, código y excepción local
de desarrollo explícita. No pide usuario/contraseña de Atlas.

Códigos: 128 bits aleatorios, Base32 agrupado para lectura, vigencia **5 minutos**,
un solo uso, SHA-256 en DB, nunca texto plano persistido. La UI conserva el código
solo en memoria, lo oculta al vencer o cerrar, sin localStorage/sessionStorage.
La respuesta se marca no-store. Se revalida permiso/membresía del emisor al
consumirlo; un código expirado/usado/revocado por pérdida de permiso se rechaza.
La longitud evita depender de un código corto de ocho caracteres adivinable.

Un bloqueo de organización serializa consumo y alta; la unicidad global del UUID
impide reasignación o robo de identidad incluso entre tenants. Dos submits con
el mismo código producen una estación: un éxito y un rechazo. UUID ya registrado
con otro código: 409, sin sobrescribir credencial, tenant o asociación.

Credencial propia `ala_` + 256 bits aleatorios, expiración **90 días**, hash SHA-256
en servidor. No es JWT de usuario ni concede acceso a los endpoints clínicos.
El agente guarda token, endpoint y asociación en DPAPI CurrentUser, no JSON plano,
.env, logs o configuración pública. El IPC solo devuelve estado/asociación, no
token. Las representaciones de solicitudes sensibles están redactadas.

Renovación explícita desde Tray: credencial anterior válida, bloqueo de fila,
nuevo secreto, revisión incrementada, anterior invalidada y evento auditado.
Revocación administrativa con motivo es irreversible en V1: no permite heartbeat,
catálogo, rotación o peers. No hay reactivación automática.

Si se pierde respuesta de pairing/rotación después del commit, o falla el guardado
DPAPI, no se presume éxito ni se reemplaza automáticamente identidad. El mensaje
indica resultado incierto/consultar administrador. Recuperación administrativa de
credencial perdida y rotación con acuse transaccional son endurecimiento futuro;
se prefiere fallo cerrado a duplicar o apropiarse de una estación.

## Heartbeat y catálogo

El proceso consulta DPAPI al refrescar. Sin credencial permanece Unpaired y no
contacta Atlas. Con credencial inicia conexiones **salientes** a Atlas.
Intervalo existente: **30 segundos**. El backend calcula offline tras **120
segundos** sin last_seen o credencial vencida. No depende de un heartbeat perdido.
Precedencia de estados: revoked → offline → degraded/online. Un servidor caído
no borra la credencial; la reconexión reutiliza la identidad. Un 401/403 frena los
intentos de esa instancia y se muestra credencial inválida/revocada.

Heartbeat no contiene datos clínicos: UUID, versión/protocolo, nombre/código y
marcador de instalación, salud y resumen acotado de impresoras/predeterminadas.
No puede cambiar organización/centro/grupo o nombre
administrativo. La respuesta devuelve asociación efectiva; cambios administrativos
de centro/grupo actualizan la asociación local protegida. No audita cada heartbeat.

Después del heartbeat se sincroniza inventario completo acotado. Si discovery
local falla, no se envía una lista vacía falsa: se conserva el catálogo previo y
se reporta degraded. Impresoras virtuales se registran como virtuales, no físicas.
Desaparecidas: `available=false`, conservando ID/historia/last_seen; su retorno
reactiva la entrada y se audita una vez. No borra ni configura impresoras Windows.

Identidad de catálogo: hash normalizado de puerto + driver + share (y nombre para
virtuales o fallback sin puerto). Windows `PRINTER_INFO_2` aporta esa metadata.
Renombrar una cola física con puerto/driver/share constantes conserva identidad;
cambiar driver/puerto puede crear otra. No existe garantía universal de identidad
física: dos colas indistinguibles pueden colisionar; el backend rechaza IDs
duplicados en un sync en vez de fusionarlos silenciosamente. La versión del hash
permite evolución futura. No se cambia `DeviceId` ni el journal de impresión local
ya validado; `RegistryId` es metadata adicional del mismo catálogo.

## Autorización, red y auditoría

**SAME LAN != AUTHORIZED; SAME ORGANIZATION != AUTOMATICALLY AUTHORIZED.**
Ni mismo grupo, mismo centro, IP, peer descubierto o credencial de dispositivo
conceden acceso a otra estación, impresora remota o historial clínico.

`local_agents:view`: catálogo del tenant; `local_agents:manage`: crear grupos/
códigos, revocar, configurar asociación y autorizar discovery explícito. No se
reutilizan permisos financieros. Solo administrador recibe defaults iniciales;
permisos individuales denegados y membresías/horarios existentes siguen vigentes.
La UI oculta controles sin permiso; backend siempre vuelve a autorizar.

`authorized_station_scopes` es direccional: A ve B solo con grant explícito; no
implica B ve A. Propia estación permitida; otra del mismo grupo no se incluye por
defecto. El endpoint peers filtra tenant y revocados y devuelve
`print_routing_allowed=false` **siempre**. Cambiar grupo/centro retira grants
previos en ambas direcciones. El catálogo administrativo no es permiso de routing.

LAN discovery permanece la abstracción simulada existente: no crea grants,
credenciales o PrintJobs. `DenyAllAuthorizationPolicy` sigue rechazando routing
(`PrintRoutingNotEnabled`). Futuros enlaces Agent ↔ Agent necesitarán cifrado y
autenticación; no se implementan sockets o transferencias LAN/cloud de documentos.

HTTPS obligatorio para pairing y endpoints de dispositivo. Cliente: TLS 1.2/1.3,
validación estándar de certificado, sin bypass, sin redirects/cookies. Excepción
solo desarrollo loopback: checkbox explícito del agente **y**
`LOCAL_AGENT_ALLOW_LOOPBACK_HTTP=true` en API temporal. No permite HTTP en IP LAN.
No se modifica Compose/.env oficial; una futura activación local necesitará definir
esta excepción o TLS. Un reverse proxy productivo debe preservar esquema HTTPS
mediante configuración confiable, no headers arbitrarios del cliente. mTLS queda
preparado como evolución, no certificado ni implantado.

Se reutiliza `ClinicalAuditLog`, sin sistema paralelo: código creado, pairing
exitoso/fallo relevante, grupo creado, revocación, rotación, alta/desaparición/
retorno de impresora, nombre/asociación y scope administrativo. Eventos de agente
identifican UUID/revisión de credencial y actor_kind; cambios administrativos,
usuario y motivo/before/after. No almacena códigos, hashes de credencial o tokens
en context/log. Códigos aleatorios desconocidos se rechazan sin generar una fila
por cada intento no autenticado; códigos conocidos fallidos sí se auditan.
Lectura y heartbeat/sync sin transición no generan falsa auditoría de modificación.

## API V1

Base `/api/v1/local-agents`:

- Usuario: GET `/registry`; POST `/workgroups`, `/pairing-codes`;
  POST `/{id}/revoke`; PUT `/{id}`, `/{id}/discovery-scope`.
- Pairing anónimo con código de alta entropía: POST `/pair`.
- Bearer de dispositivo, no usuario: POST `/device/heartbeat`, `/device/rotate`;
  PUT `/device/printers`; GET `/device/peers`.

Tenant resuelto por host con la infraestructura existente; se rechaza plataforma.
No hay endpoint de impresión o lectura clínica con credencial de estación.
En base 0066 el registro devuelve pendiente de activación, no crea tablas.

## Validación reproducible aislada

`test_local_agents.py`: fixtures sintéticos multi-tenant, HTTPS TestClient.
`validate_local_agent_registry_postgres.py`: guard rígido de host
`atlas-agent67-qa-pg` y DB `atlas_agent67_qa`, nunca oficial. Comprueba
0066→0067→0066→0067, 96 tablas históricas (97 con alembic_version), grants
iniciales aditivos y preservación de filas previas; prueba consumo concurrente
real con dos sesiones PostgreSQL. Cinco tablas nuevas inicialmente vacías.

API QA temporal sin lifespan, seed automático, workers, cuentas reales ni logs
de acceso; loopback 18067. `RegistryTests.RealHttpTemporaryRegistryOnlyWhenOptedIn`
usa exclusivamente ese puerto y código efímero capturado en memoria. Ejecuta
cliente .NET real → HTTP API → PostgreSQL, DPAPI, heartbeat, sync y rotación.
El catálogo es sintético, no otra detección o impresión física <PRINTER_NAME>.

Resultados verificados hasta el cierre de implementación:

| Validación | Resultado |
| --- | --- |
| Agente .NET, incluyendo HTTP real temporal y DPAPI | 64 PASS, 0 FAIL, 0 omitidas |
| Backend focal final | 8 PASS, 0 FAIL |
| Backend completo | 642 PASS, 29 omitidas opt-in, 0 FAIL; 1652.71 s |
| Frontend focal | 8 PASS, 0 FAIL |
| Primer frontend completo | 501 PASS, 0 FAIL; nuevas 8 focales además |
| Frontend completo final | 509 PASS, 0 FAIL, 0 omitidas; 320.03 s |
| Build .NET / analizadores | PASS; 0 errores, 0 warnings |
| Publish win-x64 self-contained Service + Tray | PASS; `agent/artifacts/pairing-v1/win-x64` |
| Frontend build | PASS; advertencia conocida de chunk >500 kB |
| PostgreSQL roundtrip final | PASS, 96 tablas históricas + alembic_version preservadas |
| Consumo concurrente PostgreSQL | PASS: 200 + 403, una estación y un código consumido |
| Python compile / Compose config / diff check | PASS |

Prueba del panel en fixture aislada: escritorio y 390 px, agrupación, estados,
detalle/modal de solo lectura y nombres largos. Sin overflow horizontal: documento
375/375 px (scrollbar) y modal de 374 px dentro del viewport 390 px. Se restauró
viewport y se cerró la pestaña QA. No se usaron sesiones o datos oficiales.

Evidencia .NET: `agent/Atlas.LocalAgent.Tests/TestResults/pairing-registry-accepted.trx`
(ignorada por Git). La prueba negativa de identidad ajena detectó una excepción
no encapsulada; se corrigió el manejo tipado y la repetición final pasó 64/64,
sin guardar esa credencial. No se oculta esa iteración como un éxito inicial.

El primer y segundo roundtrip usaron DB temporales explícitas `atlas_agent67_qa`
y `atlas_agent67_final_qa`; el segundo valida el tamaño final del estado del driver.
Ambas están restringidas por guard a `atlas-agent67-qa-pg`. La API HTTP usa solo
la primera. No se incorporan secretos, códigos o credenciales al informe.

La colección backend completa comenzó con seis casos nuevos; después se añadieron
dos casos específicos de movimiento de scope y preservación de revocación de
permisos. Ambos están incluidos en el focal final de ocho PASS. No se suman las
ejecuciones repetidas como si fueran casos diferentes. Las 29 omisiones de la
suite general corresponden a sus condiciones opt-in; el roundtrip y concurrencia
PostgreSQL de esta fase sí se ejecutaron explícitamente.

Advertencias no bloqueantes: 14718 warnings backend (incluyendo deprecaciones del
patrón UTC y fixtures existentes); advertencias de claves duplicadas en fixtures
de Agenda del frontend; chunk de build >500 kB y advertencia LF/CRLF preexistente
en AgendaMonthPanel.tsx. No se modifican esos módulos para ocultar advertencias.
No hubo errores de build o analizadores .NET.

Se detuvieron y eliminaron exclusivamente `atlas-agent67-qa-api`,
`atlas-agent67-qa-pg` y su volumen anónimo validado. Sus datos sintéticos son
descartables; no se eliminó ningún registro o volumen oficial. Ya no queda la
API temporal en 18067. No se vinculó ni revocó ninguna estación oficial.

Evidencia oficial de solo lectura: `/tmp/agent-registry-pre.json`,
`/tmp/agent-registry-post.json`, `/tmp/agent-registry-final.json` y
`/tmp/agent-registry-accepted.json`. Comparación: **97 tablas, esquema, datos y
secuencias sin cambios**, sin tablas nuevas, pérdidas o permisos adicionales.
Current oficial: **0066_document_designer**. Única head del código final:
**0067_local_agent_registry**, no aplicada oficialmente. PostgreSQL healthy;
health/docs 8001 y frontend 5174 HTTP 200. Compose y `.env` oficial sin modificar
por esta fase; target de arranque permanece 0066.

El workspace conserva los cambios pendientes previos. Archivos de esta fase:
modelo/schema/servicio/rutas `local_agent(s)`, migración 0067, registro de modelos
y router, bootstrap protegido; cliente/contratos/IPC/runtime/Tray y tests del
agente, metadata adicional RegistryId; página AgentDevices, CSS, navegación/App,
tests/fixture de UI, este documento y enlace README. No se atribuyen a esta fase
los cambios previos de esos archivos compartidos.

**Cierre:** no impresión nueva, routing remoto, activación 0067 oficial, 0068,
servicio permanente, commit, push o deploy. Detenerse; cualquier activación oficial
o pairing real requiere la siguiente microfase expresamente autorizada.

## Fuera de alcance / siguiente paso

No routing, Print Management, fallback, perfiles de documentos/centro, scanner,
POS/Verifone, WhatsApp, auto-update, PKI/mTLS productivo o servicio permanente.
Windows 11 no certificado. Oficial debe permanecer **0066**.

Siguiente microfase recomendada: revisión y activación controlada de 0067 con
backup, TLS/excepción loopback explícita y pairing administrativo de una estación;
después grants de discovery entre dos PCs, **sin habilitar impresión remota**.
No commit, push o deploy en esta fase.
