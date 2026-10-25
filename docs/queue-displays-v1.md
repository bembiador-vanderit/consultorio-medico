# 0047 — Pantalla central de turnos

0047 está preparada para una pantalla por centro que agrega una o varias QueueLines. No modifica la emisión, numeración, llamada ni concurrencia de 0046. **No aplicar esta migración a la base oficial como parte de la implementación.** La UI queda detrás de `VITE_QUEUE_DISPLAYS_ENABLED=false` hasta la activación posterior.

## Datos y privacidad

- `queue_displays` guarda organización, centro, nombre, activación, opciones públicas, límite de recientes (3–10) y **solo el SHA-256 de un token aleatorio de 32 bytes**. El token en claro se entrega únicamente al crear o regenerar; no se puede recuperar desde la API administrativa. Regenerarlo invalida el enlace anterior inmediatamente.
- `queue_display_lines` relaciona la pantalla con varias líneas del mismo centro, con orden, activación y destino público configurable (por ejemplo, «Consultorio 3»). Una línea puede aparecer en varias pantallas. El prefijo y el código de turno existentes se reutilizan; no se crea otra identidad de ticket.
- El endpoint público `GET /api/v1/queue/displays/{token}/state` exige host de tenant válido, token válido y pantalla activa. No usa sesión clínica. Su respuesta tiene una lista explícita de campos: nombre de pantalla/centro; código, destino, hora de llamada y, solo si administración lo habilita, nombre de servicio/médico. Nunca incluye paciente, cita, teléfono, diagnóstico, historia, seguro ni finanzas. No se registran accesos de cada sondeo.
- El token de URL es una credencial de pantalla: compartirlo equivale a compartir acceso a ese estado público. Usar HTTPS, evitar capturas/enlaces ajenos y regenerarlo si se expone. La página solicita `no-referrer`; el endpoint indica `no-store`. Como otros tokens en URL, el del request puede figurar en logs de acceso del proxy/servidor: restringir acceso y retención de esos logs antes de publicar pantallas fuera del piloto.

## Estado visible

La fuente de verdad es PostgreSQL. Para la fecha local de la organización, `current_calls` contiene todos los tickets de líneas suscritas y activas cuyo estado es `called`, ordenados por `last_called_at` del servidor (más reciente primero). Salen de «Ahora» al pasar a `in_service`, `no_response`, `left` o `completed`. `recent_calls` muestra los últimos tickets ya no activos que fueron llamados, limitado a la configuración. Una llamada repetida actualiza `last_called_at` del mismo ticket, sin duplicar la tarjeta. No se crea una tabla de estado de TV.

La página `/queue-display/:token` no carga el shell clínico ni solicita login. Sondea el estado cada 3 segundos; el servidor decide el contenido, y el navegador solo lo muestra. Tres líneas activas del mismo centro pueden aparecer simultáneamente en una TV. No hay audio/TTS, notificaciones externas ni integración SmartTV.

## Administración y despliegue futuro

Solo administración del tenant con `centers:manage` puede crear, actualizar, activar/desactivar y regenerar claves. Las escrituras usan la reautenticación existente y generan `SecurityAudit`. Al asociar líneas se valida tenant y centro; no se admite una línea de otro centro. La configuración está en «Localidades y centros» cuando la flag está activa. El enlace se muestra una sola vez al crearlo/rotarlo.

La migración `0047_queue_displays` parte de `0046_queue_call_policy`, crea únicamente dos tablas e índices/restricciones y no crea pantallas ni modifica tickets históricos. Su downgrade se bloquea si existen pantallas configuradas. Con la base aún en 0046, las nuevas rutas responden 503 antes de consultar tablas ausentes; mantener la flag apagada hasta una activación oficial respaldada.
