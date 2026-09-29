# 6C4C — Horarios laborales y políticas de acceso

Base: `a115df502c37734e83787d678ad80d4d93f2ccfd`, rama `feat/complete-care-context` con 6C3 y 6C4 integrados. Esta fase se revisa en una rama propia, sin cambiar `main` ni desplegar el piloto. Cardiología sigue pausada.

## Configuración y precedencia

En **Seguridad → Horarios laborales y acceso**, un administrador selecciona a un miembro de su organización. La política pertenece a esa membresía, no a la identidad global. No se activa automáticamente por rol: médicos, secretarias y administradores existentes conservan acceso sin restricción de horario hasta una decisión expresa.

- Semana local: lunes=0 a domingo=6, de cero a varias ventanas por día, hasta 28 por semana. Inicio incluido, fin excluido. `24:00` representa el final del día. Los turnos nocturnos se dividen entre dos días. Se rechazan intervalos invertidos y superpuestos; ventanas contiguas forman una jornada continua.
- Con `restrict_outside_schedule=false`, horarios, horas extra y bloqueos quedan configurados pero no limitan el acceso. Con la política activa, un día sin ventanas no permite acceso habitual; una semana vacía permite exclusivamente excepciones autorizadas.
- Las horas extra añaden un período absoluto, sin editar la semana. Requieren motivo, inicio, fin, actor autorizante y organización, asignados/verificados por el servidor. Duración máxima: 31 días; inicio dentro del próximo año. No amplían permisos, centros ni alcance clínico.
- Una fecha bloqueada (feriado, vacaciones, licencia u otro motivo) **prevalece sobre la semana y sobre cualquier excepción**, durante todo ese día local. El administrador puede retirar el bloqueo si corresponde.
- Esta fase aplica una política a toda la organización y todos sus centros. No añade excepciones por centro: los centros no son contextos de autenticación y permitir una sesión por un centro podría habilitar operaciones en otros. Se conservan las asignaciones existentes.
- La pantalla presenta las excepciones y fechas bloqueadas vigentes/futuras, quién autorizó, estado efectivo, zona horaria, fin de la ventana actual o próxima ventana calculable. Cada edición exige la reautenticación 6C3 de un solo uso, ligada a método/ruta. Los cambios se serializan con el bloqueo administrativo existente.

## Zona horaria

`Organization.timezone` contiene una zona IANA configurable. La migración `0036_access_schedules` asigna `America/Santo_Domingo` exclusivamente al tenant con slug `pilot`; otras organizaciones existentes y nuevas usan `UTC` hasta configurarse. El arranque inicial del piloto también asigna Santo Domingo. No hay una zona RD global.

La semana y las fechas bloqueadas se interpretan en la zona de la organización. Las excepciones se almacenan en UTC: la UI envía fechas/horas locales sin zona y el servidor las convierte utilizando la zona del tenant. La API también admite timestamps con desplazamiento explícito. Cambiar la zona reinterpreta semanas y días bloqueados; las excepciones conservan sus instantes absolutos. Se invalidan las sesiones de todas las membresías de esa organización.

Para zonas con horario de verano, una ventana semanal con un límite local inexistente se omite ese día; si un límite se repite, se elige el inicio más tardío y el fin más temprano. Es una interpretación conservadora que evita ampliar acceso. Una excepción con hora local inexistente o ambigua se rechaza; para una hora repetida, la API admite un desplazamiento explícito. La UI no ofrece todavía un selector de la primera/segunda repetición.

El cálculo busca hasta 370 días. Si no encuentra acceso, informa ese límite y remite al administrador. Las ventanas se unen solo cuando se tocan o superponen, después de aplicar bloqueos. El calendario usa la hora UTC del servidor; sincronizar su reloj forma parte del despliegue.

## Sesiones y control backend

`enforce_schedule` se ejecuta después de validar credenciales en login, después de validar el refresh y desde `current_user` en cada petición protegida. Un token existente no permite operaciones fuera del horario. El fallo devuelve HTTP 403, cabecera `X-Access-Schedule: denied` y un mensaje humano con la próxima ventana cuando es calculable. Solo se revela tras verificar credenciales/contexto: contraseñas incorrectas conservan la respuesta genérica.

La infraestructura usa JWT sin un registro individual por dispositivo. Se reutiliza ese modelo con dos atributos firmados:

- `schedule_version`: versión propia de la membresía, incrementada al cambiar la semana, restricción, excepciones, bloqueos o zona. Invalida tanto access como refresh anteriores solo en ese tenant, sin revocar a la identidad en otras organizaciones.
- `schedule_until`: final absoluto de la jornada continua, incluido en access y refresh de usuarios restringidos. El refresh no puede alargarlo. Aunque no se haga ninguna petición durante el cierre, un token anterior sigue inválido al abrir la siguiente ventana: hace falta autenticar de nuevo. No se necesita un proceso de revocación por minuto ni escribir una revocación global al terminar cada jornada.

