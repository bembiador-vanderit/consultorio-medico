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
