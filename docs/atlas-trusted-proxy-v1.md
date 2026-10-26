# Confianza explícita de Tailscale Serve — V1

Fecha: 2026-10-20. `<WORKSPACE>`, rama `feat/complete-care-context`.
HEAD: `3646b6bd7689d7f49941a8254ec327c3eda5682e`.

RESULT=PASS
TRUSTED_PROXY_VALIDATED=YES
HTTPS_FORWARDING_VALIDATED=YES
HEADER_SPOOF_PROTECTION=PASS

Los resultados se refieren a clientes **fuera de la frontera del host local** y
al listener HTTP directo 8001. No se autentica criptográficamente al proceso
`tailscaled` frente a otros procesos del mismo host; véase el límite explícito.

## Problema y recorrido identificado

Antes, Serve terminaba TLS y reenviaba a `127.0.0.1:<BACKEND_PORT>`. Docker entregaba al
backend tanto ese tráfico como las conexiones directas con peer `<TRUSTED_PROXY_IP>`.
Uvicorn solo confiaba por defecto en `127.0.0.1`; la dependencia existente
`secure_transport` rechazaba el esquema HTTP interno con 400.

Confiar globalmente en el gateway hubiera permitido a una conexión directa al
8001 fingir HTTPS mediante `X-Forwarded-Proto`. No se aplicó esa solución ni
`FORWARDED_ALLOW_IPS=*` ni una red Docker completa.

## Configuración final

```text
Cliente tailnet → HTTPS <PRIVATE_ATLAS_HOST>:443
               → Tailscale Serve
               → HTTP 127.0.0.1:<PROXY_PORT> (solo loopback Windows)
               → Docker, peer exacto <TRUSTED_PROXY_IP>
               → backend-tailscale / TrustedProxyIngress
               → mismas rutas FastAPI, esquema HTTPS reconocido

Cliente directo → backend 8001 → no interpreta cabeceras de proxy
                               → esquema HTTP → registro de agentes DENY
```

El gateway real se obtuvo del contenedor/red oficial `atlaspergamo_default`,
subnet `<UNTRUSTED_PROXY_SUBNET>`. **Se configura una IP, no ese subnet como confiable**.

Variables locales no sensibles añadidas a `.env`:

```dotenv
ATLAS_TRUSTED_PROXY_IP=<TRUSTED_PROXY_IP>
ATLAS_TRUSTED_PROXY_HOST=<PRIVATE_ATLAS_HOST>
ATLAS_PROXY_PORT=8002
```

No se modificó el target `0067_local_agent_registry` ni secretos existentes.
Si se recrea la red y cambia el gateway, revisar el valor explícito; no ampliar
la confianza a una red para evitar esa comprobación.

### Backend directo

Conserva 8001 y su comando permanente, añadiendo `--no-proxy-headers`.
No interpreta `Forwarded`/`X-Forwarded-*` para cambiar esquema/IP. La resolución
de tenant continúa usando Host, nunca `X-Forwarded-Host`. El registro de agentes
conserva íntegro su requisito HTTPS y RBAC.

### Entrada privada

Servicio Compose opcional `backend-tailscale`, perfil `tailscale`:

- Puerto publicado exclusivamente `127.0.0.1:<PROXY_PORT>:8000`.
- Misma aplicación y permisos; no nuevos modelos ni rutas de negocio.
- Uvicorn con `--no-proxy-headers --lifespan off`.
- No Alembic, bootstrap ni workers duplicados en este servicio.
- `TrustedProxyIngress` valida antes de la aplicación peer exacto, Host canónico,
  `X-Forwarded-Host` canónico y un único `X-Forwarded-Proto: https`.
- Rechaza valores críticos ausentes, duplicados, ambiguos o inconsistentes,
  Host ajeno, `Forwarded` residual y señal de Funnel.
- ProxyHeadersMiddleware de Uvicorn se usa dentro de esa frontera, con la única
  IP autorizada y una cabecera Proto saneada. No es middleware global.
- `X-Forwarded-For`, `X-Real-IP`, puertos, cabeceras Tailscale y demás metadatos
  reenviados se eliminan. No se confían para IP del actor, identidad o tenant.
  La IP visible aguas abajo permanece la del gateway, intencionalmente.
- No se convierten datos de identidad Tailscale en permisos Atlas.

Arranque de la entrada privada después de levantar el backend principal:

```powershell
docker compose --profile tailscale up -d --no-deps --build backend-tailscale
tailscale serve --bg --https=443 http://127.0.0.1:<PROXY_PORT>
```

Un arranque desde cero debe incluir el perfil; el Compose default no activa
este servicio opcional por sí solo. No se instaló ningún servicio de Agent.

## Validación real

Sin credencial del agente, tokens ni nuevo pairing:

| Recorrido / prueba | Resultado |
| --- | --- |
| HTTPS canónico → `device/peers` sin Authorization | 401 `Credencial de estación requerida` |
| HTTPS canónico → `pair` con `{}` sintético | 422 de campos requeridos; sin crear registro |
| HTTP directo 8001 + Proto/For/Host/Forwarded falsificados | 400 `Registro de agentes requiere HTTPS` |
| HTTP por IP LAN de esta PC al 8001 + cabeceras HTTPS | 400 |
| Host ajeno + Proto falso por 8001 | 404, tenant no disponible |
| Host ajeno por HTTPS canónico | 400, entrada de proxy no autorizada |
| Otro contenedor → entrada privada + cabeceras correctas | 400, peer no autorizado |
| Entrada privada sin cabeceras de Serve | 400 |
| IP LAN local `<LAN_IP>:8002` | TCP no accesible (timeout) |
| Windows listener de 8002 | Solo `127.0.0.1` |
| Listener de Serve 443 | Solo IPs Tailscale del nodo |

