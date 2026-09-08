# Scope y privacidad de pacientes

## Principio

Atlas conserva un único registro organizacional por paciente. La existencia de ese registro no concede acceso automático a su información clínica. La identidad administrativa y la historia clínica tienen reglas de autorización distintas.

## Administrador

El administrador puede listar, localizar y actualizar datos de identidad del paciente para tareas organizativas y prevención de duplicados. El rol `admin`, por sí solo, no permite abrir consultas, leer historias clínicas, descargar documentos clínicos ni administrar seguimientos clínicos.

Una cuenta que tenga simultáneamente los roles `admin` y `doctor` conserva únicamente el alcance clínico que le corresponde como médico responsable.

## Médico

El listado habitual muestra pacientes relacionados con el médico mediante una cita vigente/completada o una consulta histórica propia. El médico puede abrir la atención de una cita cuyo responsable actual sea él.

Una cita nueva permite atender esa cita, pero no revela automáticamente consultas realizadas por otros médicos. Los accesos directos mediante `patient_id`, `history_id` o `appointment_id` se validan nuevamente en backend.

## Secretaria

La secretaria visualiza identidades asociadas a citas incluidas en su alcance configurado de centro y médicos. Puede realizar una búsqueda mínima para preparar una cita únicamente indicando un centro y médico que tenga autorizado. No recibe acceso a historia clínica, diagnósticos, recetas, signos vitales, estudios ni seguimientos clínicos.

## Cobertura clínica

La cobertura continúa siendo una autorización explícita y concreta. Requiere principal, sustituto, centro, vigencia y una cita transferida. Solo la transferencia del paciente concreto permite consultar el historial previo autorizado; no abre los demás pacientes del médico principal. El acceso delegado previo es de solo lectura y conserva la auditoría existente.

## Búsqueda restringida y duplicados

`GET /api/v1/patients/identity-search` exige fecha de nacimiento y teléfono o correo exacto. No admite el nombre como único identificador. La respuesta contiene solamente identificador, nombre, fecha de nacimiento y contacto enmascarado; nunca incluye información clínica.

Antes de crear un paciente, el backend rechaza una coincidencia exacta de fecha de nacimiento más teléfono o correo. La pantalla de cita permite seleccionar esa identidad existente sin crear otro registro.

## No revelación

Los accesos a identidades fuera del scope responden como paciente no encontrado. Los accesos directos a una historia existente mantienen el rechazo auditado del servicio clínico. Esta combinación evita confirmar innecesariamente recursos ajenos y conserva la trazabilidad existente.

## Límites conocidos

- La prevención de duplicados es deliberadamente básica: fecha de nacimiento más teléfono o correo exacto.
- El modelo todavía no incluye documento/cédula normalizado.
- No existe acceso de emergencia (`break-glass`) ni consentimiento electrónico en esta fase.
- La política descrita es una decisión de seguridad y producto; no constituye una conclusión legal.
