# HTTPS Foundation V1 — Tailscale Serve → Atlas Backend

Fecha: 2026-10-20. Workspace: `<WORKSPACE>`.

## Estado de esta ejecución

`RESULT=PASS` para HTTPS Foundation. Tras la habilitación humana de Serve/HTTPS
se configuró el proxy y se comprobó TLS real desde Windows, curl y .NET.

- `HTTPS_ENDPOINT_READY=YES`
- `TLS_TRUST_VALIDATED=YES`
- `TAILSCALE_SERVE_ACTIVE=YES`
- `TAILSCALE_FUNNEL_ACTIVE=NO`
- `PUBLIC_INTERNET_EXPOSURE=NO` para el endpoint Serve creado.
- `TLS_PRODUCTION_VALIDATED=NO` para Atlas Local Agent.
- No migrar el endpoint protegido del agente en esta microfase.

## Precheck

- Rama `feat/complete-care-context`.
- HEAD `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
- Current/head/target `0067_local_agent_registry`.
- Tailscale Windows `1.102.4`; estado Running/Online.
- MagicDNS real: `<PRIVATE_ATLAS_HOST>`.
- IPs del nodo: `100.68.21.91`, `fd7a:115c:a1e0::ec34:155c`.
- Configuración inicial de Serve: `{}`; sin listener 443/8443.
- Backend local `/api/v1/health` y `/docs`: 200; frontend 5174: 200.
- `/` del backend devuelve 404 por diseño; no es la interfaz web ni el health.
- Excepción `LOCAL_AGENT_ALLOW_LOOPBACK_HTTP` ausente/desactivada.

## Arquitectura autorizada

`Cliente tailnet → HTTPS <PRIVATE_ATLAS_HOST>:443 → Tailscale Serve → HTTP 127.0.0.1:<BACKEND_PORT>`

No se cambia Compose, `.env`, puertos, frontend, backend ni base de datos.
El upstream HTTP es el salto local del proxy, no una excepción HTTP para el agente.
No se habilita HTTP remoto mediante Serve.

## Configuración y respaldo

Sintaxis comprobada con la ayuda de la versión instalada:

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:<BACKEND_PORT>
tailscale serve status --json
```

El primer intento indicó `Serve is not enabled on your tailnet` y solicitó
habilitación administrativa. No se ejecutó ningún comando Funnel.
Se detuvo únicamente el cliente CLI que esperaba esa confirmación, para evitar
una configuración tardía sin verificar. El daemon Tailscale sigue activo.
Estado de Serve al cerrar ese primer intento: `{}`. No fue necesario retirar
handlers. El usuario confirmó posteriormente la habilitación. Se volvió a
ejecutar el mismo comando, que terminó correctamente y publicó únicamente:

```json
{
  "TCP": { "443": { "HTTPS": true } },
  "Web": {
    "<PRIVATE_ATLAS_HOST>:443": {
      "Handlers": { "/": { "Proxy": "http://127.0.0.1:<BACKEND_PORT>" } }
    }
  }
}
```

No existe `AllowFunnel` habilitado. La CLI informa `tailnet only`.

Respaldo de configuración inicial y hashes de preservación:
`<LOCAL_EVIDENCE_DIR>`.
`serve-before.json` contiene `{}`; no contiene claves privadas ni credenciales.

## Validación TLS ejecutada

Endpoint canónico: `https://<PRIVATE_ATLAS_HOST>/`.
Usar exactamente ese hostname, no una IP ni un alias que no figure en el SAN.
No usar `-k`, `--insecure`, trust-all callbacks ni certificados de prueba.

Harness externo al código Atlas:
`<LOCAL_EVIDENCE_DIR>`.
Compilado con .NET SDK 10.0.402: cero errores y cero advertencias.
Utiliza `SslStream` con validación normal de hostname/cadena, revocación Online,
TLS 1.2/1.3 y `HttpClient` sin bypass, sin cookies, sin redirecciones y sin tokens.
Ejecución real con .NET 10.0.13, sin ningún callback de certificados:

| Comprobación | Resultado |
| --- | --- |
| Subject | `CN=<PRIVATE_ATLAS_HOST>` |
| SAN | `DNS=<PRIVATE_ATLAS_HOST>` |
| Issuer | `CN=YE2, O=Let's Encrypt, C=US` |
| Inicio de vigencia UTC | `2026-10-20T10:24:03Z` |
| Fin de vigencia UTC | `2027-01-18T10:24:02Z` |
| Huella pública SHA1 | `4140B424FE60F902A6FE82965A86E4732E5D7A87` |
| Protocolo negociado | TLS 1.2 |
| Cipher suite | `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` |
| Hostname por SslStream | PASS |
| Cadena del sistema / revocación Online | PASS |
| .NET HttpClient health / docs | 200 / 200 |
| Windows PowerShell HTTPS health / docs | 200 / 200 |
| curl Windows HTTPS health / docs | 200 / 200 |

