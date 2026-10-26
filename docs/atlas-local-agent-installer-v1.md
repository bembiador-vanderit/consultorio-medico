# Atlas Local Agent — instalador por usuario V1

## Alcance

Paquete piloto Windows x64 para preparar la segunda estación. No ejecuta pairing,
no registra la PC, no copia identidad/DPAPI/SQLite de la primera estación, no
imprime y no modifica Atlas Web, Compose, .env ni PostgreSQL. No instala servicio
Windows, tarea programada, autoarranque, firewall ni certificados.

Se reutilizan Core, Service, Tray, LocalIdentityStore, WindowsSecretStore,
LocalAgentClient y el canal owner-only. No hay una segunda implementación del
registro o de impresión. El instalador Inno Setup incluye dos publicaciones
self-contained de .NET: Service y Tray. No requiere SDK/runtime separado en
la segunda PC ni acceso a Internet durante la instalación.

## Ubicaciones y uso

- Programa: `%LOCALAPPDATA%\Programs\Atlas\LocalAgent`.
- Estado propio del usuario/estación: `%LOCALAPPDATA%\Atlas\LocalAgent`.
- Acceso directo Inicio: **Atlas Local Agent**. Escritorio opcional.
- Abrirlo inicia el host y el panel juntos, solo por acción explícita.
- La X oculta el panel. **Salir del panel** cierra panel y host propio.
- No copiar la carpeta de datos ni el directorio histórico de QA de la primera PC.
- Vincular mediante dirección HTTPS autorizada y código nuevo, en fase separada.
- Si el endpoint está en Tailscale, la segunda PC requiere conexión propia
  autorizada a la tailnet. No usar localhost de la segunda PC como servidor Atlas.
- Desinstalar desde Aplicaciones conserva datos e identidad. No revoca la
  estación en el servidor; revocar requiere Administración de Atlas Web.

## Arranque y límites de seguridad

El acceso directo utiliza `Tray.exe --managed`. Solo admite opcionalmente una
raíz explícita `--data-dir` para QA. No acepta opciones para habilitar impresión,
incluir grants físicos o relajar HTTPS. ManualAgentLaunch construye argumentos
sin shell para el hijo: raíz, Production y `--stop-on-stdin-close`. Elimina la
excepción loopback HTTP del entorno heredado. El cliente conserva validación TLS.

El host instalado no inicia el consumidor de trabajos remotos. La impresión
física continúa denegada por defecto. Pairing, heartbeat y catálogo usan la
credencial propia únicamente después del emparejamiento manual.

Un mutex evita múltiples paneles administrados; Inno lo comprueba antes de
actualizar/desinstalar. El host conserva su lock existente. El panel rechaza
una ejecución ya activa en la misma raíz: no toma control de otro agente.
El EOF de stdin redirigido cancela cooperativamente el hijo y permite cerrar
sus recursos. No mata procesos por nombre ni usa shell. Si el hijo demora en
salir, se informa sin afirmar que terminó ni forzar su cierre.

## Construcción reproducible

Desde `<WORKSPACE>\agent` con SDK fijado por global.json e Inno Setup instalado:

```powershell
.\installer\Build-Installer.ps1 -IsccPath '<ruta de ISCC.exe>'
```

La construcción usa una carpeta nueva y publica solo proyectos de ejecución;
no empaqueta binarios del árbol de QA ni datos existentes. Rechaza identidad,
station.json, secretos, SQLite, .env, autorizaciones, PDFs, dumps y resultados
de tests; elimina símbolos de desarrollo del payload nuevo. Genera manifiesto
por archivo con tamaños y SHA256. Cada build debe usar una carpeta nueva.

Prueba aislada del paquete (no arranca ni empareja el agente):

```powershell
.\installer\Test-Installer.ps1 -IsccPath '<ruta de ISCC.exe>' -PayloadDir '<payload del build>'
```

