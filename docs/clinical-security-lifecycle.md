# Seguridad clínica y ciclo de vida de consulta

## Alcance de autorización

La autorización clínica se resuelve en `app/services/clinical_access.py` y se aplica antes de leer o modificar una historia o cualquiera de sus recursos hijos.

- Administrador: puede consultar las historias de la instalación.
- Médico: solo puede acceder a historias cuyo `doctor_id` sea el suyo y cuyo centro permanezca entre sus centros asignados.
- Cuando existe `appointment_id`, paciente, médico y centro de la cita deben coincidir con el contexto inmutable almacenado en la historia.
- Otros roles no tienen alcance clínico. Las secretarias conservan su alcance de Agenda y Reportes, pero no reciben acceso al expediente clínico.

Conocer o cambiar un ID no otorga acceso. Signos vitales, diagnósticos, recetas, estudios y documentos PDF autorizan siempre a través de la historia padre. Los registros clínicos nuevos solo pueden crearse desde una cita autorizada.

Las historias antiguas sin cita se conservan para lectura. La interfaz de Historial ya no ofrece crear nuevas consultas huérfanas; un flujo futuro de consulta sin cita necesitará definir explícitamente médico, centro, motivo operativo y auditoría.

## Contexto de origen

Después de crear la historia, `appointment_id`, `patient_id`, `doctor_id` y `center_id` no forman parte del esquema de actualización. La API rechaza esos campos adicionales. Además, una cita que ya tiene historia no puede cambiar paciente, médico o centro ni puede eliminarse.

## Ciclo de vida

Los estados admitidos son:

- `in_progress`: permite edición clínica ordinaria.
- `completed`: conserva lectura y documentos, pero rechaza toda edición clínica ordinaria.

`POST /clinical-history/{history_id}/complete` finaliza la consulta y la cita asociada dentro de la misma transacción. Si el commit falla, ambos estados se revierten. Una cita no puede marcarse manualmente como completada mediante el editor general.

Solo citas `scheduled` o `confirmed` pueden iniciar o continuar una atención. Citas `cancelled`, `no_show` o `completed` son rechazadas en backend y no muestran la acción **Atender** en la Agenda. Si ya existe una consulta, la cita tampoco puede pasar a cancelada o ausente.

Por ahora se permite atender una cita futura. Esto es intencional para no imponer sin definición de producto una regla dependiente de zona horaria o tolerancias horarias. Antes del piloto debe decidirse si se permite pre-documentación y, si no, cuál es la ventana temporal válida.

No existe reapertura ni modificación ordinaria de una consulta finalizada. Una futura función de enmienda deberá conservar el contenido original y registrar motivo, autor, fecha y cambios, conforme a la política clínica y legal que se defina.

Al aplicar la migración, las historias vinculadas a citas ya completadas se marcan como completadas usando su `updated_at`; `completed_by_id` queda vacío porque el autor histórico no puede deducirse con seguridad.

## Auditoría mínima

`clinical_audit_logs` registra usuario, acción, tipo e ID de recurso, historia asociada, resultado, fecha y un contexto técnico mínimo. No copia notas, diagnósticos, medicamentos ni otro contenido clínico sensible.

Se registran lecturas relevantes, modificaciones, creación, finalización y denegaciones de alcance. La consulta de auditoría está limitada a usuarios con permiso administrativo `users:manage` mediante `GET /clinical-history/audit-logs`.
