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

La política implementada para autorización clínica, contexto inmutable, finalización y auditoría está documentada en [Seguridad clínica y ciclo de vida de consulta](docs/clinical-security-lifecycle.md).
