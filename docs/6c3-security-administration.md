# 6C3 — Security & Administration Hardening

## Prioridad y base

Auditoría previa a implementación, 2026-09-22, sobre `4c669ba331b17e345c40990bbbe0b8e1a6ccdf47` de `feat/complete-care-context`. 6C2B queda pausada por decisión del responsable del producto. No modificar assessment, ECG, plantillas ni campos clínicos. Rama de trabajo: `feat/6c3-security-administration`; PR dirigido a `feat/complete-care-context`, nunca a main.

## Auditoría del estado inicial

- `models/identity.py`: usuarios, roles y permisos many-to-many. Sin capacidades individuales, versión de sesión, reautenticación, MFA ni recuperación.
- `services/bootstrap.py`: admin obtiene users:manage, patients:access, clinical:access, centers:access y centers:manage. Doctor: patients:access, clinical:access y centers:access. Secretary: patients:access y centers:access. El arranque restaura esta matriz. El usuario inicial nace del entorno y puede recrearse si se cambia su correo.
- `api/deps.py`: permisos comprobados en backend contra la base en cada petición. Autenticación por correo en JWT, sin comprobar tipo de token; un refresh firmado puede usarse como bearer. Bloqueo is_active efectivo inmediatamente, pero desbloquear revive tokens anteriores. Cambiar contraseña no revoca sesiones.
- `api/routes/users.py`: users:manage protege listado, creación, perfil, contraseña, roles, estado, centros, especialidades y alcance de secretaria. Admin se asigna como cualquier rol, incluso al crear usuario. Cuenta global de administradores activos evita quitar el último secuencialmente, pero no serializa operaciones concurrentes. Sin auditoría administrativa ni comprobación de contraseña del actor.
- `api/routes/centers.py`, `localities.py`: centers:manage protege cambios y asignaciones. Existe una segunda vía para alterar pertenencias por centers/{id}/users que también debe protegerse.
- `clinical_catalog.py`, `insurance.py`, `regional.py`: users:manage permite mantener catálogos y perfiles. `clinical_history.py`: users:manage permite leer auditoría clínica.
- `patients.py`, `appointments.py`, `doctor_availability.py`, `reports.py`, comunicaciones de reportes y seguros de pacientes: patients:access; autorización por recurso en servicios. Admin ve identidades y agenda de toda la instalación; doctor trabaja con su relación asistencial; secretary requiere centros y médicos asignados.
- Historias, órdenes, recetas, diagnósticos, signos y addenda: clinical:access más alcance del episodio. `services/clinical_access.py` exige doctor, autoría o cobertura concreta: admin solo no puede atender ni leer historias. La documentación antigua afirma lo contrario y está desactualizada.
- Endpoints de catálogos de lectura, auth/me, seguimientos/notificaciones y envío genérico de comunicaciones tienen current_user y verificaciones específicas; no representan gestión de usuarios. El envío genérico merece capacidad explícita.
- UI: Usuarios y roles y Localidades y centros visibles solo para admin. El formulario permite seleccionar admin como un rol corriente. `App.tsx` todavía acepta admin en attendAppointment, aunque canAccessClinical exige doctor. /auth/me no devuelve permisos efectivos. Esto explica la impresión de un admin sin función: tiene funciones reales de configuración, pero su permiso clínico es ineficaz y la presentación mezcla responsabilidades.

## Arquitectura mínima decidida antes de implementar

Una instalación representa una organización del piloto. Admin es administrador de esa instalación y todos sus centros; user_centers NO delimita su administración. No presentar esto como aislamiento multiempresa ni crear un superadministrador de plataforma. Un centro no queda sin administración mientras exista un admin activo de instalación. Multiempresa requiere tenant explícito en otra fase.

