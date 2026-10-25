# Turnos V1: líneas, llegada y ticket

La migración `0042_queue_arrivals` sigue a `0041_appt_contact_attempts`. Es aditiva: crea `queue_lines`, `queue_sequences` y `queue_tickets`; no altera citas ni historias. **No se aplica automáticamente en la base oficial en esta microtarea.** Antes de usar la nueva API/UI allí, respaldar y aplicar 0042 en una tarea operativa separada.

## Configuración y operación

Administración configura una línea por médico y centro en «Localidades y centros» → «Configurar líneas de turnos». El prefijo (1–4 caracteres alfanuméricos) es único dentro del centro; la línea puede desactivarse. La creación/edición exige `centers:manage` y la reautenticación administrativa habitual. El prefijo no puede cambiarse después de emitir un ticket de esa línea, para preservar la identidad histórica.

Secretaría o administración abre «Agenda» → «Llegadas y turnos» y selecciona la fecha. Solo aparecen citas con snapshot `schedule_mode=queue`. Al pulsar «Registrar llegada» para una cita prevista **del día actual según la zona horaria de la organización**, la API verifica el alcance del usuario, cita, paciente implícito, médico, centro, línea activa y modalidad efectiva. No acepta una hora ni un número proporcionados por el cliente. Un segundo registro de la misma cita devuelve 409; no se borra ni renumera el ticket. Las citas `timed` y las jornadas que ya no resuelven a `queue` se rechazan.

El turno es una entidad distinta de `Appointment` y de los contactos previos. El ticket guarda paciente, médico, centro, especialidad y fecha como contexto del momento de emisión, `arrived_at`, `ticket_issued_at`, ambos actores y el código público (`C-001`, por ejemplo). No cambia `Appointment.status`, `appointment_time` ni `ClinicalHistory`. La cita con ticket ya no puede eliminarse, cambiar contexto/jornada o marcarse ausente/cancelada desde la edición ordinaria. El prefijo pertenece a la línea, no a la secretaria.

La numeración usa un `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` transaccional sobre el contador único por organización, centro, línea y fecha. PostgreSQL serializa los incrementos concurrentes de la misma fila; el ticket y contador se confirman juntos. Una restricción única de ticket por jornada/línea/número y otra por cita son defensas adicionales. `arrived_at` se toma del servidor inmediatamente después de obtener el número, de modo que el orden registrado sigue la emisión real, no la hora de agenda ni el contacto del día anterior. El código público se guarda como snapshot y no es clave primaria.

Las consultas ORM se limitan por organización y la autorización de citas conserva el alcance médico/centro de secretaría. Las escrituras verifican las referencias del mismo tenant y registran la acción en `security_audits`. No hay API para borrar tickets ni para reutilizar números.

## Límite de esta fase

`appointment_time` sigue obligatorio; no se inventa una hora para crear una cita `queue`. Esta fase trabaja con citas ya existentes/controladas o pruebas sintéticas. No incluye pacientes sin cita, llamada al siguiente, estados clínicos, turnero TV/audio, facturación, pausas ni reportes de espera. El backend oficial no debe reiniciarse con código 0042 antes de aplicar la migración de forma controlada.
