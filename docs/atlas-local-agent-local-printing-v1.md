# Atlas Local Agent — impresión local controlada V1

RESULT=PASS

PHYSICAL_PRINT_VALIDATED=YES

Estado: implementación, validación técnica y prueba física controlada completadas.
El usuario confirmó la impresión desde el panel y aportó una fotografía de la
página sintética <PRINTER_NAME> / A4. Confirmó además: «1 sola hoja». La impresión permanece
deshabilitada por defecto; no se habilita integración con Atlas Web.

## Alcance y arquitectura

Workspace `<WORKSPACE>`, rama `feat/complete-care-context`, HEAD
`3646b6bd7689d7f49941a8254ec327c3eda5682e` sin modificar. Se mantienen los proyectos
Core / Service / Tray / Tests de Foundation V1, .NET 10 LTS, SDK 10.0.402.
Versión de agente `1.1.0-dev`, protocolo local `2`. Actualizar Service y Tray juntos.

Se reutilizan PrintJob, PrintJobId, IPrinterDiscovery, PrinterDevice, los estados,
IAgentLog y el IPC local con ACL de usuario y rechazo de clientes remotos.
`Submitted` amplía los estados existentes para evitar confundir entrega al
spooler con impresión física. No hay integración con Atlas Web, LAN/cloud real,
PDFs, datos clínicos, datos financieros ni PostgreSQL.

Archivos principales de esta fase:

- Core: `SyntheticPrinting.cs`; extensiones a `Devices.cs`, `PrintJobs.cs`,
  `Diagnostics.cs`, `Identity.cs`, `LocalProtocol.cs`.
- Service: `LocalPrintJobStore.cs`, `SyntheticPrintCoordinator.cs`,
  `WindowsGdiPrintBackend.cs`; integración en `Program.cs`, `LocalPipeServer.cs`,
  `WindowsPrinterDiscovery.cs`.
- Tray: `SyntheticPrintPanel.cs`, integración en `AgentWindow.cs`.
- Tests: `LocalPrintingTests.cs` y actualización de contratos en `FoundationTests.cs`.

## Motor Windows

API elegida: **GDI + Winspool**, sin shell print ni automatización de navegador.
El adaptador crea un contexto explícito para la impresora seleccionada, con una
copia privada del DEVMODE del driver. Fija para ese trabajo orientación vertical,
escala 100%, una copia y papel anunciado; pide una sola cara si hay dúplex.
No llama a SetPrinter, SetDefaultPrinter ni modifica formularios del sistema.

Antes de StartDoc verifica dimensiones físicas, área imprimible real, tipografía
y que todas las líneas caben. Dibuja exactamente **un StartPage/EndPage** y finaliza
con EndDoc. StartDoc proporciona el ID de spooler, que se guarda inmediatamente.
Si ocurre un fallo posterior se intenta AbortDoc, **sin prometer cancelación física**.

Las llamadas nativas bloqueantes se ejecutan fuera del hilo de UI y los trabajos
se serializan en el coordinador. Un driver que no retorna puede bloquear su worker;
no se fuerza timeout con reenvío que pudiera duplicar papel. El aislamiento de
drivers en un proceso ejecutor separado queda como endurecimiento futuro.