1. Mantener roles existentes y alcance clínico. Retirar clinical:access de admin; doctor+admin es una combinación explícita, sin ampliar el alcance clínico. Permitir restricciones individuales de capacidades operativas, nunca delegación individual de users:manage/centers:manage. La denegación prevalece. Mantener las capacidades existentes para evitar rehacer todos los módulos.
2. Incorporar versión de sesión para invalidar access y refresh tras bloqueo, contraseña, correo, roles o restricciones. Validar tipo de JWT. /auth/me expone permisos efectivos.
3. Reautenticación de contraseña con comprobante de corta duración, ligado al actor, versión de sesión, método y ruta, de un solo uso. Proteger todas las escrituras con users:manage/centers:manage, incluidas vías alternativas. Contraseña nunca en logs ni almacenamiento del navegador. Preparar el punto de verificación para un segundo factor futuro, sin simular MFA activo.
4. Administradores nuevos solo por flujo separado: solicitud, aceptación por destinatario activo con su propia reautenticación, vencimiento, cancelación y consumo único. Dos modos explícitos: nombramiento adicional o transferencia que retira admin al solicitante. Conservar roles operativos del solicitante; si no tiene ninguno queda sin capacidades hasta asignación. Revalidar ambos al aceptar.
5. Serializar mutaciones administrativas mediante bloqueo de la fila del rol admin en PostgreSQL, antes de leer estado objetivo. Garantizar último administrador y aceptación atómica, incluyendo cambios concurrentes. No sostener bloqueos durante interacción humana.
6. Auditoría administrativa separada, sin payloads, contraseñas, tokens ni contenido clínico. Actor, acción/ruta, recurso y momento, dentro de la misma transacción que el cambio. Consulta paginada solo admin; no API para modificar/borrar auditoría.
7. Bloqueo/desbloqueo conserva registros históricos. Sin eliminación de usuarios. Reautenticación con límite de intentos persistido y espera temporal; recuperación/MFA real quedan pendientes de configuración de canales y custodia de secretos.

## Incrementos y aceptación

A: identidad, sesiones, capacidades, migración. B: reautenticación/auditoría, último admin, nombramiento/transferencia. C: UI administrativa y pruebas HTTP de permisos, intentos fallidos, reutilización, revocación, transferencia y rutas alternativas; regresión backend/frontend y migraciones PostgreSQL. Registrar evidencia real y limitaciones al cerrar. No entregar el piloto hasta completar estos incrementos.

## Implementación del piloto

### Matriz efectiva

| Capacidad | admin | doctor | secretary |
| --- | --- | --- | --- |
| Usuarios, roles, bloqueo, restricciones y auditoría administrativa | Sí, instalación completa | No | No |
| Catálogos, localidades y centros | Sí | Lectura disponible según API | Lectura disponible según API |
| Identidad de pacientes, agenda y reportes | Toda la instalación | Relación asistencial y citas propias | Centros y médicos asignados |
| Historias, recetas, signos, diagnósticos, órdenes y seguimientos | No por ser admin | Autoría/cobertura y reglas clínicas existentes | No |
| Aceptar una solicitud administrativa propia | Sí, si corresponde | Sí | Sí |

Los roles se combinan expresamente. `doctor+admin` conserva el alcance clínico del doctor, sin convertir su administración global en acceso a expedientes ajenos. `patients:access` y `clinical:access` admiten denegación individual; no hay concesión arbitraria ni excepciones capaces de fabricar un administrador. Las restricciones son bloques completos: no existe aún edición fina de cada campo. El alcance de secretaria por centro/médico sigue siendo la herramienta de delegación operativa.

### Operaciones y contratos

- `GET /auth/me` y respuestas administrativas incluyen `permissions` y `denied_permissions`.
- `POST /administration/reauthenticate`: contraseña actual, método y ruta absoluta `/api/v1/...`; devuelve prueba opaca de 120 segundos. La base guarda solo su SHA-256. Una prueba nueva sustituye la anterior del usuario. Cinco fallos de contraseña bloquean esta verificación durante cinco minutos. Esto no implementa MFA.
- Las escrituras que dependen de `users:manage` o `centers:manage` exigen `X-Reauthentication`. La UI abre un diálogo accesible ante HTTP 428 y reenvía una sola vez la operación original. La contraseña y la prueba no se guardan en localStorage. Las lecturas no exigen contraseña adicional.
- `POST /administration/transfers`: destinatario activo y `replace_initiator`. La solicitud caduca en 24 horas, no concede permisos por sí sola y conserva las versiones de identidad de ambas partes.
- `GET /administration/transfers`: administradores ven pendientes de la instalación; otros usuarios solo las dirigidas a sí mismos. Se muestran nombres para que el destinatario pueda identificar al solicitante.
- `POST /administration/transfers/{id}/accept`: solo destinatario con reautenticación propia. Revalida estado, plazo, solicitante admin activo y versiones de ambos; aplica promoción y eventual retirada en una transacción. Las sesiones afectadas dejan de funcionar. La aceptación no modifica roles operativos ni centros.
- `POST /administration/transfers/{id}/cancel`: solicitante, destinatario o admin, con reautenticación. Crear usuarios o editar roles ya no permite agregar admin directamente; retirar a otro admin sigue sujeto al último administrador y reautenticación.
- `PUT /users/{id}/permissions`: lista cerrada de capacidades denegadas. No permite negar la administración al último administrador ni conceder permisos nuevos.
- `GET /administration/audit?offset=0&limit=50`: hasta 100 registros por página, solo permiso administrativo. Registra actor, operación y ruta/recurso, resultado y fecha UTC. Solicitudes de nombramiento y creación de usuarios agregan el ID resultante. No expone APIs de edición/eliminación. Los cambios exitosos y su auditoría comparten transacción; los fallos de reautenticación se registran aparte. No es un historial completo de valores anteriores y posteriores, ni almacenamiento inviolable frente al administrador de la base.