Cadena construida y aceptada por Windows:
`<PRIVATE_ATLAS_HOST> → YE2 → Root YE → ISRG Root X2 → ISRG Root X1`.
No se agregó ninguna CA al sistema, no se exportaron claves privadas ni se
desactivó revocación, hostname o validación de cadena. No hay pinning rígido.
La huella anterior es evidencia, no una restricción de renovación.

## Alcance de red y persistencia

Serve publica dentro de la tailnet conforme a sus controles de acceso; no es
una publicación pública de Internet. Funnel está prohibido en esta fase.
No se cambia router, port forwarding ni firewall. Esto no audita reglas de
router preexistentes ni certifica la seguridad completa de la LAN.
Los puertos Atlas existentes conservan su publicación anterior; esta fase no
los restringe ni los expone de una forma nueva.

`--bg` es el modo persistente de Serve, independiente de la sesión CLI.
No se reinicia Windows ni se certifica empíricamente un reinicio de la máquina.
La CLI inicial terminó y consultas independientes posteriores conservaron la
misma configuración y dieron HTTPS 200: persistencia de sesión CLI comprobada.
La disponibilidad futura depende de que el servicio Tailscale y Atlas estén
activos; Serve gestiona su certificado conforme a su funcionamiento normal.

La inspección real de listeners confirmó exclusivamente
`100.68.21.91:443` y `[fd7a:115c:a1e0::ec34:155c]:443`, propiedad de Tailscale;
no hay listener 443 en `0.0.0.0`, `::`, loopback ni dirección LAN. MagicDNS
resolvió al `100.68.21.91` del nodo. No se agregó listener HTTP de Serve ni 8443.
La limitación tailnet-only se verificó mediante configuración, binding y estado
de Serve; no se utilizó una segunda PC externa para un sondeo desde Internet.

Referencias oficiales:

- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
- [CLI Serve y persistencia](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Rollback

La configuración inicial era vacía. Para retirar únicamente el handler agregado:

```powershell
tailscale serve --bg --https=443 off
tailscale serve status --json
```

Verificar primero que no haya handlers ajenos agregados posteriormente. No usar
un reset global si ya hay otros servicios. El resultado esperado para esta
ejecución es `{}`; backend 8001 y frontend 5174 deben seguir respondiendo.

## Límites

HTTPS del proxy no equivale a conexión TLS validada del agente real. Su pairing,
UUID, credencial DPAPI y endpoint anterior no se modifican. No hay heartbeat,
impresión, routing ni Print Management nuevos. La migración del endpoint y la
comprobación de autorización del agente a través del proxy son otra microfase.

## Preservación y cierre

- Current/head/target final: `0067_local_agent_registry`; no se ejecutó upgrade.
- PostgreSQL healthy; backend local health/docs 200; frontend 5174 200.
- Comparación del snapshot final con el cierre previo de Secure Communication:
  102 tablas y 92 secuencias; ninguna tabla/huella/schema/secuencia nueva,
  perdida o cambiada. Incluye configuración, finanzas y auditorías.
- Registry: una estación, diez impresoras; <PRINTER_NAME> mantiene id 5. Agente id 1,
  UUID `<INSTALLATION_UUID>`, sigue Offline; sin heartbeat nuevo.
- Hashes de `.env`, Compose, identidad y blob DPAPI idénticos a los respaldados.
  No se descifró ni copió el token. Endpoint protegido del agente no modificado.
- Excepción HTTP y entorno Development no configurados en backend/.env.
- Harness .NET: build con cero errores/advertencias; conexión TLS y dos GET PASS.
- `docker compose config --quiet` y `git diff --check` PASS. Existe el aviso
  previo LF/CRLF de `AgendaMonthPanel.tsx`, ajeno a esta tarea.
- Solo documentación nueva dentro de Atlas: este archivo. El harness y las
  evidencias quedan fuera del repositorio, en el directorio de respaldo indicado.
- Sin cambios de código Atlas, Compose o `.env`; no se repiten suites completas.
- No se reiniciaron servicios Atlas. No impresión, 0068, servicio Agent
  permanente, commit, push ni deploy.

Siguiente microfase: migración segura del endpoint protegido del agente existente
al hostname HTTPS, validando credencial, esquema HTTPS reconocido por backend,
heartbeat, catálogo y reconexión. No está autorizada ni ejecutada en esta fase.

Actualización posterior: la [microfase de confianza del proxy](atlas-trusted-proxy-v1.md)
separó la entrada privada en `127.0.0.1:<PROXY_PORT>`. Serve ahora apunta a ese puerto,
no a 8001; el recorrido inicial de este informe queda como evidencia histórica.
El agente todavía no se migró ni se conectó.