Referencias primarias:
[GDI Print API](https://learn.microsoft.com/en-us/windows/win32/printdocs/gdi-printing),
[StartDocW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-startdocw),
[DocumentProperties](https://learn.microsoft.com/en-us/windows/win32/printdocs/documentproperties),
[GetJob](https://learn.microsoft.com/en-us/windows/win32/printdocs/getjob).

## Solo página sintética

El IPC acepta únicamente GUID de trabajo, GUID de agente, ID derivado de impresora
y formato enumerado. No acepta bytes, texto del documento, paciente, ruta, URL,
PDF, facturas o número de copias. JSON desconocido se rechaza. El receptor genera
internamente `PrintJob`, `PlainText`, una copia y referencia fija
`atlas-synthetic-test-v1:<formato>`.

Contenido fijo: ATLAS PÉRGAMO / PRUEBA DE IMPRESIÓN, estación, versión, impresora,
formato, fecha/hora **local con offset**, GUID, separadores y advertencia de página
sintética sin información clínica/financiera. Los únicos datos variables son
metadatos operativos y el GUID. No se captura contenido del usuario.

## Formatos y capacidades

Papeles Windows ahora incluyen su RawKind. Se exige ID válido y dimensiones
anunciadas, no solamente un nombre como «A4». La validación se repite antes del
envío y se contrasta con el contexto de impresión real del driver.

| Formato | Dimensiones / diseño | Comportamiento |
| --- | --- | --- |
| POS 80 mm | Ancho 80 mm; papel anunciado de 180–600 mm de largo; margen 3 mm, cuerpo 9 pt y título 10 pt | Diseño propio, sin escalar Letter/A4; wrapping y control de altura. |
| Letter | 215.9 × 279.4 mm; margen 15 mm, cuerpo 11 pt y título 15 pt | Una página; se rechaza clipping antes de StartDoc. |
| A4 | 210 × 297 mm; misma tipografía de página normal | Una página; se respeta el área imprimible del driver. |

POS solo dibuja un final lógico; no envía comandos RAW ni de cutter. No se supone
que exista cortador físico. Si no cabe el texto o no se anuncia el papel, falla
sin imprimir. 58 mm no se habilita en esta fase.

Inventario real: **10 impresoras**. Físicas detectadas: <PRINTER_NAME>,
<PRINTER_NAME>, <PRINTER_NAME>, <PRINTER_NAME>. Se identifican
como virtuales y bloquean para esta prueba impresoras remotas, fax y PDF,
evitando diálogos de salida a archivo y destinos remotos inesperados.

Ningún driver instalado anuncia actualmente un papel POS 80 mm compatible: no se
crea uno ni se supone que una impresora de etiquetas admita recibos de 80 mm.
POS está preparado y probado con mocks, **no validado físicamente**.

El usuario eligió **<PRINTER_NAME>**. Su driver anuncia A4 y Letter. Ambos
pasaron preflight nativo sin StartDoc: **17 líneas, final a 123 mm**, una página;
spooler disponible, **cero trabajos físicos enviados durante ese preflight**.
La prueba física posterior usó **A4**, con confirmación del usuario en el panel.
Una impresora no seleccionada reportó flags de error; no se prueba ni se cambia su estado.

## Ciclo de vida, errores y cancelación

Queued → Received → Printing → Submitted → Printed, cuando Windows lo informe.
Failed y Cancelled representan fallo y cancelación previa al envío.

- Queued: preparado, sin impresión ni autorización implícita.
- Received: confirmado y aceptado, aún cancelable antes del límite de spool.
- Printing: registro duradero escrito inmediatamente antes de StartDoc. Ya no
  se promete cancelación, porque la API podría estar ejecutándose.
- Submitted: EndDoc aceptado; **no equivale a papel físicamente entregado**.
- Printed: Windows informa impreso; todavía requiere comprobar la salida.
- Si el job desaparece del spooler, se conserva Submitted con estado Missing:
  no se interpreta como éxito ni se reenvía.
- La consulta contrasta también el título sintético/GUID: un ID de spooler
  reutilizado tras reinicio no atribuye al agente el estado de otro documento.
- Error después de aceptación: Failed / OutcomeUnknown, conserva spool ID y no
  se reintenta. Puede existir papel o un trabajo aún en Windows.

CancelSyntheticTest realiza una transición atómica solo desde Queued, Received
o Ready. Si el driver ya cruzó la frontera, devuelve TooLateToCancel. No cancela
otros trabajos del usuario ni afirma una cancelación física.

Impresora inexistente, selección inválida, driver, spooler apagado, offline,
papel incompatible y layout demasiado grande tienen códigos y textos sanitizados.
No se simula offline apagando dispositivos reales ni deteniendo el spooler.

## Idempotencia, concurrencia y recuperación

`LocalPrintJobStore` implementa el registro existente y persiste recibos mínimos
en `print-jobs/<GUID>.json`, fuera de Git. No guarda contenido renderizado, PDFs,
credenciales, nombre de paciente o bytes de impresión.

La transición Queued → Received se reclama una sola vez bajo sincronización; solo
el ganador programa el worker. Inmediatamente antes de StartDoc se persiste
Printing. El servicio conserva el bloqueo único `service.lock` por raíz.

- Mismo ID + misma intención: devuelve estado/ID de spooler existente, sin enviar.
- Mismo ID + payload diferente: conflicto, sin enviar otra copia.
- Nueva intención deliberada: nuevo GUID y nueva confirmación.
- Failed, Cancelled y resultado incierto tampoco se reenvían con el mismo ID.
- Al reiniciar, Received/Ready/Printing incompletos pasan a Failed/OutcomeUnknown;
  **no se redisparan**. Queued sigue pendiente sin imprimir automáticamente.
- Se utilizan archivo temporal, flush a disco y reemplazo atómico. Un registro
  corrupto produce fallo cerrado, no una intención regenerada.

La garantía es de **un envío lógico al spooler por ID dentro de esa raíz intacta**,
incluyendo concurrencia y reinicio del proceso. No es exactly-once física frente
a fallos de hardware/driver, pérdida/corrupción del journal o restauración de un
respaldo antiguo. No borrar/copiar el journal para intentar otro envío.

Durante estrés se corrigió una carrera de IPC: el servidor ahora espera un acuse
de lectura antes de desconectar el pipe. El reintento sigue usando el mismo ID y
el journal; no depende de que llegue una respuesta de UI.

## Tray, seguridad y diagnóstico

Pestaña «Prueba de impresión»: selección explícita de impresora y formato,
driver/default/capacidades, botón de prueba, estado persistido, mismo ID para
consultar/reintentar, cancelación previa y nueva intención deliberada.
Los formatos no anunciados se señalan y no permiten activar la prueba.

El diálogo identifica impresora, formato, página sintética, una página/una copia
y ausencia de pacientes. Sus botones son **Imprimir / Cancelar**, con foco inicial
en Cancelar. Abrir la ventana no imprime; reabrir un trabajo tampoco lo envía.
Si una comunicación falla, se consulta/reintenta el ID, no se crea otro en silencio.

Dos barreras: el receptor exige UserConfirmed y el proceso de fondo inicia con
**impresión física deshabilitada**. Solo tras autorización humana expresa puede
ejecutarse manualmente con `--allow-physical-print`; ese flag no imprime por sí
solo y sigue siendo necesaria la confirmación de cada trabajo. No es permiso de
Atlas, pairing o autorización de otros agentes: el alcance es la cuenta Windows
local protegida por la ACL del pipe.

Diagnóstico: spooler disponible, inventario, selección/driver, formatos, último
recibo, spool ID/estado y diez errores recientes tipados. Logs JSONL de trabajo:
evento, ID, identificador derivado de impresora, formato, estado, error, timestamp,
spool ID y versión. No hay contenido, nombre arbitrario de impresora, excepción
bruta, PHI o secretos en logs.

La captura/entrada de la herramienta Windows falló con `FrameArrived timed out`
y `coordinate input geometry is unavailable`. Se leyó el árbol accesible. Una
selección real de <PRINTER_NAME> + A4 desde el panel generó el recibo QA
`<QA_JOB_ID>`, inicialmente
**Queued / sin spool ID / NotSubmitted**.
No se atribuye validación visual completa a una captura no obtenida.

El usuario realizó por su cuenta una página de prueba desde Windows y confirmó
salida correcta: acredita disponibilidad de <PRINTER_NAME>, **no valida el motor del agente**.
También informó que desde el agente aún no salía página, comportamiento esperado
con el gate físico bloqueado y el host QA de duración limitada. El usuario cerró
el panel para actualizar los ejecutables. Hasta ese punto no se había impreso
desde el agente; la prueba posterior se documenta a continuación.

### Prueba física autorizada y cierre visual

Se reabrió manualmente el host QA con duración limitada e impresión habilitada,
sin envío automático. El usuario confirmó la prueba en el panel del agente.
La fotografía recibida muestra estación **<WORKSTATION_NAME>**, agente **1.1.0-dev**,
**<PRINTER_NAME> / A4**, fecha local **2026-10-19 20:35:45 -04:00** y el mismo
GUID `<QA_JOB_ID>`. El texto sintético y el pie aparecen
completos, legibles y sin clipping visible. El usuario confirmó **una sola hoja**,
sin copias ni páginas adicionales.

El journal y los logs registran **una aceptación**, **un envío Submitted** y
**un único ID de spooler: 6**, con `copies=1`, formato A4 y error None. No se
reenviaron trabajos para verificar el resultado. Las dos observaciones Printing
(antes de StartDoc y al persistir el spool ID) son transiciones del mismo trabajo,
no dos impresiones.

El recibo conserva Submitted y la última observación Windows Queued; no se altera
artificialmente a Printed. La validación física procede de la fotografía y la
confirmación humana, independientemente del último estado observado del spooler.
**Prueba física A4 PASS**. Letter y POS 80 mm permanecen sin validación física.

La predeterminada reportada cambió durante comprobaciones manuales de Windows.
El agente no contiene ni invoca APIs para cambiarla y no
  restaura ni altera esa selección del sistema; siempre usa el destino explícito.

## Ejecución y validaciones

Publicaciones self-contained en `agent/artifacts/win-x64/service` y `tray`, sin
instalador o servicio permanente. Ejecutar ambos con la misma raíz de datos.
Tamaños locales medidos: Service 77.04 MiB y Tray 117.45 MiB, incluyendo sus
runtimes separados. Los binarios y resultados de prueba permanecen ignorados por Git.
La raíz QA conserva el GUID de Foundation V1:
`<LOCAL_EVIDENCE_DIR>`.

Comandos técnicos, sin habilitar impresión:

```powershell
dotnet restore Atlas.LocalAgent.slnx
dotnet build Atlas.LocalAgent.slnx -c Release --no-restore
dotnet test Atlas.LocalAgent.slnx -c Release --no-build --logger "trx;LogFileName=local-printing.trx"
dotnet format analyzers Atlas.LocalAgent.slnx --verify-no-changes --no-restore --severity warn
dotnet publish Atlas.LocalAgent.Service/Atlas.LocalAgent.Service.csproj -c Release -r win-x64 --self-contained true -o artifacts/win-x64/service
dotnet publish Atlas.LocalAgent.Tray/Atlas.LocalAgent.Tray.csproj -c Release -r win-x64 --self-contained true -o artifacts/win-x64/tray
```

`--inspect-printer "<PRINTER_NAME>" --format A4` (o Letter), junto al mismo
`--data-dir`, hace preflight de solo lectura y nunca llama StartDoc. `--once`
enumera y termina; `--probe` consulta el host. No hay autoarranque.

Pruebas completas: **53 PASS / 0 FAIL / 0 omitidas**. Incluyen las 27 de Foundation,
selección/JSON, formatos, layouts, gate/confirmación, backend nativo bloqueado,
30 submits concurrentes del mismo ID, ID nuevo, conflicto, recuperación, spooler
ausente, impresora inválida/offline/virtual, fallos antes/después del spool,
cancelación antes/después, observación y logs sanitizados. La impresión automática
usa mocks: no requiere papel ni envía páginas físicas. Smoke focal IPC/concurrencia:
**7 PASS**. Build: **0 errores / 0 warnings**; analizadores en modo verificación.
Tras corregir el cierre prematuro de IPC, se repitió además tres veces el caso
de cliente inválido seguido de 20 consultas: **3 PASS**, 60 respuestas completas.
El ejecutable publicado también respondió por IPC con el mismo GUID, versión
1.1.0-dev, protocolo 2, spooler disponible y **PhysicalPrintingEnabled=false**.
Windows 10 real; Windows 11 compatible por API, todavía no certificado.

## Protección de Atlas y cierre

Atlas current/head permanece `0066_document_designer`, una sola head. La evidencia
read-only usa `/tmp/local-agent-print-pre.json`, `/tmp/local-agent-print-post.json`
y el cierre `/tmp/local-agent-print-physical-final.json` en el backend oficial
para contrastar las 97 tablas, esquema y secuencias.
Resultado: **sin tablas, datos, esquemas o secuencias alterados**, sin tablas
nuevas ni pérdidas. PostgreSQL healthy, health/docs 8001 y frontend 5174 HTTP 200.
`git diff --check` PASS; también se revisaron los archivos fuente nuevos sin
hallazgos de whitespace. La única advertencia de conversión LF/CRLF procede de
un archivo frontend preexistente, que no se editó en esta fase.
No se ejecutó Alembic, reinicio de Atlas, escritura clínica/financiera o migración.
No se modificaron frontend/backend web, Compose o `.env`.

No 0067, servicio Windows permanente, startup automático, tarea programada,
routing real, perfiles por centro/organización, commit, push o deploy.

**Cierre: RESULT=PASS / PHYSICAL_PRINT_VALIDATED=YES**, limitado a la página
sintética A4 y la impresora <PRINTER_NAME> comprobadas. No se enviará otra
prueba sin nueva autorización. No certifica POS/Letter físicos, Windows 11 ni
integración con documentos reales o Atlas Web.
