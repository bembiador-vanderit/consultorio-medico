# 0052 — Salas de espera configurables

La migración `0052_waiting_rooms` parte de `0051_card_batch_controls`. **No se aplica a la base oficial en esta microtarea.** La UI está detrás de `VITE_WAITING_ROOMS_ENABLED=false` y debe activarse solo después de una migración operativa respaldada. El backend devuelve 503 en las rutas nuevas mientras la base no tenga la tabla; las rutas 0051 de líneas y pantallas siguen funcionando sin la columna nueva.

## Propiedad y asignaciones

- `WaitingRoom` pertenece a organización y centro; el nombre es configurable y único por centro sin distinguir mayúsculas. No hay salas predefinidas ni semillas QA.
- `QueueLine.waiting_room_id` es opcional: una línea tiene a lo sumo una sala principal. Cambiarla no altera tickets, citas, historias, prefijos ni numeración. El ticket no guarda un snapshot de sala; por ahora, la sala se resuelve desde la configuración actual de la línea. Por ello, un traslado también cambia la agrupación visible de tickets aún activos.
- `WaitingRoomSecretary` permite muchas secretarias por sala y varias salas por secretaria. Su asignación exige membresía activa, asignación al centro y `SecretaryCenterScope`; **no concede permisos**. La lectura de líneas para secretaría es la intersección de líneas de la sala con su alcance médico/centro existente. La secretaria puede cambiar el filtro de sala en «Agenda → Llegadas y turnos», sin modificar autorizaciones del backend.
- `QueueDisplay.waiting_room_id` también es opcional. Una sala puede alimentar varias pantallas.

## Precedencia de pantallas

Una pantalla **sin sala** usa exclusivamente sus `QueueDisplayLine` actuales, sin cambio de comportamiento. Una pantalla **con sala** toma las líneas activas asignadas a esa sala en el mismo centro. Una asociación `QueueDisplayLine` explícita de una de esas líneas puede ajustar destino y visibilidad; una asociación de otra sala se conserva en la base, pero no se muestra mientras la pantalla esté ligada a la sala. Si no hay destino explícito, se usa el nombre de la línea como texto público. Para mostrar un consultorio concreto, configure el destino explícito de esa línea. El encabezado deriva el nombre de sala y, solo si están habilitadas las opciones existentes, los nombres de médicos/servicios; nunca incluye paciente ni datos clínicos.

## Administración y seguridad

«Administración → Localidades y centros → Salas de espera» permite crear, editar, desactivar y asignar líneas/secretarias. Las pantallas se vinculan desde «Pantallas de turnos». Crear o modificar exige administrador del tenant, `centers:manage` y la reautenticación administrativa existente. Las escrituras generan `SecurityAudit`. No hay eliminación física de salas. Una sala inactiva puede desasignarse, pero no acepta recursos nuevos. Los endpoints validan centro/tenant; la FK compuesta de PostgreSQL impide ligar líneas o pantallas de otro centro u organización incluso ante una carrera. Platform admin no recibe acceso de tenant por defecto.

Los datos sintéticos existentes de audio/turnos QA no se migran ni se borran. La migración crea salas y asignaciones vacías; no altera 0051, tickets, eventos, citas ni historias. El downgrade se bloquea si existen salas, para evitar pérdida accidental de configuraciones.
