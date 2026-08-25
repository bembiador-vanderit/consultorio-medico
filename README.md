# Consultorio Médico

Sistema de gestión profesional para consultorios médicos, inicialmente orientado a cardiología.

## Estado

La **Fase 0** establece infraestructura local con React/Vite, FastAPI y PostgreSQL.

## Requisitos

- Docker Desktop con Docker Compose

## Inicio rápido

Después de clonar el repositorio, todo lo necesario para construir la aplicación está versionado en Git. Los datos de PostgreSQL y los secretos se mantienen fuera del repositorio mediante volúmenes y `.env`.

### Windows PowerShell

1. Crear la configuración local:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Editar `.env` y cambiar los valores de ejemplo, especialmente `POSTGRES_PASSWORD`, `SECRET_KEY` e `INITIAL_ADMIN_PASSWORD`.
3. Construir e iniciar:

   ```powershell
   docker compose up -d --build
   ```
4. Comprobar migraciones:

   ```powershell
   docker compose exec backend alembic current
   ```
5. Ejecutar pruebas:

   ```powershell
   docker compose exec backend python -m pytest -q
   ```

### Linux / macOS

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend alembic current
docker compose exec backend python -m pytest -q
```

## Servicios disponibles

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000>
- Health check: <http://localhost:8000/api/v1/health>
- Documentación OpenAPI: <http://localhost:8000/docs>

## Reproducibilidad

El proyecto no debe depender de archivos existentes únicamente en la PC del desarrollador. El código fuente, Dockerfiles, Compose, migraciones y `.env.example` están en Git. `.env`, datos de PostgreSQL, `node_modules`, cachés y demás artefactos locales están excluidos mediante `.gitignore`.

No se deben incorporar pacientes reales, datos clínicos, contraseñas ni archivos `.env` al repositorio.

Consulta [la arquitectura inicial](docs/architecture.md).
