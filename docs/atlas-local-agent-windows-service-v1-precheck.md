# Windows Service V1 — detenido antes de implementación/instalación

RESULT=FAIL
WINDOWS_SERVICE_READY=NO
SERVICE_AUTO_START_READY=NO
DPAPI_SERVICE_COMPATIBLE=NO
PAIRING_PRESERVED=YES
DURABLE_STORE_PRESERVED=YES
SINGLE_INSTANCE_PROTECTED=NO
SAFE_DEFAULTS_PRESERVED=YES
MULTI_STATION_SERVICE_VALIDATED=NO
PHYSICAL_PRINTS_SENT=0

FAIL significa aceptación de servicio no alcanzada: se activó la condición de detenerse del apartado 6 de la solicitud. No se detectó ni provocó una regresión del agente manual. NO se instaló servicio, migró secreto, eligió cuenta de arranque, cambió ACL ni implementó host nuevo.

## Precheck reutilizable

Antes de instalar, verificar revisión de base y arranque, salud de servicios, identidad de Windows, raíz del agente, estado del registro, impresoras y huellas de `identity.json`, `station.json`, secreto DPAPI cifrado y SQLite. Conservar la evidencia operativa fuera del repositorio. Un heartbeat o inventario remoto no certifica que el servicio pueda acceder al perfil, credencial o impresoras de otra estación.

## Bloqueo de cuenta y DPAPI

WindowsSecretStore.cs usa CryptProtectData/CryptUnprotectData con flag 1 (UI_FORBIDDEN), sin CRYPTPROTECT_LOCAL_MACHINE: protección CurrentUser. El secreto `secrets/secret.atlas-registry-v1.bin` está protegido por DACL para su propietario Windows. No basta dar permisos NTFS a otra cuenta: el contexto criptográfico tampoco es el mismo.

LocalSystem, LocalService, NetworkService y una cuenta dedicada diferente no pueden asumirse compatibles con ese secreto CurrentUser existente. No se ejecutó una prueba real bajo esas cuentas ni se afirma un fallo observado de decrypt: la incompatibilidad de cambiar de identidad se determina por el alcance criptográfico documentado y la ACL real.

Microsoft documenta que CurrentUser asocia el secreto al usuario y que LocalMachine amplía el alcance de descifrado. No se cambiará a LocalMachine como atajo ni se abrirá el directorio a Everyone/SYSTEM para simular compatibilidad.

Referencias primarias: [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), [DataProtectionScope](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.dataprotectionscope).

Ejecutar un servicio con la MISMA cuenta propietaria podría conservar CurrentUser, sujeto a validar logon de servicio, perfil, impresoras y ACL. Si la propietaria fuese una cuenta administrativa, elegirla como cuenta persistente ampliaría el riesgo y requeriría una decisión explícita. No se solicita contraseña por chat ni se incorpora ninguna a scripts o artefactos.

## Arquitectura inspeccionada y consecuencias

- Program.cs es un host CLI manual; el proyecto no usa Generic Host, AddWindowsService/UseWindowsService, BackgroundService ni ServiceBase. Registrar el EXE actual no lo convierte por sí solo en un servicio SCM.
- Tray ManagedAgentHost inicia un hijo manual, redirige stdin y lo cancela por EOF. Ese ownership no es el ciclo de vida de un servicio Windows; no se cambiará sin resolver la cuenta.
- DefaultRoot usa LocalApplicationData del usuario. La raíz emparejada puede diferir de la predeterminada. Un servicio bajo otra cuenta resolvería otra carpeta y podría crear otra identidad si se deja el comportamiento LoadOrCreate: debe fallar cerrado ante raíz/UUID incorrectos, no crear otra estación.
- SQLite/logs/secrets se resuelven desde root absoluto. La ruta no depende solo de cwd, pero sí de identidad/configuración de arranque. No se mueve a ProgramData sin backup y plan explícito.
- Endpoint, token y asociación están juntos en el blob DPAPI. Endpoint es configurable en el flujo existente; no se necesita hardcodear el hostname en un servicio.
- IPC: nombre depende de usuario + raíz; servidor DACL solo SID actual, rechazo de clientes remotos; cliente valida dueño SID. Una cuenta de servicio distinta también cambia esta frontera: no puede resolverse abriendo permisos a cualquiera.
- Impresoras: EnumPrinters incluye locales y conexiones del contexto actual. No se garantiza que un servicio con otra cuenta/session 0 vea las mismas impresoras; requiere validación bajo la identidad elegida, no modificar drivers/defaults.
- Instancia única actual: service.lock exclusivo por raíz y mutex del Tray. Existe protección manual por raíz, pero no se ha certificado servicio + manual bajo distintas cuentas/rutas. Por eso SINGLE_INSTANCE_PROTECTED=NO para esta aceptación, no una negación del lock existente.
- Safe defaults actuales: físico global false, sin grant por defecto; consumidor oficial solo se inicia con --routing-safe-validation. El servicio futuro deberá iniciarlo explícitamente conservando barreras SQLite/UNKNOWN y sin aceptar flags físicos por accidente.
- Shutdown manual ya usa CancellationToken, drain y StopAsync. No se certifican SCM Stop/Start, delayed start ni recovery porque no se implementó/instaló un servicio.

## Decisión segura necesaria

Recomendación: microfase separada de identidad de servicio y credenciales. Elegir una cuenta dedicada de mínimos privilegios POR PC y definir una transferencia/reprotección local controlada, sin plaintext en disco, sin copiar secretos entre PCs y conservando UUID/SQLite/endpoint. Requiere autorización específica antes de migrar credenciales reales. Primero validar con secretos sintéticos, ACL y perfil de servicio; luego autorizar la operación real por estación. No prometer preservación criptográfica sin esa prueba.

Alternativa de menor cambio: servicio bajo la misma cuenta Windows propietaria, con raíz existente explícita. Si esa cuenta es administrativa, debe aceptarse expresamente el riesgo y validarse el contexto real; no es la recomendación de mínimos privilegios. Cualquier ingreso de credenciales Windows lo realiza el usuario mediante un canal seguro local, nunca el chat.

No sustituir el requisito por una tarea programada/logon task ni afirmar Windows Service READY. No instalar primero y arreglar después el pairing. Mantener el modo manual actual hasta decidir.

## Criterios antes de implementar el servicio

- Seleccionar cuenta y perfil de mínimos privilegios; documentar la migración CurrentUser y validar con secretos sintéticos antes de usar credenciales reales.
- Confirmar UUID, raíz, SQLite/WAL y catálogo de impresoras por estación, sin asumir equivalencia entre contexto interactivo y servicio.
- Diseñar host SCM, arranque, recuperación y parada ordenada; verificar exclusión mutua entre servicio y modo manual.
- Preservar SafeValidation y la denegación física por defecto. Un estado de impresión incierto nunca debe provocar reimpresión automática.
- Respaldar antes de cualquier corte real y conservar una vía de reversión probada sin exponer secretos.
