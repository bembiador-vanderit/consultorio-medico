# Contexto del proyecto para Codex

## Propósito

`consultorio-medico` es una aplicación web de gestión clínica, inicialmente orientada a cardiología. Maneja datos sensibles; la integridad clínica, la autorización en backend y la privacidad tienen prioridad sobre la velocidad de entrega.

## Arquitectura verificada

- Frontend: React, Vite, TypeScript, Tailwind CSS y Axios en `frontend/`.
- Backend: FastAPI, SQLAlchemy y Pydantic en `backend/app/`.
- Persistencia: PostgreSQL y migraciones Alembic en `backend/alembic/versions/`.
- Entorno: Docker Compose con servicios `frontend`, `backend` y `postgres`.
- API: rutas bajo `/api/v1`; el frontend consume la API HTTP y no accede directamente a la base de datos.
- CI: `.github/workflows/compose.yml` construye el stack, espera el health check, comprueba Alembic, ejecuta pytest y compila el frontend.

## Dominios presentes en el código auditado

Autenticación y usuarios; pacientes y seguros; centros, localidades y disponibilidad médica; citas; historia clínica y contexto de consulta; diagnósticos; recetas; estudios solicitados y catálogo clínico; seguimientos y notificaciones; comunicaciones por correo/WhatsApp; reportes y PDF.

## Convenciones obligatorias

1. Leer `AGENTS.md`, este archivo, `CURRENT_STATE.md` y `CODEX_TASK.md` antes de modificar código.
2. Trabajar desde la rama indicada en `CURRENT_STATE.md`; no asumir que `main` contiene las funciones del PR abierto.
3. Hacer cambios pequeños, relacionados y verificables. No mezclar refactorizaciones con cambios funcionales.
4. Mantener la autorización en el backend. Nunca confiar solo en controles de la interfaz.
5. No versionar secretos, archivos `.env`, datos clínicos reales ni archivos médicos.
6. No modificar ni eliminar migraciones ya publicadas sin analizar la cadena completa y el impacto sobre bases existentes.
7. Para cambios relevantes, verificar como mínimo pruebas backend, compilación frontend y validación Docker Compose cuando el entorno lo permita.
8. Registrar con exactitud qué se ejecutó. Un CI verde demuestra el flujo automatizado definido, no una aceptación funcional manual completa.
9. La interfaz y la documentación funcional permanecen en español.

## Comandos de referencia

Con un `.env` local seguro:

```text
docker compose config -q
docker compose up -d --build
docker compose exec -T backend alembic current
docker compose exec -T backend python -m pytest -q
docker compose exec -T frontend npm run build
docker compose down -v
```

## Límites clínicos

El sistema registra decisiones del profesional. No debe diagnosticar, recomendar tratamientos ni generar indicaciones farmacológicas de forma autónoma. Cualquier futura asistencia con IA requiere validación clínica, trazabilidad y confirmación explícita del profesional.
