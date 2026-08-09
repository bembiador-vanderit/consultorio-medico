# Arquitectura inicial

La Fase 0 separa el sistema en tres servicios:

- **frontend**: React, Vite y Tailwind CSS. Consume únicamente la API HTTP.
- **backend**: FastAPI. Expone la API versionada bajo `/api/v1`.
- **postgres**: almacén de datos persistente para el entorno local.

No se incluyen datos médicos ni migraciones iniciales en esta fase. Las entidades clínicas, autenticación y permisos se incorporarán por fases, con validaciones y auditoría desde el backend.
