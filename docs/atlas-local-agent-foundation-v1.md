# Atlas Local Agent — Foundation V1

Informe histórico de Foundation V1 (`1.0.0-dev`). La evolución de impresión local
controlada (`1.1.0-dev`, protocolo 2) se documenta en
[Impresión local controlada V1](atlas-local-agent-local-printing-v1.md).

## Alcance y decisión técnica

Componente Windows independiente de Atlas Web, en `agent/`. No utiliza la base de
datos oficial, sus credenciales, documentos, PDFs ni endpoints. No modifica Caja,
Facturación, ARS, Document Designer, Compose o `.env`.

SDK detectado y utilizado: **.NET SDK 10.0.402**, runtime **10.0.13**, arquitectura
**win-x64**. Se eligió .NET 10 LTS, disponible en el equipo y con soporte hasta
noviembre de 2028 según la [política oficial de .NET](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core).
Codex no instaló SDKs. El código usa APIs Windows compatibles con Windows 10/11;
la ejecución real se verificó en Windows 10, versión 10.0.19045. Windows 11 queda
pendiente de validación en una segunda estación.

Versión del agente: `1.0.0-dev`. Versión de protocolo: `1`.

## Proyectos y responsabilidades

| Proyecto | Responsabilidad |
| --- | --- |
| `Atlas.LocalAgent.Core` | Identidad, configuración, dispositivos, contratos, estados, autorización, transportes simulados y PrintJob. |
| `Atlas.LocalAgent.Service` | Proceso de fondo, ciclo de vida, heartbeat, DPAPI, enumeración Winspool y servidor IPC exclusivamente local. |
| `Atlas.LocalAgent.Tray` | Panel WinForms e icono de notificación: estado, impresoras, diagnóstico y configuración no sensible. Solo depende de Core. |
| `Atlas.LocalAgent.Tests` | MSTest: contratos, concurrencia, DPAPI nativo, impresoras reales, IPC y ciclo de vida. |

`Atlas.LocalAgent.slnx` agrupa los cuatro proyectos. `global.json` fija el SDK y
`Directory.Build.props` activa nulabilidad, analizadores .NET, compilación
determinista y advertencias como errores. Las dependencias de pruebas son
Microsoft.NET.Test.Sdk 18.11.0 y MSTest TestAdapter/TestFramework 4.5.1. Los tres
componentes de ejecución no agregan paquetes externos.

No se registró un servicio permanente en el Service Control Manager, tarea
programada, autoarranque, regla de firewall ni instalador. `Service` es por ahora
un ejecutable de fondo con cancelación y parada limpia, no un servicio SCM ya
listo para instalar. No contiene Electron, Python o Node como runtime.

## Identidad y configuración

`LocalIdentityStore` genera un GUID criptográficamente aleatorio con
`Guid.NewGuid()`, persistido en `identity.json` junto a `createdAt`. El bloqueo de
archivo y la escritura temporal/renombrado evitan identidades duplicadas en
creaciones concurrentes. Una identidad corrupta produce error: no se sustituye
silenciosamente. Renombrar la estación o su código no cambia el GUID.

`station.json` contiene solamente `stationName`, `displayCode` y asociación
opcional `organizationId`, `centerId`, `workgroupId`. No hay IDs reales
preconfigurados. El código visible no es una clave global de autorización.
Las cadenas tienen límites y validaciones; propiedades JSON desconocidas son
rechazadas. El panel solo permite editar nombre/código, no el GUID ni asociación.

Por defecto se usa `%LOCALAPPDATA%\Atlas\LocalAgent`. `--data-dir` permite una
raíz aislada para desarrollo. **La identidad de V1 corresponde a esa raíz de
datos y al usuario Windows que ejecuta el proceso**. No se presenta todavía como
instalación machine-wide para todos los usuarios de una estación. Una futura
instalación por estación debe definir cuenta de servicio, directorio ProgramData
con ACL y acceso del tray sin regenerar el GUID ni copiar credenciales.

## Seguridad y límites de confianza

- `ISecureSecretStore` se implementa con DPAPI **CurrentUser**, sin diálogos, y un
  directorio `secrets` cuya DACL solo permite al SID del usuario actual.
- Los secretos se escriben cifrados y de forma atómica, con tamaños acotados.
  Claves de almacenamiento restringidas impiden path traversal. Se limpian los
  buffers temporales administrados/nativos y `SecretBuffer` al disponerlos.
- No se guardan secretos en JSON, `.env`, appsettings ni logs. La única prueba de
  DPAPI utiliza una cadena sintética sin valor como credencial y elimina su
  directorio temporal. No se crearon credenciales de Atlas.
