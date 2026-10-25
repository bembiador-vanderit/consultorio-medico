# Atlas Local Agent — Secure Communication V1

RESULT=PASS — foundation implementada y validada.
TLS_PRODUCTION_VALIDATED=NO.

## Alcance e inventario real

Workspace <WORKSPACE>, rama feat/complete-care-context, HEAD
3646b6bd7689d7f49941a8254ec327c3eda5682e. Base/current/head/target 0067_local_agent_registry.
No requiere esquema nuevo ni 0068. No ejecuta impresión o descarga documental.

Se reutilizan AtlasRegistryClient, DPAPI CurrentUser, identidad persistente,
heartbeat/sync HTTPS, permisos local_agents:view/manage, tenant guard,
authorized_station_scopes direccional, PrintJob, ILocalTransport/ICloudTransport,
ILanDiscovery, AuthorizedRouteSelector, MockLocalTransport/MockCloudTransport y logs tipados.
Antes de esta fase el registro usaba polling de 30 s y timeout HTTP 10 s;
la ruta se elegía por disponibilidad después de policy, sin prueba de canal.
No existía WebSocket, listener LAN seguro, command execution o cola remota.

## HTTPS/TLS y configuración

AtlasRegistryClient conserva HttpClient con TLS 1.2/1.3, validación estándar de
cadena, hostname/SNI y fechas, sin callbacks que acepten certificados inválidos.
Se habilita comprobación de revocación. No cookies, redirects ni contraseña humana.
Timeout 10 s; límites de respuesta 1 MiB. No hay downgrade automático a HTTP.
Bearer propio sigue protegido por DPAPI y almacenado como hash en Atlas.
AuthenticationKind/credential reference permiten AgentBearer, UserSession,
ServiceIdentity y MutualTls futuro; no se implementa PKI/mTLS productivo.

No hay URL HTTPS productiva suministrada en este entorno. No se inventa dominio,
certificado o CA y no se cambia la confianza Windows. La instancia 5174/8001/5433
conserva sus puertos y configuración; la estación real puede permanecer Offline.

En producción debe proporcionarse una base URL HTTPS con cadena confiable,
SAN/hostname correcto, certificado vigente y reloj sincronizado. No se corrige
clock skew ignorando fechas del certificado. Un fallo TLS mantiene el transporte
desconectado; no borra el pairing ni cambia el endpoint silenciosamente.
El endpoint HTTP guardado por el pairing de desarrollo se conserva, pero el
cliente Production nuevo lo rechaza con TransportPolicyDenied sin tocar DPAPI.
Migrar esa asociación a un origen HTTPS validado requiere una microfase explícita;
no se envía la credencial a otro dominio por una simple redirección/configuración.

