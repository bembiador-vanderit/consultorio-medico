# Atlas Web HTTPS — arquitectura y validación segura

## Resultado y desviación de alcance

```text
RESULT=FAIL
HTTPS_WEB_READY=YES
PAIRING_HTTPS_BLOCK_RESOLVED=YES
READY_FOR_PAIRING_TEST=YES
```

El resultado histórico de la comprobación HTTPS no debe confundirse con una
certificación de pairing. Para una validación sin persistencia, comprobar el
control de transporte antes de enviar una solicitud autenticada que genere código.
Si un operador crea un código durante la prueba, detener el flujo y tratar esa
vinculación como una operación separada; no borrar ni revocar credenciales sin
autorización.

## Arquitectura y cambio exacto

URL de Atlas Web: **https://<PRIVATE_ATLAS_HOST>/**, sin puerto de desarrollo.

```text
Cliente autorizado de tailnet
  → HTTPS :443 / Tailscale Serve
      /                 → http://127.0.0.1:5174        (frontend existente)
      /api              → http://127.0.0.1:<PROXY_PORT>/api    (entrada API protegida)
      /docs             → http://127.0.0.1:<PROXY_PORT>/docs
      /openapi.json     → http://127.0.0.1:<PROXY_PORT>/openapi.json
      /redoc            → http://127.0.0.1:<PROXY_PORT>/redoc
```

El frontend y la API comparten origen HTTPS; las peticiones `/api/v1` no pasan
por el proxy HTTP de Vite. Serve elimina el mount point al reenviar: se conserva
explícitamente `/api` en el destino para no perder el prefijo original.

Cambio operativo: handlers persistentes de **Tailscale Serve**,
con `--bg --https=443 --set-path=...` y los destinos anteriores. No se añadió
Funnel, listener público, HTTP de Serve, certificado, CA, contenedor ni servicio.
No se reinició backend, frontend o PostgreSQL. No se modificó `.env`, Compose,
Vite, backend, autenticación, RBAC, impresión o contrato PrintJob.

Estado previo: el handler `/` apuntaba a 8002 y devolvía 404 porque era la API,
no Atlas Web. Se conservó la misma entrada segura para todas las rutas API.

## Transporte, host y certificado

- Entrada privada sigue publicada solo en `127.0.0.1:<PROXY_PORT>`.
- `TrustedProxyIngress` conserva el peer exacto `<TRUSTED_PROXY_IP>`, Host canónico,
  `X-Forwarded-Host` canónico y un único `X-Forwarded-Proto: https`.
- Listener directo 8001 conserva `--no-proxy-headers`.
- No confianza global en gateway/red, wildcard ni headers de clientes directos.
- Serve reemplaza forwarding recibido con los valores del transporte TLS real;
  el middleware limpia los metadatos antes de la aplicación.
- Excepción `LOCAL_AGENT_ALLOW_LOOPBACK_HTTP` ausente/OFF. No se cambia la
  validación HTTPS de registro.
- Certificado público válido para `<PRIVATE_ATLAS_HOST>`: comprobar SAN/CN, vigencia,
  cadena y revocación en cada despliegue; registrar huella solo en evidencia local.
- TLS 1.2+, hostname, cadena Windows y revocación online deben validarse,
  sin callback de aceptación, `--insecure`, CA agregada o exportación de claves.

## Comprobaciones

| Prueba | Resultado |
| --- | --- |
| Frontend HTTPS `/` | 200, HTML React y login visibles |
| API HTTPS `/api/v1/health` | 200 |
| HTTPS `/docs` y `/openapi.json` | 200 |
| Backend HTTP health y docs | 200 / 200 |
| Frontend HTTP 5174 | 200, configuración previa conservada |
| PostgreSQL | healthy |
| Sesión por HTTPS | Verificar login, `/auth/me` y registry sin exponer credenciales |
| Restauración de sesión | Verificar refresh y `/auth/me` por la entrada protegida |
| API/origen | Axios `/api/v1`, same-origin, sin nueva regla CORS |
| Recursos | Scripts relativos `/@vite/client` y `/src/main.tsx`; login con estilos; sin errores de consola observados |
| Mixed content | No endpoints HTTP/WS absolutos en fuentes TS/TSX; navegador HTTPS sin alertas de mixed content |
| HMR/WebSocket real | Si se usa Vite en desarrollo, comprobar WSS :443 sin registrar token efímero |
| SSE/WebSocket de negocio | No implementación encontrada en fuentes; no se inventa certificación de un flujo inexistente |
| HTTP pairing-codes, cuerpo vacío sin sesión | 400 `Registro de agentes requiere HTTPS` |
| HTTPS pairing-codes, mismo cuerpo sin sesión | 403 `Not authenticated`; superado control de transporte, sin generar código |
| HTTPS `/pair`, cuerpo vacío | 422 por campos requeridos; sin asociación ni credencial |
| HTTP directo + forwarding falsificado | 400, sigue siendo HTTP |
| HTTPS + forwarding malicioso | Serve lo sanea; 403 de autenticación, no cambio de contexto |
| HTTPS Host ajeno con SNI canónico | 400 `Entrada de proxy no autorizada` |
| Otro contenedor a entrada privada con cabeceras correctas | 400, peer no autorizado |

