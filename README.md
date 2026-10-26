# Consultorio Médico

Sistema de gestión profesional para consultorios médicos, inicialmente orientado a cardiología.

## Estado

La **Fase 0** establece infraestructura local con React/Vite, FastAPI y PostgreSQL.

## Requisitos

- Docker Desktop con Docker Compose

## Inicio rápido

Después de clonar el repositorio, todo el código y la configuración estructural necesarios para construir la aplicación están versionados en Git. Los secretos, la configuración local y los datos de PostgreSQL permanecen fuera del repositorio.

### Windows PowerShell

1. Crear la configuración local:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Editar `.env` y establecer valores propios para:
   - `POSTGRES_PASSWORD`
   - `DATABASE_URL` (debe usar el mismo usuario, contraseña, base de datos y host definidos arriba)
   - `SECRET_KEY`
   - `INITIAL_ADMIN_PASSWORD`

   **No reutilizar las credenciales de ejemplo ni subir `.env` al repositorio.**

3. Validar que Docker Compose recibió todas las variables obligatorias:

   ```powershell
   docker compose config -q
   ```

   Si falta una variable obligatoria, Compose detendrá la ejecución con un mensaje indicando qué variable debe configurarse.

4. Construir e iniciar:

   ```powershell
   docker compose up -d --build
   ```

5. Comprobar migraciones:

   ```powershell
   docker compose exec backend alembic current
   ```

6. Ejecutar pruebas:

   ```powershell
   docker compose exec backend python -m pytest -q
   ```

### Linux / macOS

```bash
cp .env.example .env
# Editar .env y establecer los secretos locales antes de continuar
docker compose config -q
docker compose up -d --build
docker compose exec backend alembic current
docker compose exec backend python -m pytest -q
```

## Servicios disponibles

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000>
- Health check: <http://localhost:8000/api/v1/health>
- Documentación OpenAPI: <http://localhost:8000/docs>

### Instancia local oficial Atlas Pérgamo

Cada instalación usa su propio directorio de trabajo, proyecto Compose y puertos.
Los valores de la plantilla anterior son orientativos; consulte su `.env` y
`docker compose config` antes de operar una instancia.

La base y el target permanente de arranque deben mantenerse sincronizados.
Compose ejecuta ese target antes de Uvicorn;
no se usa `upgrade head` ni se aplica una revisión posterior automáticamente.
No hace falta el override temporal de Uvicorn utilizado durante la recuperación.

Usar únicamente el Compose aprobado para cada instalación. No cambiar el target a
otra revisión sin una activación expresamente autorizada. La idempotencia ARS
y el diseñador de documentos se describen en sus módulos y pruebas; los
informes históricos de activación se conservan fuera del repositorio.

## Validación integrada pre-piloto

La fase reproducible de staging para 6C3–6C7 usa un proyecto Docker y una base PostgreSQL desechable separados. El procedimiento, los datos sintéticos, la matriz PASS/FAIL y la recomendación de readiness están en [`docs/pre-pilot-validation.md`](docs/pre-pilot-validation.md). No ejecutar los scripts de pre-piloto contra una instalación real.

El frontend admite tanto `http://localhost:5173` desde la PC del servidor como
`http://IP_DE_LA_PC:5173` desde la red local. No es necesario sustituir localhost
en el código: las llamadas a la API usan `/api/v1` en la dirección con la que se
abre Atlas. Docker Compose reenvía esas llamadas al servicio backend mediante
la configuración del frontend; conserva la autenticación y los permisos existentes.
Cada dirección mantiene su propia sesión de navegador.

Después de aplicar esta configuración a una instalación existente, recrear solo
el frontend para cargar su variable de reenvío:

```sh
docker compose up -d --build --no-deps frontend
```

Si se ejecuta Vite fuera de Docker, el backend predeterminado del reenvío es
`http://localhost:8000`; `API_PROXY_TARGET` permite cambiarlo. Una configuración
explícita `VITE_API_URL` sigue disponible para una API separada. Para servir el
bundle con otro servidor web, configurar también el reenvío de `/api/v1`.
Para exponer Vite de desarrollo o staging detrás de un host HTTPS, configurar
`VITE_ALLOWED_HOSTS` en el entorno del proceso frontend con una lista de nombres
exactos separados por comas. No admite comodines; no aplica al build ni al preview.
Verificar el host autorizado antes de reiniciar el frontend de una instalación.

