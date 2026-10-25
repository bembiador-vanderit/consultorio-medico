# Turnos V3: finalización operativa explícita

`POST /api/v1/queue-tickets/{id}/complete` permite únicamente
`in_service -> completed`. Requiere `clinical:access` y que el usuario sea el
médico asignado al turno y a su línea. La operación bloquea el turno, comprueba
su estado y registra en una transacción el estado `completed`,
`consultation_finished_at`, `consultation_finished_by_user_id` y un nuevo evento
`SERVICE_COMPLETED`. Una segunda solicitud, incluso concurrente, recibe `409` y
no reescribe el primer cierre. Turnos no visibles devuelven `404`; un usuario sin
capacidad o sin asignación recibe `403`.

El botón **Finalizar consulta** solicita confirmación y es la única acción que
dispara ese endpoint. Guardar notas, signos vitales, diagnósticos, imprimir,
navegar o cerrar sesión no finaliza el turno. Secretaría ve el estado y las horas
de inicio y finalización, pero no dispone del botón.

`QueueTicket.completed` significa que la atención operativa terminó. No cambia
`Appointment` ni `ClinicalHistory`. Esta última conserva su ciclo clínico propio
y su endpoint de finalización separado; completar el turno no firma, bloquea ni
crea una historia clínica. Los eventos anteriores del turno permanecen intactos.

La duración se deriva de `consultation_finished_at - consultation_started_at`;
el tiempo total en el centro, de `consultation_finished_at - arrived_at`. No se
almacenan duraciones duplicadas. La base comprueba que la finalización no sea
anterior al inicio cuando se registra. En el futuro,
`consultation_finished_at + preparation_delay` podría definir cuándo llamar al
siguiente paciente, pero V3 no implementa espera, temporizador ni llamada
automática.

La migración `0044_queue_service_completion` sigue a `0043_queue_call_lifecycle`
y no aplica backfill. Debe validarse y aplicarse de forma controlada antes de
usar V3 en la base oficial; esta microtarea no migra esa base.