Referencias de diseño: [validación/SNI de HttpClient](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-sni)
y [despliegue/proxies confiables de Uvicorn](https://www.uvicorn.org/deployment/).

## Frontera Development / Production

Production es el default del constructor .NET y de la API. Una opción antigua
AllowLoopbackHttp en DPAPI o en PairingInput no permite HTTP en Production.
Un cliente de desarrollo debe construirse expresamente con CommunicationEnvironment.Development
y recibir además AllowLoopbackHttp=true. Solo acepta hosts literales localhost,
127.0.0.1 o ::1; no IP LAN, otra PC, dominio externo, credenciales/query en URL.
localhost HTTP se normaliza a 127.0.0.1 antes de conectar; el factory Development
deshabilita proxies para que DNS o proxy no conviertan la excepción en tráfico
fuera de loopback. Production conserva TLS end-to-end y validación normal aun
cuando la instalación utilice un proxy de salida.
Program construye Production por defecto; una ejecución de desarrollo requiere
además --environment Development. Ese modo no permite HTTP no-loopback ni omite
validación de certificados. No se habilitó este modo en la estación oficial ni
se publicó/reemplazó su ejecutable durante la fase.

El backend solo admite la excepción si TODAS estas condiciones coinciden:

- ATLAS_AGENT_ENVIRONMENT=Development.
- LOCAL_AGENT_ALLOW_LOOPBACK_HTTP=true.
- IP real de request.client loopback, no inferida de Host/Origin.
- Host loopback y sin Forwarded/X-Forwarded-For/X-Forwarded-Proto.

Host: localhost desde un cliente LAN, bridge Docker, proxy o nombre no-IP falla.
Production ignora la bandera. Ninguna excepción está habilitada oficialmente.
Docker Desktop presenta IP de bridge: no se la agrega a una lista de confianza
para hacer pasar loopback. Una futura prueba HTTP nativa requeriría conexión
loopback real y aislamiento explícito, no spoofing o headers reenviados.

HTTPS se obtiene del scope del servidor ASGI, no de headers inspeccionados aquí.
Un proxy TLS futuro necesita upstream privado, proxy autorizado explícitamente y
eliminación/reconstrucción de forwarding headers; jamás forwarded-allow-ips=* o
upstream accesible por clientes no confiables. Esta fase no instala ese proxy.

## Internet, reconexión y canal persistente

V1 mantiene polling saliente HTTPS hacia Atlas. No necesita listener del agente,
port forwarding, IP pública del agente o VPN. No se fuerza WSS sin cola/eventos.
ICloudTransport/ITransport siguen como contratos para un canal persistente futuro.

AgentRuntime aplica backoff exponencial con jitter acotado: primera demora 1–2 s,
crecimiento hasta techo 300 s; éxito reinicia el contador. No duplica submits de
pairing ni rotación incierta. En operación sana conserva intervalo 30 s.
Disconnected/Error representan reconexión pendiente con backoff. Degraded conserva
30 s para no expirar presencia por un problema de discovery/impresora. No se
añade un estado wire incompatible solo para dibujar una etiqueta nueva.
401/403 de credencial bloquean las solicitudes de esa instancia; la rotación
sigue siendo explícita. Fallos de red no borran pairing ni provocan nuevo alta.

## LAN y selección de ruta

LAN discovery sigue siendo la abstracción InMemoryLanDiscovery existente:
metadata de presencia, sin credenciales, documentos, sockets o trabajos.
No se afirma discovery multicast/mDNS real ni canal TLS LAN implantado.

El selector ahora exige policy explícita, target Online/no revocado, credencial
vigente y origen coherente. IsAvailable no basta. Para LAN exige además canal
seguro, autenticación mutua verificada y peer identity igual al target autorizado.
La ruta LAN exige además agente origen; móvil/tablet/browser sin agente usan
Atlas. La sesión de usuario solo autoriza el origen, nunca se convierte en
credencial del canal agente/relay. El canal usa referencia propia de agente,
servicio o certificado; rechaza UserSession como credencial de transporte.
Internet exige canal seguro autenticado hacia Atlas. Discovery no es autorización.
MockTransport solo modela esos estados en fixtures; no demuestra TLS real.
DenyAllAuthorizationPolicy continúa siendo el default para routing no habilitado.

| Escenario conceptual probado | Decisión |
| --- | --- |
| Misma LAN, policy positiva, canal mutuo y peer correcto | LAN segura simulada |
| Misma LAN/grupo sin autorización | DENY |
| Peer equivocado / LAN no disponible / firewall | Atlas HTTPS si policy y canal seguros |
| Redes locales distintas | Atlas HTTPS conceptual, sin VPN |
| Revocado, Offline, credencial vencida o tenant ajeno | DENY |

No se abre listener, no se firma un certificado de estación ni se transfieren
documentos. mTLS/peer proof real debe implementarse antes de activar LAN.

## Orígenes PC / móvil / tablet y PrintJob

PrintOriginType: WebDesktop, WebMobile, WebTablet, LocalAgent, System.
PrintOrigin conserva actor/context como referencias opacas; SourceAgent es
nullable para navegadores y obligatorio solo para origen LocalAgent.
PrintJob añade Origin opcional y SecurityClass; jobs locales/legacy existentes
continúan válidos. Un job futuro remoto debe aportar origen explícito validado.
No se cambia el journal ni el motor de impresión sintética existente.

Flujo futuro: browser móvil/tablet → sesión Atlas → autorización documental
→ target autorizado → transporte seguro. El dispositivo origen no necesita
agente y su sesión humana nunca se entrega al agente destino.
Origin y SecurityContext declarados en un contrato no prueban identidad: debe
vincularlos un autenticador servidor con sesión, tenant, centro y policy vigente.

## Disponibilidad de destinos, no permiso de imprimir

GET /api/v1/local-agents/destinations, HTTPS obligatorio, local_agents:view y sesión humana.
Filtros center_id, workgroup_id, paper_name y origin_type. Tenant por contexto
existente; centros activos, y para no-admin intersección con sus centros asignados.
Grupo se valida contra centro; Offline, Degraded, revocado y printer no disponible
no se ofrecen. Papel por nombre anunciado (no garantía universal de dimensiones).
No inventa autorización por compartir grupo/red/organización.

Respuesta acotada, no-store, solo metadata:
availability_only=true, execution_enabled=false, document_authorization_required=true,
route=ATLAS_HTTPS, lan_channel_available=false. No tokens, documentos, job execution
o URL firmada. origin_user proviene de la sesión, no del query. origin_type es
una pista de presentación; jamás una autorización ni una identidad de SYSTEM.

La consulta es lectura: no genera auditoría falsa de modificación. Auditoría de
configuración, pairing, scope y revocación se conserva en el sistema existente.
Una futura creación/ejecución de trabajo necesitará permiso documental específico,
clase de seguridad, auditoría de actor/documento/destino y persistencia transaccional.
La visibilidad del destino no concede acceso clínico/financiero.

Frontend incorpora solo listAvailableDestinations y contratos tipados, sin UI
de Print Management, botones de imprimir ni endpoint de envío. Respetan 403.

## Command envelope, replay e idempotencia

CommandEnvelope contiene CommandId único, CommandType tipado (solo
AvailabilityNotification en V1), Source, TargetAgent, IssuedAt, ExpiresAt,
PayloadReference opaco y CommandSecurityContext. Clasificaciones: General,
Administrative, Financial, Clinical, SensitiveClinical.
Contexto incluye organización/centro/grupo, clase, tipo de autenticación y
ValidationReference para policy/firma futura; NO es una firma verificable por sí solo.

Valida lifetime máximo 5 min, emisión futura <=30 s, expiración estricta,
campos/enums/origen-auth coherentes. ICommandAuthenticator debe aprobar y vincular
identidad, target y contexto antes del registro. No acepta payload arbitrario.
InMemoryCommandInbox almacena hash de intención: mismo ID/intención Duplicate,
payload distinto Conflict, inválido/no autenticado Denied. Concurrencia: una
aceptación lógica. Límite 4096 sin eviction que permita replay; saturación DENY.

Es FOUNDATION process-local, sin ejecución ni persistencia, sin garantía de
idempotencia durable tras reinicio. No se debe conectar a impresión antes de
disponer de inbox/estado transaccional durable, expiración y política de reloj.
Si esa evolución requiere esquema nuevo, detenerse antes de 0068.

## Privacidad y preservación

No PHI, bytes documentales o secretos en discovery/envelopes/logs. Logs existentes
siguen siendo tipados/allowlist. ToString de job/origen/envelope/referencia de
credencial omite documento, contexto y secretos. Las refs no deben codificar PHI.
La clasificación prepara filtros; no implementa una política clínica completa.

La estación oficial existente se conserva Offline, sin arrancar ni publicar
agente nuevo. No se cambia endpoint/credencial, GUID, pairing, printer catalog,
historia ni permisos de esa estación. No se modifica .env/Compose, no se habilita
loopback HTTP, no se reinicia stack ni se ejecutan migraciones.

## Validación y límites

TLS en fixtures: certificado válido confiado solo por política del cliente de
test, certificado vencido, hostname incorrecto y CA no confiable con factory
productivo. Certificados/keys de prueba temporales, no instalados en Root/CA de
Windows ni en Atlas. Schannel requirió importación temporal de clave de fixture
sin PersistKeySet; no se relajó la validación para resolver el fallo inicial.

| Validación | Resultado verificado |
| --- | --- |
| .NET todos los tests disponibles | 73 PASS, 1 omitido opt-in, 0 FAIL |
| TLS focal incluido en .NET | 4 PASS (no se suma dos veces) |
| Backend focal | 21 PASS, 367 warnings, 0 FAIL; 17.06 s |
| Frontend focal | 12 PASS, 0 FAIL |
| Frontend completo | 513 PASS, 0 skipped, 0 FAIL; 360.63 s |
| Frontend build | PASS, 207 módulos, 9.99 s |
| .NET build / analizadores Service + Tray | PASS, 0 errores / 0 warnings |
| Python compile / Compose config / diff check | PASS |
| Backend completo | 657 PASS, 29 skipped opt-in, 0 FAIL; 1150.28 s; 14858 warnings |

El omitido .NET requiere expresamente API/DB PostgreSQL desechables en 18067;
no se activa ese fixture ni se lo redirige a la estación oficial. El resto de
pruebas TLS sí usa sockets SSL reales loopback, sin instalar confianza del sistema.
Warnings conocidos: bundle frontend >500 kB (717.38 kB; gzip 196.46 kB),
deprecaciones/fixtures backend y aviso LF/CRLF previo de AgendaMonthPanel.tsx.
No se ocultan warnings cambiando funcionalidades ajenas a esta microfase.

Snapshot postimplementación: 102 tablas y 92 secuencias idénticas al precheck,
sin modificación de filas/esquema/auditorías. Hashes de .env, Compose, identidad
y blob DPAPI idénticos. Agente oficial id=1 / UUID existente / credential_revision=1,
sin revocar ni cambiar last_seen. Evidencia en
<LOCAL_EVIDENCE_DIR>
Snapshot final tras las suites: misma comparación sin diferencias de filas,
esquema o secuencias; .env, Compose, GUID y blob DPAPI conservan sus hashes exactos.
Estado final: PostgreSQL healthy; health 8001 / docs 8001 / frontend 5174 HTTP 200;
current/head/target 0067. Sin errores recientes SQL/startup inesperados observados.
Sin procesos del agente/Tray activos. No se instaló servicio o autoarranque.
No hay listener 443/8443 ni configuración Tailscale Serve en la PC inspeccionada;
no se suministró otro origen HTTPS de esta instancia para una validación productiva.

Archivos funcionales de esta fase: contratos Core de comunicación, seguridad,
origen/PrintJob y command envelope; AtlasRegistryClient, AgentRuntime y Program;
guard y endpoint de local_agents, servicio agent_destinations; cliente frontend
agentDestinations. Tests focales nuevos/ajustados, este informe y README.
Se preservan los cambios pendientes anteriores del workspace. No se modifica
el esquema, configuración funcional, Document Designer, clínica o finanzas.
No hubo prueba contra URL/certificado productivo disponible: TLS_PRODUCTION_VALIDATED=NO.

Siguiente microfase: proporcionar URL HTTPS real y proxy/boundary confiables,
validar cadena/hostname/revocación/reloj en esa instalación y migrar el endpoint
de la asociación mediante procedimiento autenticado, sin perder identidad.
Después, prueba controlada de dos estaciones y canal LAN mutuamente autenticado,
siempre antes de ejecutar trabajos reales. No commit, push, deploy o impresión.