Esta variante usa AppId QA único y ningún acceso directo: verifica instalación,
reinstalación, hashes de los archivos, desinstalación y estado local preservado.
No instala/actualiza el producto de la estación 1 ni ejecuta contenido impreso.

## Certificación y límites

El paquete piloto no está firmado con certificado Authenticode de Atlas.
SHA256 permite comprobar integridad, no sustituye firma/autenticidad del editor.
No deshabilitar antivirus, SmartScreen ni políticas del equipo para instalarlo.
Distribución productiva firmada y mecanismo de actualización son trabajo futuro.
Revisar la licencia comercial del compilador antes de distribución comercial;
esta entrega se destina a validación interna controlada de segunda estación.

Windows 10 22H2 x64: entorno local de validación. Windows 11: compatibilidad
prevista, aún no certificada mediante ejecución en una segunda PC. Emparejamiento,
acceso HTTPS desde esa PC y SafeValidation de destinos se validarán después;
crear el instalador no constituye aprobación de esos escenarios ni de impresión.

## Validación de esta entrega

- Instalador entregado: `<USER_PROFILE>\Downloads\AtlasLocalAgent-Setup-1.2.0-win-x64.exe`.
- Copia de construcción: `agent/artifacts/installer-20261022-v2/`.
- Tamaño: **63.771.460 bytes**; payload: **469 archivos / 206.288.176 bytes**.
- SHA256: `<SHA256>`.
- Firma Authenticode: **NotSigned**, advertencia documentada; no se cambia la
  política de seguridad Windows.
- Inno Setup 6.7.3 instalado por el usuario; el intento automatizado de obtener
  el compilador fue bloqueado y no se eludió. Compilador anuncia uso no comercial;
  no se certifica licencia para distribución comercial.
- Restore/build .NET: 0 errores, 0 advertencias en compilación inicial.
- Focal arranque/contrato de instalación: 5 PASS.
- Build final .NET: **0 errores / 0 advertencias**.
- Agent completo final: **159 PASS / 1 omitido opt-in HTTP temporal / 0 fallos**,
  TRX `installer-full-final.trx`, 35 s.
- Instalación/reinstalación/desinstalación aisladas: **PASS**. Los **469 archivos**
  instalados coinciden con el manifiesto. Estado local normal intacto.
- Ejecución del binario self-contained ya instalado: **PASS**, raíz QA nueva,
  Unpaired, sin organización asignada, impresión física apagada y cierre limpio
  al cerrar su stdin. Se eliminó solamente esa raíz de runtime QA tras validarla.
- No quedan ejecutables instalados ni registros de desinstalación QA; se conservan
  los paquetes de prueba y evidencia de compilación, sin credenciales.
- La primera comprobación QA de registro usó un AppId demasiado largo que Inno
  abrevia con hash. Se verificó la clave real y se desinstaló correctamente;
  el test repetido con AppId QA corto pasó. No cambió el AppId del producto.
- La prueba de proceso hijo utiliza una raíz temporal nueva, sin vincular,
  confirma impresión física apagada, EOF/cierre limpio e identidad preservada.
- Se corrigió antes del empaquetado una lectura de stdin que bloqueaba el
  arranque; la prueba de proceso real detectó el problema y pasó al repetirla.
- El primer empaquetado coincidió con compilación de tests y encontró un lock
  de DLL; se repitió en otra carpeta, sin compilaciones .NET concurrentes.
- Current/head oficial consultado, sin ejecutar upgrade: `0069_print_job_contract`.
- Backend health, /docs, frontend: HTTP 200; PostgreSQL healthy.
- Identidad, estación y blob DPAPI del Agent 1 mantienen sus SHA256 previos.
- `.env` y Compose mantienen sus SHA256 previos; no se reinició ningún servicio.

El panel gráfico del acceso directo no se certificó visualmente en una segunda
PC: esa validación, el pairing y la conectividad HTTPS siguen pendientes allí.

No migración nueva, pairing, impresión, servicio permanente, commit, push o deploy.
