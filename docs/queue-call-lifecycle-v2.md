# Turnos V2: llamada e inicio de atención

La revisión 0043 agrega el ciclo operativo de un turno sin alterar la cita,
la historia clínica ni el orden de llegada:

`waiting -> called -> in_service`

También permite volver a llamar un turno (`called -> called`), marcarlo sin
respuesta (`called -> no_response`) o registrar que se retiró (`waiting` o
`called` -> `left`). Los estados terminales no se reingresan a la cola.

Cada llamada conserva su actor y hora en `queue_ticket_events`. El turno
mantiene `first_called_at`, `last_called_at`, `called_by_user_id` (el último
actor) y `call_count`. El inicio de atención conserva
`consultation_started_at` y su actor. La historia de eventos no se reemplaza.

## Inicio de consulta

La acción explícita **Iniciar consulta** es la fuente operativa para el inicio
de atención. No crea una `ClinicalHistory`, no guarda contenido clínico y no
modifica `Appointment.status`. La historia clínica continúa siendo creada por
el flujo clínico existente cuando el médico abre el espacio clínico autorizado.

Por defecto, un turno `waiting` debe ser llamado antes de iniciar consulta.
Una línea puede habilitar `call_on_consultation_start`; en ese caso el inicio
desde `waiting` registra, en una sola transacción, la llamada y el inicio.

## Permisos y aislamiento

Secretaría autorizada y el médico asociado pueden consultar y operar sus líneas
según el alcance existente. Secretaría puede llamar, volver a llamar, marcar
sin respuesta o registrar retiro; el médico asociado puede además iniciar la
consulta. Administración conserva las capacidades existentes. Todas las
operaciones se validan contra la cita, línea y organización activas; no se
permite cruzar tenants.

Las acciones exitosas devuelven `200`. Un turno inexistente o no visible se
responde con `404`; una identidad autenticada sin alcance operativo recibe
`403`; una transición incompatible o una contienda concurrente recibe `409`.
Los parámetros semánticamente inválidos conservan el contrato `422` de Atlas.

`POST /queue-tickets/{id}/call` acepta únicamente `waiting` y registra un
`CALLED`. `POST /queue-tickets/{id}/recall` acepta únicamente `called` y agrega
un `RECALLED`. Dos peticiones concurrentes de primer llamado al mismo turno se
serializan: una obtiene `200` y la otra `409`, sin convertir la segunda en
rellamada. Dos rellamadas explícitas concurrentes se serializan y ambas pueden
registrarse; cada acción conserva su evento, actor y hora.

## Migración

`0043_queue_call_lifecycle` debe aplicarse después de `0042_queue_arrivals` en
un entorno controlado. La migración agrega los campos de trazabilidad, la
configuración por línea y `queue_ticket_events`; no transforma tickets
existentes ni introduce turnos, audio, TV, WebSocket, facturación o cierre
clínico.

La base oficial local no se migra automáticamente desde esta microtarea.