### Sesiones, concurrencia y arranque

Access y refresh verifican tipo, expiración, ID permanente del usuario, correo y versión de sesión. Un refresh no sirve como bearer; reutilizar un correo no reutiliza identidad. Cambiar contraseña, correo, bloqueo, roles o restricciones invalida las sesiones anteriores. Desbloquear no revive tokens antiguos. Pertenencias y alcance de secretaria también invalidan sesiones cuando se administran desde usuarios.

Todas las escrituras administrativas HTTP adquieren el mismo bloqueo de la fila del rol admin en PostgreSQL y vuelven a comprobar identidad/permisos antes de cambiar datos. Eso serializa comprobación del último admin, consumo de prueba y aceptación. SQLite se usa para pruebas funcionales; la garantía concurrente se prueba con PostgreSQL. No aplicar estas garantías a modificaciones SQL manuales que eludan la aplicación.

El arranque mantiene la matriz declarada y solo crea el admin inicial si no existe ningún usuario. Cambiar el correo del admin inicial o transferir su rol ya no recrea automáticamente otra cuenta privilegiada a partir del entorno.

### Aplicación y recuperación operativa

1. Respaldar la base y verificar que se conoce la contraseña de al menos un administrador activo. Conservar la copia fuera de Git.
2. Tras revisar e integrar el PR en la rama de trabajo, actualizar backend y frontend juntos y ejecutar `alembic upgrade head` mediante el procedimiento Docker de la instalación. La migración es `0034_administration`; no borra historias, usuarios ni centros.
3. Todos deben volver a iniciar sesión: los tokens previos carecen de los nuevos atributos obligatorios. Revisar Usuarios y roles → asignaciones, y Seguridad → administración y restricciones.
4. Probar con cuentas ficticias: secretaria sin acceso clínico; médico sin gestión de usuarios; admin sin acceso a historias; bloqueo y reingreso; nombramiento con segunda cuenta; cancelar y aceptar solicitudes; consultar auditoría.
5. No usar downgrade como recuperación ordinaria: elimina las tablas nuevas de seguridad. En caso de incidente, restaurar código/base coordinadamente desde la copia probada. La reversión de la migración se verifica solo sobre una base desechable.

Si el único administrador pierde su contraseña, esta fase no tiene recuperación automática: requiere intervención operativa controlada y registro externo de esa intervención. Para el piloto conviene nombrar un segundo administrador de confianza mediante el flujo existente. MFA, códigos de recuperación, verificación de canales, limitación distribuida de intentos de login, revocación individual por dispositivo y aislamiento multiempresa son posteriores. El punto de reautenticación es el lugar para incorporar factores futuros sin alterar todas las rutas. HTTPS y la custodia de configuración/respaldos pertenecen al despliegue; esta PR no despliega ni certifica la instalación.

6C2B permanece pausada. La fase 6C3 no añade campos clínicos ni cambia plantillas de Cardiología.

El [inventario de rutas administrativas del estado inicial](6c3-route-audit.md) enumera método, endpoint, permiso y archivo, extraídos del commit auditado.

## Evidencia de verificación (2026-09-24)

- Backend completo: **302 pruebas aprobadas**, sin omitidas, con PostgreSQL para concurrencia administrativa, clínica e identidad de pacientes. Tras añadir tres casos de privacidad/arranque, la suite específica final pasó **16/16**; incluye esos tres casos adicionales.
- Frontend completo: **266 pruebas aprobadas**, sin omitidas. Verificación final de Seguridad, shell, Dashboard y navegación: **46/46**, más compilación TypeScript/Vite correcta.
- PostgreSQL desechable: todas las migraciones hasta `0034_administration`, downgrade a `0033_specialty_codes`, nuevo upgrade y revisión de head correctos.
- Concurrencia administrativa: dos administradores que intentan desactivarse mutuamente dejan exactamente uno activo; dos solicitudes con la misma prueba producen un único cambio y consumo.
- `git diff --check` correcto. No se ejecutó una validación visual manual en navegador ni una prueba de despliegue sobre la instalación real. Las pruebas de interfaz son de comportamiento con DOM simulado.
- El workflow `Security and administration` repite backend, frontend y migraciones en PRs dirigidas a `feat/complete-care-context` o `main`. La configuración usa exclusivamente credenciales y bases desechables de CI.
