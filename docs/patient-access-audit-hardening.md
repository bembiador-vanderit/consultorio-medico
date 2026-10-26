# Patient Access & Audit Hardening

## Permisos explícitos

- `patients:view`: listado, conteo, búsqueda de identidad y ficha individual.
- `patients:edit`: crear/actualizar ficha, **requiere también view efectivo**.
- Edit sin view no concede ninguna operación de ficha; negar view elimina edit
  del conjunto efectivo. No se infiere view desde edit.
- La única ruta de actualización existente es PUT. No se agrega PATCH; un método
  PATCH sigue devolviendo 405, nunca efectúa una modificación.
- Los filtros de organización, relaciones médico/paciente y scope de secretaría
  se conservan tanto para lectura como escritura. Platform no adquiere acceso.
- Seguro mantiene `insurance:manage`: pacientes edit no evita esa comprobación.
  Seguro usa view para lectura, y view + insurance:manage para sus escrituras.

El frontend consume permisos efectivos de `/auth/me`; no interpreta el rol ni
`patients:access` como autorización de edición. La ficha conserva Ver/Editar,
confirmación de descarte y guardado sin cambios local. Se oculta la creación a
usuarios view-only. La navegación Pacientes y su contador consumen view.
Tras actualizar código/catálogo, una pestaña que conserve el perfil anterior
debe recargarse para obtener los permisos nuevos desde `/auth/me`.

## Compatibilidad y bootstrap

Antes de esta fase `patients:access` significaba tanto leer como crear/editar.
Admin, médico y secretaría ya podían editar datos demográficos autorizados.
Por ello los tres roles iniciales conservan **view + edit**, no reciben una
capacidad nueva. Para secretaría de solo lectura se retira/deniega edit mediante
la administración existente. No se modifica ninguna denegación individual.

El catálogo de permisos es dinámico: no hay migración Alembic. En la primera
inicialización que incorpora `patients:edit`, los roles heredados (incluidos los
personalizados) con access y sin ningún permiso explícito nuevo reciben view y
edit. Un rol que ya tiene una definición explícita de pacientes se respeta.
Creación del catálogo y mapping se confirman en una sola transacción.

Después, la presencia del permiso de catálogo evita repetir el mapping. El
bootstrap conserva permisos de pacientes existentes y personalizados: no
restablece edit retirado, ni ambos permisos retirados, aunque siga existiendo
access. Los roles creados inicialmente usan los defaults de compatibilidad.

Negar `patients:access` conserva la restricción heredada: bloquea también view y
edit. Esta regla es solo una denegación; access por sí solo **no** otorga view ni
edit en los endpoints nuevos. Negar edit permite view. Negar view bloquea ambos.

## Mapa de dependencias

Se separa la autorización en `/patients` y en las lecturas territoriales y de
seguro necesarias para abrir la ficha completa. Regional conserva su permiso
administrativo para modificar catálogo. El panel de seguro conserva su permiso
especializado, no deriva autorización de patients:edit.

Access se mantiene sin cambios para Agenda/appointments, contactos previos,
disponibilidad, turnos, pausas, waiting rooms, cobertura clínica, comunicaciones,
reportes y notificaciones vinculadas. También permanece el contrato existente
de preparación de documentos clínicos. No se migran sus reglas ni se concede
acceso a esos módulos al otorgar únicamente view/edit de pacientes.

Administración permite denegar view/edit por separado; access se etiqueta como
operación heredada para evitar confundirlo con el nuevo permiso de ficha.

## Auditoría y privacidad

Se reutiliza `clinical_audit_logs`, que ya contiene actor, organización, centro
opcional, recurso, acción, timestamp y contexto JSON. Cada PUT con diferencias
agrega una fila `patient.update`, recurso patient e ID del paciente. La misma
transacción guarda datos y auditoría. No se duplican los eventos nuevos en
SecurityAudit; los históricos de ese registro permanecen sin reinterpretarse.

`context.changes` contiene exclusivamente campos realmente modificados con
`before`/`after`. Fechas se serializan ISO. Hay una lista explícita de campos
demográficos admitidos; claves arbitrarias, credenciales, tokens y seguros no
se copian. Seguro continúa con su auditoría especializada existente.

**Política específica de esta fase:** los valores demográficos anteriores/nuevos
son datos personales confidenciales y se almacenan solo en la tabla de auditoría
protegida en PostgreSQL, nunca en mensajes, acciones de texto o logs de aplicación.
No es una tabla pública. Lectura: endpoint existente
`GET /clinical-history/audit-logs`, restringido a `users:manage` y tenant activo.
Para eventos de paciente exige además view efectivo y filtra el recurso por el
mismo scope de identidades; una denegación de view no puede sortearse leyendo
el before/after desde este visor. Otros tipos de auditoría conservan su contrato.
No existe ruta normal para editar/borrar una fila. No se añade UI de auditoría.
El paciente no pertenece a un único centro, por lo que no se inventa center_id
para una actualización sin contexto de centro fiable.

`registered_sex` y `blood_type` registran el nombre del campo y before/after
`[REDACTED]`, no su contenido clínico, respetando la política clínica existente.
No se auditan notas, diagnósticos, tratamientos ni documentos clínicos aquí.

GET, abrir/cerrar, cancelar, PUT sin diferencias y escrituras rechazadas no crean
evento de modificación exitosa. El frontend evita PUT al guardar sin cambios;
el backend también compara valores normalizados antes de auditar.

## Límites y deuda

- No hay cifrado por campo ni nueva política de retención de auditoría. Backups,
  credenciales de PostgreSQL y exportaciones deben tratarse como datos sensibles.
- Administradores con users:manage pueden consultar la auditoría; las cuentas
  con acceso SQL privilegiado no quedan protegidas por la inmutabilidad de UI.
- No se modifica ni reconstruye before/after de eventos históricos antiguos.
- No se separan más permisos clínicos/demográficos que los ya existentes.
- Base oficial permanece en `0057_clinical_draft_identity`; no hay nueva revisión.