El intento PowerShell de Host falso rechazó en TLS antes de HTTP; se repitió con
curl manteniendo SNI canónico y Host HTTP ajeno para comprobar específicamente
el 400 del proxy. No se registra el resultado anterior como HTTP exitoso.

HTTP conserva su arquitectura previa, no se redirige en esta microfase. No es un
bypass: creación de código, pairing y endpoints de agente siguen denegados por
HTTP incluso con cabeceras falsas. Debe usarse la URL HTTPS para Administración.

Cookies/sesión: se conserva la configuración existente de desarrollo,
HttpOnly/SameSite=Lax y ruta `/api/v1/auth`; `Secure` depende de `environment`,
actualmente development. La comunicación comprobada usa HTTPS, pero el
endurecimiento de cookies Secure y la retirada/redirección general de HTTP
quedan como deuda antes de certificar una publicación productiva completa.
No se afirma que habilitar esta URL certifique toda la seguridad del despliegue.

No extraer contraseñas, cookies ni tokens de una sesión para replicarla.

## Pairing: límite de una prueba de transporte

Una respuesta HTTPS autenticada de `pairing-codes` puede crear un código real y
no debe emplearse como prueba sin persistencia. Para validar el transporte sin
generar código, enviar un cuerpo vacío sin sesión: HTTP debe fallar por HTTPS y
HTTPS debe avanzar hasta autenticación. Conservar cualquier evidencia de
vinculación manual en un registro operativo privado, no en esta guía.

## Integridad y pruebas

- Comparar current/head/target y huellas históricas de clínica, finanzas,
  permisos, agentes y PrintJobs antes y después de cambiar solo el proxy.
- Registrar pruebas focales de proxy/transporte/registry y login/sesión; conservar
  conteos, fechas, hashes y snapshots en evidencia operativa externa al repositorio.
- No atribuir a la configuración HTTPS una operación manual de pairing ni
  presentarla como prueba sin persistencia.

## Rollback documentado, NO ejecutado

Primero comprobar que no existan handlers agregados por otros operadores. Para
volver al estado inicial de esta microfase sin reset global:

```powershell
tailscale serve --bg --https=443 --set-path=/ http://127.0.0.1:<PROXY_PORT>
tailscale serve --bg --https=443 --set-path=/api off
tailscale serve --bg --https=443 --set-path=/docs off
tailscale serve --bg --https=443 --set-path=/openapi.json off
tailscale serve --bg --https=443 --set-path=/redoc off
```

Esto recupera API raíz, no deshace el pairing manual ni modifica registros.
HTTPS Web queda activo al cerrar, conforme al objetivo autorizado.

## Deudas y cierre

- Deuda UX: el frontend convierte cualquier error excepto 503 en mensaje genérico
  de permisos. El HTTP 400 de HTTPS debe explicarse de forma específica en una
  tarea separada; no hubo rediseño ni cambio del manejador en esta microfase.
- Endurecimiento productivo de cookies/HTTP y reemplazo de servidor Vite de
  desarrollo son trabajo posterior, no bypass añadido aquí.
- Toda vinculación manual requiere revisión explícita de la estación antes de
  cualquier aceptación de routing. No se amplían permisos por red/grupo.

La configuración HTTPS no autoriza por sí misma migraciones, cambios RBAC,
impresión ni routing de impresión.

Referencias de configuración: [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[rutas de proxy de Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[WebSocket tras reverse proxy de Vite](https://v6.vite.dev/config/server-options.html#server-hmr).
