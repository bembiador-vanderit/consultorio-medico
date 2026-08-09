# Consultorio Médico

Sistema de gestión profesional para consultorios médicos, inicialmente orientado a cardiología.

## Estado

La **Fase 0** establece infraestructura local con React/Vite, FastAPI y PostgreSQL.

## Requisitos

- Docker Desktop con Docker Compose

## Inicio rápido

1. Crear el archivo de configuración local:

   ```bash
   cp .env.example .env
   ```

2. Cambiar los valores de ejemplo, especialmente `POSTGRES_PASSWORD`.
3. Iniciar los servicios:

   ```bash
   docker compose up --build
   ```

Servicios disponibles:

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000>
- Health check: <http://localhost:8000/api/v1/health>
- Documentación OpenAPI: <http://localhost:8000/docs>

Consulta [la arquitectura inicial](docs/architecture.md) y las reglas de contribución en [AGENTS.md](AGENTS.md).

> No incorporar pacientes reales, datos clínicos, contraseñas ni archivos `.env` al repositorio.