- DPAPI no protege frente a un proceso malicioso bajo la misma cuenta Windows ni
  reemplaza autenticación/administración de certificados. La cuenta de servicio
  futura necesitará su propia política de acceso/rotación.
- `IAgentAuthorizationPolicy` separa descubrimiento de autorización. La política
  predeterminada es **deny-all**. Source, target, organización, centro, acción y
  referencia/expiración de credencial forman parte del contexto.
- `IDeviceCredentialLifecycle` prepara rotación y revocación; no implementa PKI,
  enrolamiento, certificados productivos ni administración remota de claves.

### Canal panel → proceso de fondo

Named pipe Windows de nombre derivado de usuario y raíz. Se crea con DACL
restringida al SID del usuario, propietario explícito, primera instancia
exclusiva, handles no heredables y `PIPE_REJECT_REMOTE_CLIENTS`. El cliente verifica
el SID propietario antes de escribir; no confía en el propietario de grupo del
token de una cuenta administradora. No hay listener HTTP/TCP o puerto nuevo.

El IPC local no es una ruta LAN de impresión. Es un canal del mismo sistema
operativo, protegido por ACL; **no se afirma que sea una sesión TLS**. TLS aplica
al contrato de comunicaciones futuras entre estaciones y con Atlas.

Solo existen comandos `Snapshot`, `Refresh`, `Configure`. No hay comandos para
imprimir, leer archivos, recibir PDFs, vincular agentes o detener el servicio.
Los mensajes usan JSON estricto, profundidad máxima 16, frame máximo 1 MiB y
timeouts. El servidor conserva el pipe y rechaza solicitudes inválidas sin
terminar el proceso. Un bloqueo por raíz impide dos procesos de fondo simultáneos.

Referencia de la restricción remota:
[CreateNamedPipe, Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea).

## LAN, Internet y selección de ruta

`ITransport`, `ILocalTransport`, `ICloudTransport` y `IRouteSelector` permiten rutas
coexistentes. `AuthorizedRouteSelector` requiere autorización y credencial no
expirada antes de preferir LAN; si LAN no está disponible, considera cloud. No
concede autorización a partir de descubrimiento o disponibilidad.

`SecureChannelRequirements` permite exclusivamente HTTPS/WSS, contempla TLS
1.2/1.3 y autenticación mutua, y rechaza credenciales, query y fragmento en la URL.
Es un contrato, **no un handshake TLS/mTLS implementado**. Las dos implementaciones
actuales son mocks en memoria, no conexiones reales.

`ILanDiscovery` tiene fixtures en memoria. No hace broadcast, mDNS, escaneo de red
ni abre sockets. Un agente descubierto no se agrega a credenciales, autorización
o trabajos. El contrato saliente cloud prepara HTTPS/WebSocket seguro sin exigir
IP pública, port forwarding o puertos de Internet entrantes. No se llama al
backend oficial ni a otro backend.

## Estados y heartbeat

Estados definidos: `Unpaired`, `Pairing`, `Connected`, `Disconnected`, `Degraded`,
`Revoked`, `Error`. Todos tienen representación en español en el tray.

El agente permanece **Sin vincular** aunque el mock reciba heartbeats: no se
simula una autorización real. Un fallo de enumeración produce `Degraded`, con
error tipado y sin mensaje bruto del driver.

Heartbeat inicial y periódico cada 30 segundos: GUID, estación, versión de agente,
versión de protocolo, SO, estado, última actividad UTC y cantidades de dispositivos.
Solo lo retiene `MockCloudTransport` en memoria. No se envían nombres de impresora
ni datos clínicos. El tray consulta el estado local cada 5 segundos; no arranca ni
detiene servicios al conectarse/desconectarse.

## Dispositivos e impresoras

`IAtlasDevice`, `IPrinterDevice` e `IPrinterDiscovery` separan catálogo y adaptador
Windows. No se implementan scanners, POS o lectores de códigos. El ID estable de
impresora se deriva del nombre normalizado y se interpreta bajo el Agent ID, no
como identificador mundial de hardware.

El adaptador consulta Winspool (`EnumPrintersW`, `GetDefaultPrinterW`,
`DeviceCapabilitiesW`): nombre, estado/flags reportados, predeterminada,
local/red, driver, color, dúplex, copias máximas y papeles/dimensiones disponibles.
Datos no expuestos quedan `null` o sin lista. Se deduplican IDs. La enumeración
trabaja fuera del hilo de UI, limita memoria/cantidad y aplica timeout de 15 s.
Si un driver nativo se bloquea, se reutiliza la tarea pendiente, no se crean
hilos de enumeración indefinidamente; no se pretende cancelar código nativo ajeno.

**Sin alertas reportadas no significa impresora físicamente lista.** La condición
local/red refleja la instalación en Windows, no la ubicación física del equipo
ni conectividad verificada. No se altera ninguna impresora ni su predeterminada.

