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

`POST /clinical-history/{history_id}/complete` finaliza la consulta y la cita asociada dentro de la misma transacción. Si el commit falla, ambos estados se revierten. Una cita no puede marcarse manualmente como completada mediante el editor general ni reabrirse desde ese editor después de finalizar.

Solo citas `scheduled` o `confirmed` pueden iniciar o continuar una atención. Citas `cancelled`, `no_show` o `completed` son rechazadas en backend y no muestran la acción **Atender** en la Agenda. Si ya existe una consulta, la cita tampoco puede pasar a cancelada o ausente.

Por ahora se permite atender una cita futura. Esto es intencional para no imponer sin definición de producto una regla dependiente de zona horaria o tolerancias horarias. Antes del piloto debe decidirse si se permite pre-documentación y, si no, cuál es la ventana temporal válida.

No existe reapertura ni modificación ordinaria de una consulta finalizada. Una futura función de enmienda deberá conservar el contenido original y registrar motivo, autor, fecha y cambios, conforme a la política clínica y legal que se defina.

## Cobertura clínica

Una cobertura es concedida exclusivamente por el médico principal para sí mismo, a otro médico activo asignado al mismo centro y durante un intervalo con inicio y fin. Su estado (`future`, `active`, `expired` o `revoked`) se deriva de esas fechas y de `revoked_at`; la expiración no necesita un proceso en segundo plano.

Solo el médico principal crea, revoca y ejecuta la transferencia. El suplente no puede autoasignarse ni ampliar el período, y compartir centro no concede acceso. En el flujo ordinario un médico solo crea y gestiona citas asignadas a sí mismo; la antigua selección de otro médico del mismo centro queda reservada a los alcances administrativos de administrador y secretaria. La transferencia entre médicos pasa exclusivamente por una cobertura explícita. La transferencia solo acepta citas programadas o confirmadas, sin consulta iniciada, del principal y centro indicados, mientras la cobertura esté activa y cuando la fecha/hora de la cita caiga dentro del intervalo. Para el MVP se exige simultáneamente vigencia actual y vigencia de la cita.

Las fechas de cobertura se guardan como hora local sin desplazamiento, de acuerdo con el modelo actual. Backend, autorización y estado API usan una única hora de instalación definida por `APP_TIMEZONE` (por defecto `America/Santo_Domingo`). El estado es `future` antes del inicio, `active` desde el inicio inclusive hasta el fin exclusivo, `expired` desde el fin inclusive, y `revoked` siempre que exista `revoked_at`. La UI confía en ese estado API y compara horarios locales sin conversión implícita a UTC. Una política multi-zona queda pendiente.

La transferencia conserva una fila inmutable con cita, cobertura, médico originalmente programado, suplente, ejecutor y fecha. La cita pasa al suplente, por lo que cualquier nueva consulta queda atribuida al médico que efectivamente la realiza. Una cita finalizada o con consulta iniciada nunca se reasigna.

El acceso delegado es únicamente de lectura y requiere una cita concreta del mismo paciente transferida bajo esa cobertura. Solo abre historias previas del principal en el mismo centro; no abre todos sus pacientes. Al revocarse, expirar o antes de comenzar la cobertura, desaparece ese acceso delegado. Las consultas realizadas por el suplente permanecen bajo su acceso normal.

Al revocar una cobertura, todas sus citas transferidas que aún no iniciaron consulta regresan al médico principal, independientemente de si la transferencia la ejecutó el principal o una secretaria autorizada. Una cobertura expirada distinta no se cierra implícitamente: debe cerrarse desde su propia acción para restaurar sus citas pendientes. La transferencia y la restauración permanecen registradas en la auditoría, y la cita puede transferirse de nuevo mediante otra cobertura válida. Si el suplente ya inició la consulta, la revocación no interrumpe esa atención propia: conserva el contexto transferido y puede completarla, sin conservar acceso delegado a otras historias previas. Transferencia y revocación bloquean las filas afectadas durante la transacción para evitar una aplicación concurrente parcial.

Cada transferencia genera una notificación administrativa, vinculada a la cita y sin identidad ni información clínica del paciente, para el suplente y las secretarias activas cuyo alcance incluye al principal o al suplente en ese centro. La restauración genera un evento diferenciado para los mismos destinatarios. La clave única por usuario, cita y tipo evita duplicados; una nueva ocurrencia del mismo evento actualiza y vuelve a marcar como pendiente la notificación existente. Los recordatorios ordinarios de citas también filtran secretarias mediante el alcance real de médicos y centro.

Agenda y notificaciones son conceptos distintos. La Agenda expone todas las citas actualmente administrables; `appointment_due` es un recordatorio persistido que solo se presenta mientras la cita continúe programada o confirmada, permanezca dentro de las próximas 24 horas y siga perteneciendo al alcance actual del destinatario. Dashboard y campana muestran la misma colección de notificaciones pendientes (`unread_only=true`), de modo que contador y tarjetas coinciden; marcar una como leída la retira inmediatamente de ambas superficies. Los eventos de transferencia y restauración son tipos explícitos distintos del recordatorio de proximidad.

Las coberturas no se editan en este MVP. Para corregir suplente, centro o período se revoca la cobertura y se crea otra; esto evita reescribir condiciones que pudieron haber autorizado transferencias o lecturas clínicas. La expiración corta autorización automáticamente, pero la restauración de citas pendientes es una acción explícita e idempotente desde la pantalla (`Cerrar y restaurar citas pendientes`); no se incorpora un proceso programado en esta fase.

Al aplicar la migración, las historias vinculadas a citas ya completadas se marcan como completadas usando su `updated_at`; `completed_by_id` queda vacío porque el autor histórico no puede deducirse con seguridad.

## Auditoría mínima

`clinical_audit_logs` registra usuario, acción, tipo e ID de recurso, historia asociada, resultado, fecha y un contexto técnico mínimo. No copia notas, diagnósticos, medicamentos ni otro contenido clínico sensible.

Se registran lecturas relevantes, modificaciones, creación, finalización y denegaciones de alcance. La consulta de auditoría está limitada a usuarios con permiso administrativo `users:manage` mediante `GET /clinical-history/audit-logs`.