## Configuración y seguridad

`.env` es obligatorio para iniciar el stack porque contiene credenciales y secretos específicos de cada instalación. El archivo `.env.example` es únicamente una plantilla y deja vacíos los valores sensibles.

`docker-compose.yml` no contiene contraseñas predeterminadas para PostgreSQL, `DATABASE_URL`, `SECRET_KEY` ni la contraseña del administrador inicial. Docker Compose exige esos valores mediante interpolación de variables obligatorias antes de crear los servicios.

El archivo `.gitignore` excluye `.env`, mientras que `.env.example` sí permanece versionado como plantilla. Los datos de PostgreSQL se almacenan en un volumen Docker local y no forman parte del repositorio.

### Instalación en otra PC

Una instalación nueva necesita su propio `.env`. Por diseño, clonar el repositorio por sí solo no proporciona las credenciales privadas ni los datos de la instalación original.

Para migrar una instalación existente a otra PC se debe transferir de forma segura la configuración privada y, si corresponde, realizar una copia/restauración de la base de datos. No se deben copiar credenciales ni datos clínicos al repositorio Git.

## Reproducibilidad

El proyecto contiene en Git el código fuente, Dockerfiles, Compose, migraciones, pruebas y la plantilla `.env.example`. Los archivos y datos específicos de cada PC (`.env`, volúmenes de PostgreSQL, `node_modules`, cachés y otros artefactos locales) permanecen fuera del repositorio.

No se deben incorporar pacientes reales, datos clínicos, contraseñas ni archivos `.env` al repositorio.

Consulta [la arquitectura inicial](docs/architecture.md).

## Atlas Local Agent

La [impresión local controlada V1](docs/atlas-local-agent-local-printing-v1.md)
describe una prueba física sintética de una sola hoja. La siguiente fase de
[pairing y registro de estaciones](docs/atlas-local-agent-pairing-registry-v1.md)
incorpora registro, credenciales propias y catálogo de impresoras. Su migración
`0067_local_agent_registry` incorpora la persistencia del registro. El
[diseño de comunicación segura](docs/atlas-local-agent-secure-communication-v1.md)
explica pairing, heartbeat, catálogo y reconexión con HTTPS; ninguna identidad
de estación debe versionarse en Git.
La [foundation de comunicación segura V1](docs/atlas-local-agent-secure-communication-v1.md)
agrega aislamiento de la excepción, backoff, rutas y orígenes móvil/tablet.
No certifica TLS productivo sin una URL HTTPS real ni ejecuta trabajos remotos.
La [foundation HTTPS con Tailscale Serve](docs/atlas-https-tailscale-serve-v1.md)
y la [frontera explícita del proxy](docs/atlas-trusted-proxy-v1.md) validan el
endpoint tailnet HTTPS. Serve usa la entrada privada loopback 8002 (perfil
Compose `tailscale`), mientras el backend directo 8001 ignora proxy headers.
El agente ya conserva el endpoint HTTPS en DPAPI; su ejecución QA manual es
temporal y no equivale a instalación productiva permanente ni routing remoto.

La [persistencia de trabajos de impresión](docs/atlas-print-job-persistence-v1.md)
se valida primero en PostgreSQL temporal. La revisión
`0068_print_job_persistence` define el esquema correspondiente.
Incluye inbox SQLite durable del agente; no habilita polling, routing ni impresión.
No usar `upgrade head` para activar revisiones futuras no autorizadas.

La [extensión del contrato PrintJob V1](docs/print-job-contract-extension-v1.md)
preparó `0069_print_job_contract` en PostgreSQL temporal: estados
Received/Ready/Printing, intención inmutable v2 y compatibilidad SQLite.
Su activación requiere alinear current/head/target. No habilita routing ni impresión; el inbox
SQLite sigue pendiente de integración con el runtime real.

La fundación visual, componentes y contratos del shell están documentados en
[Atlas UI V2 — Fase 0](docs/ui-v2/FOUNDATION.md), incluyendo el catálogo exclusivo de desarrollo.

La política implementada para autorización clínica, contexto inmutable, finalización y auditoría está documentada en [Seguridad clínica y ciclo de vida de consulta](docs/clinical-security-lifecycle.md).