Ejemplo de salida sanitizada del inventario de validación:

| Impresora | Predeterminada | Color | Dúplex | Papeles |
| --- | --- | --- | --- | ---: |
| <PRINTER_NAME> | No | No | No | <PRINTER_PAPER_ID> |
| Impresora virtual QA | Sí | Sí | No | <PRINTER_PAPER_ID> |

La detección informa driver, capacidades y errores tal como los expone Windows;
no inventa reparación ni disponibilidad física. Una alerta del driver no implica
un fallo añadido por el agente.

## Panel y diagnóstico

WinForms con icono de notificación, estado, estación, código, GUID y tabla de solo
lectura. `Actualizar` enumera de nuevo; `Diagnóstico` muestra datos operativos y
capacidades en un cuadro de solo lectura. Configuración solo cambia nombre/código.

La X oculta la ventana y deja el icono. `Salir del panel` cierra únicamente el
proceso UI. Ninguna acción del panel mata el proceso de fondo. La parada de este
último se realiza por cancelación/Ctrl+C o timeout de la prueba.

`Prueba local` queda **deshabilitada y señalada como próxima microfase**. No se
enviaron trabajos físicos, PDFs ni documentos clínicos/financieros. Esto usa la
excepción de alcance expresamente permitida para Foundation V1.

## PrintJob e idempotencia

`PrintJobId` es GUID no vacío. `PrintJob` contiene destino agente/impresora,
referencia opaca al documento, formato PDF/texto, copias y estado. No contiene
bytes, rutas de archivos del usuario ni instrucciones ejecutables.

Estados: Queued, Received, Downloading, Ready, Printing, Printed, Failed, Cancelled.
Son contratos, no una cola ejecutora. No se descarga ni imprime nada.

`InMemoryPrintJobRegistry`: mismo ID + misma intención → Duplicate; mismo ID con
payload distinto → Conflict; nueva intención → nuevo ID. Se excluye el estado de
la comparación de intención. El registro concurrente permite una sola aceptación
lógica. Es volátil: **no ofrece exactly-once de impresión física, persistencia tras
reinicio ni deduplicación distribuida**. No está expuesto por IPC o red.

## Logs y privacidad

JSONL tipado con timestamp, evento, Agent ID, estado, contador y código de error.
Eventos: inicio, fin, cambios de estado, discovery, enumeración, heartbeat, error.
No hay API de mensajes arbitrarios ni se escriben excepciones de terceros,
nombres de impresora, nombres de pacientes, archivos, PDFs, tokens o contraseñas.
El diagnóstico local sí muestra metadatos de estación/impresoras necesarios para
operar, no credenciales. No se captura contenido del usuario, navegador o Atlas.
Rotación/retención de logs queda para el endurecimiento de producción.

## Compilación, pruebas y publicación

Desde `<WORKSPACE>\agent`:

```powershell
dotnet restore Atlas.LocalAgent.slnx
dotnet build Atlas.LocalAgent.slnx -c Release
dotnet test Atlas.LocalAgent.slnx -c Release --no-build --logger "trx;LogFileName=foundation-release.trx"
dotnet list Atlas.LocalAgent.slnx package --vulnerable --include-transitive
dotnet publish Atlas.LocalAgent.Service/Atlas.LocalAgent.Service.csproj -c Release -r win-x64 --self-contained true -o artifacts/win-x64/service
dotnet publish Atlas.LocalAgent.Tray/Atlas.LocalAgent.Tray.csproj -c Release -r win-x64 --self-contained true -o artifacts/win-x64/tray
```

Restauración PASS; build Release **0 errores / 0 advertencias**, con analizadores
.NET habilitados. `dotnet format analyzers --verify-no-changes --no-restore
--severity warn` terminó con código 0, sin reescribir archivos.
**27 pruebas PASS / 0 FAIL / 0 omitidas**. Consulta de
vulnerabilidades NuGet: ninguna reportada para los paquetes de esta solución.
No implica ausencia garantizada de vulnerabilidades futuras.

Cobertura: persistencia/concurrencia/corrupción de identidad, configuración,
estados, DPAPI, traversal y tamaños, dispositivos, deduplicación, capacidades
desconocidas, TLS/URL, rutas autorizadas/denegadas, descubrimiento sin confianza,
heartbeat, startup/shutdown, errores redactados, PrintJob, concurrencia de 30
registros, IPC real, ACL de usuario, recuperación tras frame inválido y 20
consultas IPC consecutivas. Los directorios temporales son exclusivos de pruebas.

Publicación local self-contained **win-x64** (sin instalador, sin instalar servicio):