La caducidad JWT ordinaria continúa aplicándose. El navegador borra su bearer y vuelve al login al alcanzar el límite de jornada, y también ante una denegación del backend. Un navegador suspendido puede retrasar su temporizador hasta reanudarse; la autorización del servidor nunca depende de ese temporizador. No existe borrado remoto de información ya mostrada o copiada. Las peticiones que ya pasaron autenticación pueden terminar; no se cancelan transacciones en curso ni se garantiza guardar formularios incompletos al cierre.

Los tokens anteriores a la migración siguen funcionando para membresías no restringidas con versión cero. Activar la restricción o modificar la política exige un nuevo inicio de sesión. Cambiar la política propia puede cerrar el acceso del administrador; conviene mantener otro administrador autorizado. No se añade un bypass ni recuperación de cuenta nueva en esta fase.

## Aislamiento y auditoría

Las rutas usan `users:manage` y el mecanismo 6C3 de reautenticación. El backend obtiene la organización del host, nunca del payload. Las tablas de excepciones/bloqueos implementan `TenantOwned`; la política semanal vive en `OrganizationMembership`. Un administrador de plataforma dentro de un tenant conserva solo su autoridad local y no puede descubrir membresías de otros tenants.

La única ampliación del límite de escritura de `Organization` admite cambiar su `timezone` en el contexto de su propia organización; nombre, slug, propietario, creación y borrado siguen protegidos. La validación IANA ocurre antes de persistir.

Se auditan cambios de semana y activación/desactivación, excepciones creadas/retiradas, fechas bloqueadas creadas/retiradas y zona horaria. Actor, organización y recurso se guardan atómicamente con cada escritura. Los motivos se guardan en los registros administrativos, no se copian al log. No se registran contraseñas, tokens ni payloads. Los bloqueos de acceso autenticado se registran como `schedule.denied`, como máximo una vez por membresía cada cinco minutos mediante actualización condicional atómica. El log no enumera cada request repetida.

Retirar una excepción/bloqueo elimina su registro operativo y conserva su evento de auditoría con ID y actor. Las filas vencidas no retiradas permanecen en la base. La auditoría existente no es un historial íntegro de valores previos ni un almacén inviolable frente a SQL directo; se conserva ese límite de 6C3. No se implementa RLS nueva.

## API administrativa

Prefijo `/api/v1/administration/access-schedules`:

| Método/ruta | Función |
| --- | --- |
| `GET /{user_id}` | Semana, restricción, estado calculado y excepciones/bloqueos actuales |
| `PUT /{user_id}` | Sustituir semana y política de restricción |
| `POST /{user_id}/exceptions` | Autorizar período con motivo |
| `DELETE /{user_id}/exceptions/{id}` | Retirar excepción |
| `POST /{user_id}/blocked-dates` | Bloquear fecha local con motivo |
| `DELETE /{user_id}/blocked-dates/{id}` | Retirar bloqueo |
| `PUT /timezone` | Configurar zona IANA del tenant actual |

## Migración y validación

Actualizar backend y frontend juntos y ejecutar `alembic upgrade head` conforme al procedimiento de la instalación, con respaldo previo. No se activa ninguna restricción, no se cambia la versión global de sesión y no se eliminan datos existentes. No se ejecutó una migración sobre la instalación real.

El workflow de seguridad ejecuta backend completo, pruebas frontend, build y migraciones PostgreSQL. `backend/scripts/check_access_schedule_migration.py` exige una base vacía y desechable: crea datos sintéticos en 0035, verifica backfill del piloto y otro tenant, sesiones sin cambios y restricciones inactivas; hace downgrade a 0035 y nuevo upgrade. El downgrade elimina la configuración de horarios y no es un procedimiento de recuperación de producción.

Pruebas específicas: login fuera de horario y contraseña errónea, sesión activa al cierre exacto, refresh sin ampliación, tokens que no reviven en la siguiente jornada, usuario sin restricción y token anterior, excepción y bloqueo prioritario, reautenticación y auditoría, políticas aisladas entre tenants, zona configurable, límites inválidos y horario de verano. La interfaz tiene pruebas de selección/configuración, horas extra, bloqueos, reautenticación y salida por fin de jornada. Los resultados ejecutados se documentan en el PR.

No incluye Seguros/ARS, Caja/Facturación, Reclamaciones ni Cardiología.
