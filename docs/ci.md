# Validación CI

GitHub Actions valida el proyecto mediante Docker Compose antes de integrar cambios.

La validación crea un `.env` temporal dentro del runner con credenciales de prueba que no pertenecen a ninguna instalación real. Después:

1. construye y levanta PostgreSQL, backend y frontend;
2. comprueba el endpoint `/api/v1/health`;
3. comprueba el estado de las migraciones de Alembic;
4. ejecuta las pruebas del backend;
5. valida que el frontend pueda compilar;
6. elimina los contenedores y volúmenes temporales al finalizar.

El `.env` de CI nunca se guarda en el repositorio ni sustituye el `.env` privado de una instalación local.