401 en la ruta de dispositivo demuestra que se superó la dependencia HTTPS y
se llegó a la comprobación de autenticación, **no** que se aceptara una credencial.
422 en el payload vacío no es pairing real ni validación de un código válido.

Serve 1.102.4 reemplaza Proto/Host/For según su conexión TLS; su reverse proxy
también elimina cabeceras de forwarding de entrada. Un `Forwarded` malicioso
enviado por HTTPS no se propagó: el backend recibió el recorrido saneado y
devolvió 401, no un cambio de esquema/tenant. Se distingue sanitizar de rechazar
la petición completa; el intento de manipular el contexto no tiene efecto.

.NET 10.0.13 repitió TLS real sin bypass: hostname y cadena confiable PASS,
TLS 1.2, certificado Let's Encrypt YE2 vigente hasta 2027-01-18; health/docs 200.

## Pruebas focales y tooling

- Nuevas pruebas de proxy: **29 PASS**.
- Ejecución final conjunta: proxy + comunicación segura + registry + aislamiento
  de organizaciones: **60 passed, 0 failed**, 512 warnings, 29.94 s.
- Frontend panel/dispositivos/destinos: **12 passed, 0 failed**, 5.82 s.
- Harness .NET contra HTTPS real: PASS; ninguna credencial o petición de agente.
- Python compile, Compose con perfil y `git diff --check`: PASS.
- Aviso LF/CRLF previo de AgendaMonthPanel ajeno a la tarea.
- No se repiten suites completas ni se cambia código .NET/frontend.

El primer intento de tests usó una opción de TestClient no disponible en la
versión instalada. Se corrigió únicamente el fixture de peer sintético; la
ejecución final anterior pasó. No se actualizaron dependencias para solventarlo.

## Datos, operación y preservación

Current/head/target permanecen `0067_local_agent_registry`. Se recreó el backend
para cargar `--no-proxy-headers`; su startup normal comprobó el target ya aplicado
sin aplicar una revisión nueva. El listener privado no ejecuta Alembic.

Snapshot pre/post: 102 tablas y 92 secuencias; huellas, schema, datos y secuencias
idénticos, incluidas auditorías y logs operativos (communication_logs=48).
No se añadieron auditorías de pairing, acceso autenticado o heartbeat.

Identidad del agente y blob DPAPI conservan sus hashes:

- Identidad SHA256: `<SHA256>`.
- DPAPI SHA256: `<SHA256>`.

Agente id 1, UUID `<INSTALLATION_UUID>`, conserva pairing,
endpoint anterior y estado Offline; diez impresoras, <PRINTER_NAME> id 5, sin cambios.
No se inició Agent ni se leyó/envió su token.

PostgreSQL healthy; backend HTTP local health 200, HTTPS health/docs 200 y
frontend 5174 200. Excepción HTTP ausente en `.env` y ambos listeners.

## Límite de confianza local

La protección diferencia los **listeners**, no solo la IP. El puerto público
8001 nunca considera confiable al gateway para forwarding. El 8002 pertenece a
la frontera del host local y solo acepta el gateway exacto. Otros contenedores,
LAN y clientes remotos no acceden como un proxy confiable.

Un proceso local con acceso a loopback puede enviar los metadatos esperados al
8002 y queda dentro de esa frontera. **No se afirma autenticar exclusivamente al
binario tailscaled ni resistir procesos locales hostiles o administradores de
la PC.** Requerir eso implica un canal autenticado adicional, fuera de esta
configuración de red. Sigue siendo necesaria una credencial Atlas válida para
cualquier operación de agente. Se mantiene el alcance del host confiable ya
requerido para Docker, sus secretos locales y DPAPI del usuario.

No se certificó desde una segunda PC física; aislamiento real comprobado con
otro contenedor, bind y conexión por interfaz LAN local, además de unit tests.

## Rollback y siguiente paso

La configuración anterior de Serve está guardada en
`<LOCAL_EVIDENCE_DIR>`.
Para recuperar el recorrido anterior (health funcional, registro aún bloqueado):

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:<BACKEND_PORT>
docker compose stop backend-tailscale
```

Mantener `--no-proxy-headers` en el backend directo; nunca reemplazarlo por
confianza global en gateway o wildcard. No revertir a una excepción HTTP.

Siguiente microfase: reanudar la migración protegida del endpoint del mismo
agente, con backup DPAPI, preservación de token, heartbeat y reconnect. No se
realizó esa migración en esta tarea.

Sin HTTP exception, 0068, pairing nuevo, impresión, commit, push ni deploy.

Actualización posterior: la migración HTTPS del agente se valida por separado,
sin alterar esta arquitectura. El estado Offline/endpoint previo descritos
arriba corresponden al cierre histórico de la microfase de proxy.

## Fuentes técnicas

- [Uvicorn: proxy headers y frontera de confianza](https://www.uvicorn.org/deployment/).
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
- [Reescritura de forwarding en Tailscale 1.102.4](https://github.com/tailscale/tailscale/blob/v1.102.4/ipn/ipnlocal/serve.go).
