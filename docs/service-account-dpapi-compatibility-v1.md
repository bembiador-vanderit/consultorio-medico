# Service account + DPAPI compatibility V1 — laboratorio sintético

RESULT=PASS
SERVICE_ACCOUNT_STRATEGY_READY=YES
DPAPI_SERVICE_STRATEGY_READY=YES
SYNTHETIC_DPAPI_VALIDATED=YES
LEAST_PRIVILEGE_MODEL_READY=YES
PRINTER_ACCESS_MODEL_VALIDATED=YES
HTTPS_SERVICE_CONTEXT_VALIDATED=YES
REAL_CREDENTIALS_UNTOUCHED=YES

REAL_PAIRING_MIGRATED=NO
REAL_DPAPI_CHANGED=NO
REAL_SQLITE_CHANGED=NO
PHYSICAL_PRINTS_SENT=0

Este PASS documenta una estrategia validada con pruebas sintéticas en `<WORKSTATION_NAME>`, NO instalación productiva ni migración real. No se convirtió el Agent actual en servicio Windows. Los servicios QA fueron temporales, demand-start y eliminados al terminar.

## Decisión concreta

SERVICE_ACCOUNT_STRATEGY=Virtual service account NT SERVICE\AtlasLocalAgent, propia de cada equipo.

DPAPI_STRATEGY=CurrentUser bajo la identidad virtual y el perfil cargado por SCM; nunca fallback automático a LocalMachine.

PAIRING_MIGRATION_STRATEGY=Reprotección local explícita, solo en memoria y con pares Windows autenticados; preservar UUID/credencial/asociación. Requiere una autorización futura por estación; NO ejecutada sobre datos reales.

DATA_DIRECTORY_STRATEGY=C:\ProgramData\AtlasPergamo\LocalAgent\ con config/data/logs/secrets y ACL por identidad; binarios protegidos en Program Files. Sin dependencia de cwd ni creación automática de otra identidad al faltar datos.

Se eligió cuenta virtual porque el laboratorio comprobó aislamiento DPAPI, perfil propio, reinicio, SQLite, impresoras y HTTPS sin cuenta administrativa ni contraseña de usuario que administrar. Windows gestiona la identidad/contraseña de esta clase de cuenta. No se creó AtlasLocalAgentSvc como usuario SAM productivo.

## 1. Precheck y DPAPI actual

- Verificar branch, revisión de base y target antes de la prueba; no ejecutar migraciones, stamp ni downgrade.
- WindowsSecretStore usa CryptProtectData/CryptUnprotectData con UI_FORBIDDEN (flag 1), sin LOCAL_MACHINE y con entropy adicional nula. El decrypt lo realiza WindowsSecretStore en el mismo proceso/identidad Windows.
- Raíz emparejada: `<AGENT_DATA_ROOT>`. Blob: `secrets\secret.atlas-registry-v1.bin`. ACL del secreto: solo el propietario Windows. No modificar ni descifrar el blob real para el laboratorio.
- Ciphertext y claves maestras DPAPI son conceptos separados: cambiar ACL o mover el blob no cambia su identidad criptográfica. CurrentUser requiere el contexto/perfil correcto. El perfil operativo del futuro servicio forma parte de la preservación de credenciales.
- Conservar fuera del repositorio huellas de `identity.json`, `station.json`, blob real y `routing/1-1/inbox.sqlite`; comparar `.env` y Compose con baseline. No inferir integridad remota si no se releen sus archivos.

## 2. Comparación de cuentas

| Opción | DPAPI y aislamiento | Impresoras / HTTPS | Operación / decisión |
|---|---|---|---|
| LocalSystem | Contexto distinto al usuario actual; privilegios muy amplios | Contexto de sistema; visibilidad no idéntica garantizada | Excesivo para Atlas; rechazado |
| NetworkService | Identidad compartida con otros servicios que la usen | Red con identidad de equipo; HTTPS requiere validación | No ofrece la separación por servicio elegida; rechazado |
| LocalService | Identidad compartida; no abre blobs de otro usuario | Salida HTTPS posible; catálogo depende de contexto | Menos privilegios, pero aislamiento compartido; rechazado para esta estrategia |
| Usuario local dedicado AtlasLocalAgentSvc | CurrentUser independiente y viable con perfil | Requiere validar drivers/red bajo esa cuenta | Fallback si virtual no es viable; añade provisioning/rotación de contraseña y riesgo DPAPI ante resets. No crear ni fijar PasswordNeverExpires por defecto |
| Virtual NT SERVICE\AtlasLocalAgent | Identidad de servicio, perfil y CurrentUser propios | Validar impresoras y HTTPS bajo esa identidad en cada instalación | RECOMENDADA; sin contraseña manual ni usuario interactivo nuevo |

