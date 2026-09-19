# Arquitectura inicial

La Fase 0 separa el sistema en tres servicios:

- **frontend**: React, Vite y Tailwind CSS. Consume únicamente la API HTTP.
- **backend**: FastAPI. Expone la API versionada bajo `/api/v1`.
- **postgres**: almacén de datos persistente para el entorno local.

No se incluyen datos médicos ni migraciones iniciales en esta fase. Las entidades clínicas, autenticación y permisos se incorporarán por fases, con validaciones y auditoría desde el backend.

## Asignación y autoría de citas

`appointments.doctor_id` identifica al médico responsable de la cita, incluso cuando otro médico la crea como cobertura o sustitución. La visibilidad y las operaciones del rol médico continúan limitadas a las citas donde figura como responsable.

El modelo todavía no conserva un campo `created_by` independiente. Por tanto, el médico que crea una cita para un sustituto no queda registrado como autor ni conserva acceso a ella por ese motivo. Incorporar esa trazabilidad requiere una fase posterior de auditoría y no debe resolverse sobrecargando `doctor_id`.

## Autoedición administrativa

Un administrador puede modificar su propio nombre, contraseña, roles adicionales y centros. Para evitar invalidar silenciosamente la sesión actual o perder acceso administrativo, no puede cambiar su propio correo, desactivar su propia cuenta ni retirarse el rol `admin`; esas operaciones deben ser realizadas por otro administrador. Independientemente del usuario que ejecute el cambio, el backend impide desactivar o retirar el rol al último administrador activo.