| Componente | Archivos | Bytes | MiB |
| --- | ---: | ---: | ---: |
| Proceso de fondo | 194 | 80704434 | 76.97 |
| Tray | 273 | 123086115 | 117.38 |

Las carpetas separadas incluyen runtime independiente; sumarlas duplica parte
del runtime. No se optimizó/trimeó para un instalador definitivo. `bin/`, `obj/`,
`TestResults/` y `artifacts/` están ignorados por `agent/.gitignore`.

Ejemplo de ejecución de desarrollo, usando la misma raíz en ambos procesos:

```powershell
.\artifacts\win-x64\service\Atlas.LocalAgent.Service.exe --data-dir <LOCAL_EVIDENCE_DIR> --run-for-seconds 120
.\artifacts\win-x64\tray\Atlas.LocalAgent.Tray.exe --data-dir <LOCAL_EVIDENCE_DIR>
```

Ejecutar en dos terminales. `--once` enumera, muestra diagnóstico y termina sin
servir IPC. `--probe` consulta un proceso existente sin crear identidad ni iniciar
otro agente. No mezclar raíces: una raíz distinta representa otra instalación de
desarrollo. No reutilizar una identidad/GUID en otra estación.

## Evidencia Windows y protección de Atlas

Raíz QA local fuera de Git:
`<LOCAL_EVIDENCE_DIR>`.
GUID persistente: `<INSTALLATION_UUID>`.
La estación y código iniciales se resolvieron localmente; la asociación Atlas
permanece vacía. No se registró el agente en la base de datos.

El ejecutable publicado arranca, enumera 10 impresoras, mantiene heartbeat y
responde por IPC con el mismo GUID. La UI abrió y su árbol accesible muestra
estación, GUID, estado Sin vincular, diez filas con driver/default y controles de
configuración. La captura de imagen de la herramienta Windows falló con
`FrameArrived timed out` y `window capture timed out`; la entrada por coordenadas
no estaba disponible. No se atribuye una revisión visual automatizada mediante
screenshot. El usuario verificó directamente estación, diez impresoras,
apertura de Diagnóstico y salida del panel, y respondió **«verificado»**.

Después de salir del panel, otra ejecución del proceso de fondo fue consultada
por IPC: `Running=true`, mismo GUID, diez impresoras y **cero procesos Tray**.
Los dos recorridos de fondo con temporizador terminaron con código **0**, con
evento `Shutdown`/`Disconnected`. No quedan procesos QA del agente en ejecución
ni se instaló un servicio permanente.

La base oficial se consulta únicamente en transacciones de lectura. Permanece
en `0066_document_designer`, sin 0067. La comparación con una referencia anterior
de Finanzas detectó adiciones preexistentes de configuración de prestadoras y
auditorías a las 08:39 del 19/10, anteriores a la creación de `agent/` a las 08:54.
No se revierten ni se atribuyen a esta implementación. Ninguna funcionalidad del
agente tiene acceso al backend o a PostgreSQL. No se reiniciaron servicios Atlas.
Las dos capturas nuevas de cierre (`/tmp/local-agent-foundation-post.json` y
`/tmp/local-agent-foundation-final.json`, dentro del backend oficial) coinciden
en **las 97 tablas, datos, esquema y secuencias**. Current y única head siguen en
`0066_document_designer`. PostgreSQL healthy; health/docs de 8001 y frontend 5174
responden HTTP 200. `git diff --check` pasa; se conservan los cambios preexistentes
del workspace. Solo se añadieron 24 archivos fuente/configuración bajo `agent/`
y este documento.

**Resultado de Foundation V1: PASS.** La confirmación visual procede del usuario;
la enumeración, IPC, persistencia, independencia del proceso y parada limpia
también tienen comprobación técnica. Esto no certifica impresión remota,
instalación SCM o pairing, que están explícitamente fuera de esta fase.

## Próximas microfases propuestas

1. Prueba de impresión exclusivamente local, con selección/confirmación explícita
   de impresora y página sintética; spooler, errores y cancelación.
2. Instalación por estación y host SCM, cuenta mínima, ACL compartida UI/servicio,
   identidad machine-wide, recuperación y retención de logs.
3. Pairing/enrolamiento Atlas, autorización verificable por organización/centro,
   lifecycle de credenciales y compatibilidad de versiones.
4. Transportes LAN/cloud reales cifrados y autenticados, descubrimiento acotado
   sin confianza automática, sin abrir puertos de Internet.
5. Cola durable, deduplicación tras reinicio y estados verificables antes de
   integrar Document Designer o documentos clínicos/financieros.

No hay cambios en Atlas Web, datos clínicos, datos financieros, PDFs o esquema.
No se creó 0067, instalador final, auto-update, panel web, commit, push o deploy.
