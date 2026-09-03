# Alcance de agenda y reportes por rol

## Regla de autorización

El backend es la fuente de verdad para el alcance de citas y reportes:

- `admin`: puede consultar y gestionar todas las citas.
- `doctor`: puede consultar, editar y eliminar únicamente sus citas asignadas. Al crear o actualizar una cita puede seleccionar otro médico activo y disponible del mismo centro como sustituto.
- `secretary`: puede consultar y gestionar citas únicamente para los centros y médicos configurados por un administrador.

El alcance de una secretaria se define por centro con una de estas modalidades:

1. médicos específicos;
2. todos los médicos del centro.

La pertenencia al centro sigue siendo obligatoria. Una secretaria nunca obtiene acceso a un centro solamente por tener configurado un médico, y un médico debe estar activo, tener rol `doctor` y pertenecer al centro.

## Compatibilidad de datos existentes

Antes de esta funcionalidad, toda secretaria asignada a un centro podía trabajar con todos sus médicos. La migración `0020_secretary_doctor_scopes` conserva esa interpretación: crea para cada asignación existente un alcance con `manage_all_doctors = true`.

Las asignaciones nuevas no reciben alcance implícito. El administrador debe configurarlo expresamente en **Usuarios y roles → Editar → Alcance de agenda (secretaria)**.

## Aplicación uniforme

La misma función de alcance del backend se utiliza para:

- listado y filtros de Agenda;
- selección de médicos al crear citas;
- listado y filtros de Reportes;
- generación y descarga de PDF;
- envío del reporte por correo o WhatsApp.

La interfaz de Reportes consume `/appointments/scope-options`, que devuelve solamente centros y médicos visibles para la cuenta autenticada. Esto evita conceder a doctores o secretarias acceso administrativo a `/users` o `/centers`.