No se supone que la cuenta virtual podrá leer el secreto real del usuario propietario: precisamente las pruebas negativas lo rechazan. Una cuenta virtual con el mismo nombre en otra PC no convierte sus claves DPAPI en compartidas; no usar el SID/nombre como identidad global de estación.

Referencias primarias: [cuentas de servicio y perfiles SCM](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts), [cuentas virtuales](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-service-accounts), [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

## 3. Laboratorio Windows real, sin datos reales

Código aislado: agent/qa/Atlas.LocalAgent.IdentityLab. Host SCM one-shot de QA con ServiceBase; NO se añade modo servicio al binario operativo ni se cambia su ciclo de vida. Reutiliza WindowsSecretStore, WindowsPrinterDiscovery y el cliente HTTPS existente, sin AgentRuntime, pairing, heartbeat autenticado, consumidor de trabajos ni motor de impresión.

Orquestador: agent/qa/Invoke-ServiceIdentityLab.ps1. Exige administrador para crear/eliminar solo sus servicios QA. Usa raíces nuevas bajo la base sintética `C:\AtlasQaLabs` (o `ATLAS_IDENTITY_LAB_BASE` de máquina) con patrón rígido `service-account-lab-<12 hex>`; rechaza rutas reales de Agent/ProgramData. Config SyntheticOnly=true, UUID de fixture nuevo, cuentas distintas y endpoint GET HTTPS `/api/v1/health` obligatorio. No acepta token, pairing code, password ni ruta de credencial real.

Ejecución sintética: cuentas A (origen), B (servicio candidato) y C (observador no autorizado), con UUID de fixture `<INSTALLATION_UUID>` nunca registrado en Atlas. Guardar los SIDs, rutas y hashes particulares únicamente en evidencia local.
- A cifra un valor marcado ATLAS-QA-DPAPI-SECRET-DO-NOT-USE más UUID sintético en su contexto. El valor es fixture explícito, no token de Atlas.
- B puede leer una copia del ciphertext A pero NO descifrarla: WrongUserBlobDenied=true. Así se distingue denegación criptográfica de denegación NTFS.
- B tampoco puede abrir el archivo secreto privado A: OtherUserSecretsAclDenied=true.
- A descifra su secreto sintético en memoria y lo envía por pipe local efímero autenticado a B. B verifica que coincide exactamente con el fixture de ese UUID, lo reprotege con CurrentUser y borra los buffers.
- B descifra su nuevo blob: SameServiceAccountDecrypt=true. SCM detiene y vuelve a iniciar B; RestartDpapiRecovered=true. UUID sintético antes/después idéntico.
- A no puede descifrar la copia del nuevo ciphertext B: CreatorCannotDecryptCandidateCopy=true. A conserva lectura de su propio fixture.
- C, no administrador, no puede leer el directorio privado de B: CandidateSecretsAclDenied=true. C sí recibe una copia cifrada legible y no la puede descifrar bajo su propio perfil: CopiedCandidateBlobDenied=true.
- No se realizó copia a una segunda PC. CROSS_PC_DPAPI_TEST=NOT_RUN; no se afirma validación física cross-PC. La prueba de perfil equivocado corresponde a otra identidad/perfil cargado, no a falsificar una variable USERPROFILE bajo el mismo SID.

Evidencia esperada fuera del repositorio: reportes de ambas fases, verificación del creador, observador y resumen, con `Succeeded=true` y servicios temporales eliminados.

## 4. Provisioning y handoff seguro propuestos

Para instalaciones nuevas, preferir que la credencial nazca y se proteja directamente en el contexto del servicio mediante un bootstrap explícitamente autorizado. El código de pairing no es contraseña de usuario y no debe aparecer en CLI/entorno/logs. No se ejecutó pairing en este laboratorio.

Para las estaciones existentes, no hace falta crear otra estación ni emparejar automáticamente si el propietario actual aún puede leer su credencial y se autoriza una reprotección segura. El UUID de Atlas, la credencial de pairing y el SID Windows son identidades diferentes. El backend actual no vincula su UUID a un SID Windows: cambiar el protector local no requiere por sí solo una revisión DB.

Flujo futuro, todavía NO autorizado sobre secretos reales:

1. Detener y bloquear el consumidor anterior. Confirmar UUID/root esperado y respaldar datos coherentes, incluido SQLite/WAL/tombstones; no copiar una DB abierta ignorando WAL.
2. Instalar/verificar binario protegido y cuenta virtual estable. Preparar directorios/ACL, perfil y estado de staging; no usar una carpeta escribible por usuarios como binPath de un servicio privilegiado.
3. Fuente bajo SID propietario original; destino bajo SID exacto de servicio. Pipe local con primer-instance, rechazo remoto, DACL solo ambos SIDs. Fuente verifica propietario del pipe; destino identifica el SID Windows de la fuente antes de leer.
4. Plaintext únicamente en memoria del handoff; no archivos temporales, argumentos, variables persistentes, stdout ni logs. Frame acotado, timeout, cancelación y buffers explícitos limpiados. Persistir solo nuevo ciphertext mediante escritura atómica en destino.
5. Destino comprueba UUID/endpoint/asociación, descifrado y evidencia durable, sin regenerar identidad ni imprimir. Solo tras aceptación explícita se cambia al runtime nuevo. Mantener staging y rollback del origen hasta confirmar el corte.
6. Rotación del bearer, invalidación/borrado de copias antiguas y rollback requieren una decisión transaccional aparte: rotar invalida el token anterior y puede impedir rollback. No prometer reversibilidad del token viejo después de rotarlo ni ejecutar una rotación real en esta fase.

El pipe sintético implementó los controles de identidad y transferencia de memoria indicados; NO es todavía un migrador de credenciales productivas. La fuente real solo debe leer el blob real en una fase futura expresamente autorizada y con verificación de binario, raíces, límites y consentimiento.

Límites: un administrador local/kernel puede tomar posesión, inspeccionar memoria o suplantar procesos. DPAPI/ACL no protegen contra el administrador de la propia máquina. ZeroMemory reduce la vida de buffers; no certifica ausencia en pagefile/hibernación/dumps del SO. No se deshabilitó seguridad de Windows para simular esa garantía.

## 5. Perfil, SQLite, impresoras y HTTPS

SCM debe crear/cargar un perfil de servicio sin login interactivo bajo `<SERVICE_PROFILE>`. B no debe ser administrador. Limitar RequiredPrivileges a lo necesario; no agregar grupos administrativos ni privilegios de depuración/backup/impersonación. El pipe usa identificación del cliente, no impersonación para ejecutar operaciones del usuario.

SQLite sintético en service/data/synthetic.sqlite: lectura, escritura, commit, rollback y bloqueo entre dos conexiones reales PASS. Una segunda transacción recibe SQLITE_BUSY mientras la primera mantiene el write lock. Tras stop/start el contador continúa y conserva el mismo UUID; no se reconstruye la DB ni se usa SQLite de Atlas/Agent real.

Impresoras desde el contexto B: enumerar `<PRINTER_NAME>`, su driver y `<PRINTER_FINGERPRINT>`. Validar OpenPrinter/ClosePrinter y consulta del servicio spooler sin StartDoc, SubmitAsync, página de prueba, PDF ni job Windows. No asumir que la impresora visible para el usuario interactivo lo será para el servicio.

DNS y HTTPS desde B: exigir health 200, TLS estándar y validación de certificado normal. Sin bearer de estación, cookies, redirects, HTTP fallback ni excepción loopback. Una prueba en `<WORKSTATION_NAME>` no certifica todos los drivers o redes de equipos futuros.

## 6. Directorios, ACL y cuenta operativa

Modelo futuro:

| Ruta | Cuenta de servicio | Administración |
|---|---|---|
| Program Files / binarios | Read/Execute, nunca Modify | Instalador/admin/SYSTEM escriben |
| ProgramData / config | Read; binding de UUID/raíz esperado inmutable para runtime | Admin/SYSTEM administran |
| ProgramData / data, logs | Modify únicamente dentro de esas carpetas | Backup/operación según política |
| ProgramData / secrets | Control de su propio directorio privado necesario para propietario/DACL; ciphertext CurrentUser | Sin acceso ordinario de terceros; admins conservan capacidad administrativa del SO |

En laboratorio, root/bin/config fueron protegidos con herencia cortada y sin Write para Everyone/Authenticated Users. La candidata solo administra sus directorios sintéticos. WindowsSecretStore vuelve privada su carpeta secrets al SID B; observador C queda denegado. No se modificaron ACL del Agent real, perfiles reales, spooler, impresoras ni del repositorio entero.

Cuenta recomendada: virtual, sin password hardcodeado/generado por scripts y sin PasswordNeverExpires. SCM gestiona el logon de servicio; no se crea usuario interactivo/RDP. Conservar nombre de servicio y perfil entre upgrades/uninstall para no perder claves DPAPI. No se certificaron intentos de login interactivo/RDP ni reboot completo.

Instancia única futura: binding per-machine de UUID/raíz bajo ACL administrativa + mutex global cross-session con DACL explícita + lock de archivo de la raíz canónica. El proceso manual debe rechazar una estación poseída por servicio, no escoger otra raíz y crear otro UUID. Global mutex/IPC cross-account del producto debe validarse en la fase de host real; no se reemplaza aquí el lock actual ni se abre el IPC del Agent a Everyone.

Safe defaults del laboratorio y estrategia futura: SafeValidation=true, PhysicalGlobal=false, AllowedJobId=null. El laboratorio no ejecutó consumidores de impresión ni habilitó routing.

## 7. Iteraciones y limpieza sin ocultar fallos

Una denegación `UnauthorizedAccessException` durante `ProtectAsService` puede indicar que `Modify` no alcanza para cambiar propietario/DACL de la carpeta `secrets`. En el laboratorio ajustar solo la carpeta sintética para el SID de servicio; no elevar privilegios generales ni modificar carpetas reales. Un servicio one-shot puede terminar antes de que `Start-Service` observe `Running`: evaluar también el reporte y estado final del SCM.

Eliminar servicios y procesos QA al terminar. Los perfiles de servicio sintéticos pueden permanecer cargados después de retirar el servicio; inventariar SID y ruta fuera del repositorio, esperar descarga normal o reinicio autorizado y nunca forzar la eliminación de perfiles reales.

## 8. Pruebas y tooling

- IdentityLabTests deben cubrir guards de raíces reales, identidades/fases, HTTPS-only, rechazo de entrada no sintética, conservación UUID y diagnóstico redactado.
- Ejecutar Agent completo y build Release sin fallos; conservar conteos, TRX y publish QA en evidencia local, sin instalar un paquete productivo.
- Compile/restore/build iniciales y laboratorio están separados del runtime real. QA project agregado a solución y referencia solo desde tests; el proyecto de Service productivo no depende del laboratorio.
- Validar Compose config --quiet y git diff --check; separar avisos preexistentes de regresiones.
- Backend/frontend/Python compile N/A: no se modificaron. No se repiten sus suites ni se reutilizan conteos anteriores como nuevos.

## 9. Aplicación futura por estación y cierre

Primera estación `<WORKSTATION_NAME>`: mantener UUID `<INSTALLATION_UUID>` y raíz existente como origen; NO asumir LocalAppData predeterminado. Requiere corte, backup coherente, consentimiento del propietario, handoff al servicio y validación antes de retirar el origen.

Segunda estación `<WORKSTATION_NAME>`: repetir primero validación sintética local bajo su cuenta virtual y sus drivers. Descubrir allí el propietario Windows y usar su propia raíz LocalAppData como origen, UUID `<INSTALLATION_UUID>`. No copiar blobs, perfiles ni SQLite entre estaciones.

No se necesita re-pairing por cambiar exclusivamente el protector DPAPI si un handoff autorizado conserva la credencial válida y la identidad. Si el secreto original es irrecuperable, detenerse y usar un procedimiento administrativo de recuperación definido; no saltar la unicidad del UUID ni crear una estación sustituta automáticamente.

Antes del corte, comprobar health de PostgreSQL, backend, frontend y HTTPS, así como current/head/target. Comparar hashes locales de identidad, credencial cifrada y SQLite; no afirmar garantías sobre archivos remotos no leídos.

Archivos de la fase: proyecto QA IdentityLab (csproj, LabOptions, LabPipe, LabProbe, Program), Invoke-ServiceIdentityLab.ps1, IdentityLabTests.cs, integración del test project/solución y este informe. Ningún cambio en código productivo de cifrado, Agent/Web, backend, frontend, Compose o .env.

La prueba sintética no autoriza migración DB, servicio permanente, pairing/re-pair real, impresión ni routing.

Siguiente microfase recomendada: host Windows Service productivo con cuenta virtual y rutas/ACL verificadas, primero contra fixtures; después solicitar autorización separada de corte/handoff real por estación. Este resultado NO autoriza migrar los secretos reales ni instalar el servicio productivo. DETENERSE.
