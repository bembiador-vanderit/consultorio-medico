# 0045: pausas operativas del médico

Las pausas son registros operativos independientes de `QueueTicket`, `Appointment`
y `ClinicalHistory`. No cambian el estado ni los tiempos de espera de pacientes.

- `POST /api/v1/provider-pauses/start`: inicia ahora una pausa. El servidor fija
  `actual_started_at` y el actor. Médico: su propia identidad; administración:
  puede indicar `doctor_id` de un médico asignado al centro.
- `POST /api/v1/provider-pauses/{id}/finish`: finaliza ahora. El servidor fija
  `actual_finished_at` y el actor. Una segunda finalización responde **409**, igual
  que las transiciones repetidas de Queue V2/V3.
- `GET /api/v1/provider-pauses/current?center_id=...&doctor_id=...`: pausa abierta
  o `null`.
- `GET /api/v1/provider-pauses?center_id=...&doctor_id=...&day=YYYY-MM-DD`:
  historial, opcionalmente filtrado por solapamiento con el día local de la
  organización. `duration_seconds` se deriva solo para pausas cerradas.

La sesión de tenant determina `organization_id`; nunca se acepta del cliente.
El médico necesita estar asignado al centro y tener `clinical:access` efectivo
para iniciar/finalizar. Administración del tenant puede gestionar. Secretaría
con alcance sobre centro/médico puede consultar, pero no iniciar/finalizar.
Los permisos individuales denegados siguen aplicándose. El contexto de
plataforma no habilita estas operaciones.

La restricción PostgreSQL `uq_provider_pause_open` impide más de una pausa
abierta por organización, centro y médico incluso ante START concurrentes. El
segundo intento responde **409**. FINISH concurrente también produce un único
cierre efectivo y **409** para el perdedor.

`is_provider_paused(db, doctor_id, center_id)` queda disponible para el futuro
auto-call; 0045 no lo conecta aún al algoritmo de llamada. La migración 0045 no
crea pausas históricas y su downgrade se permite solo si la tabla está vacía.
La base oficial debe permanecer en 0044 hasta una aplicación operativa separada.
Mientras siga en 0044, la tarjeta de pausas de Agenda está desactivada por
defecto y no consulta la tabla nueva. Tras aplicar 0045 y validarla en la base
oficial, habilitarla explícitamente con `VITE_PROVIDER_PAUSES_ENABLED=true` en
el entorno del frontend y reiniciar ese servicio. No habilitar la bandera antes
de migrar.