El flujo de solicitudes estructuradas, sus reglas de contexto, seguridad e impresión está documentado en [Órdenes clínicas estructuradas](docs/clinical-orders.md).

Las garantías de una consulta por cita, revisión optimista y serialización de escrituras clínicas están documentadas en [Integridad y concurrencia de consultas](docs/clinical/CONSULTATION_CONCURRENCY.md).

El [workspace cardiológico V1 (6C2B / 0061)](docs/cardiology-workspace-v1.md) amplía
la consulta existente con captura estructurada y seguimiento operativo para
secretaría. Su implementación se validó en PostgreSQL temporal y su activación
local controlada dejó la base oficial en `0061_cardiology_workspace`.

La [visibilidad contextual de capacidades V1](docs/contextual-feature-visibility-v1.md)
separa presentación, permisos y contratación futura. Implementación 0062 con
switches independientes de panel Safety y alerta crítica, organización/centro y
audiencias médico/secretaría. Los defaults son restrictivos y la activación
de cada revisión debe verificarse por separado.

## Seguridad administrativa pre-piloto (6C3)

[6C3 — Seguridad y Administración](docs/6c3-security-administration.md) estableció la matriz de roles, transferencia protegida, reautenticación, restricciones individuales, revocación de sesiones y procedimiento de actualización. En esa fase el administrador cubría toda la instalación; 6C4 añade el aislamiento entre organizaciones. 6C2B/Cardiología queda pausada.

## Organizaciones (6C4)

Los [horarios laborales y políticas de acceso (6C4C)](docs/6c4c-access-schedules.md) permiten restricciones opcionales por membresía, zona horaria por organización, horas extra y días sin acceso. Se configuran en Seguridad y conservan el acceso actual del piloto hasta activarse expresamente.

La [fase 6C4](docs/6c4-organizations.md) introduce organizaciones, membresías con roles y estado propios, y aislamiento por host en el backend. El piloto se migra a la organización inicial `pilot` conservando centros e historiales. Configure `TENANT_HOSTS_JSON` y, si se prepara un host de plataforma, `PLATFORM_HOSTS_JSON` según la documentación antes de publicar nuevos hosts. Se requiere un nuevo inicio de sesión tras la migración. Este cambio depende de 6C3/PR #48 y se integra hacia `feat/complete-care-context`; Cardiología permanece pausada.

## Seguros / ARS (6C5)

La [fase 6C5](docs/6c5-insurance-authorizations.md) incorpora planes, afiliaciones históricas y cobertura/autorización por cita, aisladas por organización. Prepara los importes para fases posteriores de Caja y Reclamaciones sin implementarlas.

## Caja / Facturación (6C6)

[6C6](docs/6c6-cash-billing.md) añade Finanzas: cajas por usuario/centro, cobros mixtos y parciales, documentos internos, saldos de pacientes y cierres auditables. El importe ARS permanece esperado, separado de lo recaudado. No incluye fiscalización ni reclamaciones ARS. Migración aditiva `0038_cash_billing`, sin cobros sembrados para el piloto.

## Reclamaciones y cuentas por cobrar ARS (6C7)

[6C7](docs/6c7-ars-receivables.md) convierte el importe esperado de ARS en reclamaciones con fotografía histórica, glosas, correcciones, remesas, aplicaciones, reversos, aging y conciliación. Estos cobros permanecen separados de Caja y del saldo del paciente. Migración aditiva `0039_ars_receivables`, sin reclamaciones sembradas.

## Validación aislada de impresión post-0069

Las pruebas de routing con fakes integran navegador, HTTPS, PostgreSQL y SQLite del Agent usando exclusivamente documentos sintéticos y un ejecutor simulado. No habilitan impresión física.

La integración post-0069 añade API autenticada y consumidor HTTPS del Agent con SQLite real. La acción de validación segura es **sin papel** y no usa documentos reales.

La [compatibilidad de cuenta de servicio y DPAPI](docs/service-account-dpapi-compatibility-v1.md)
documenta la conservación de identidad, el traspaso protegido de credenciales
y el almacenamiento SQLite durable. La instalación del servicio y la activación
física requieren validaciones y autorizaciones independientes por estación.
