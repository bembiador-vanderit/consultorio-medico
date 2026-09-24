# 6C4 — Organizaciones y contexto de acceso

## Auditoría previa (2026-09-24)

Base: `19c1599`, PR #48 abierto, hacia `feat/complete-care-context`. Esta rama depende de #48; no integra main. Cardiología/6C2B, Seguros y Caja permanecen fuera del alcance.

- `users`, `roles`, `permissions`, `user_roles`: identidad y capacidades globales a la instalación. Reutilizar los códigos de rol y permiso, trasladando su asignación operativa a una membresía.
- `care_centers`, `user_centers`, `secretary_center_scopes`: lugares de atención y alcance asistencial. Un centro no es un tenant; varios centros pertenecen a una organización.
- Pacientes, citas, historias, órdenes, coberturas, seguimientos, comunicaciones y auditorías carecen de organización. Los servicios aplican alcance médico/secretaria, pero admin tiene alcance de instalación.
- Catálogos clínicos y localidades son editables por admin: también requieren aislamiento. Países y divisiones territoriales son datos de referencia comunes, sin escritura HTTP.
- JWT ligados a usuario/versión/tipo; falta contexto de organización. El proxy de Vite cambia Host, lo cual impediría una resolución segura por dominio.
- Worker de recordatorios utiliza una sesión global: debe iterar organizaciones con sesiones independientes.
- Índices únicos de identificación de pacientes y nombres de catálogos son globales; deben delimitarse por organización.

## Decisiones previas

Identidad global `User`, `Organization` explícita, membresía usuario↔organización con estado, roles existentes y restricciones propias. Separar autoridad de plataforma de admin de organización. Resolver únicamente hosts configurados en backend, rechazar desconocidos e ignorar cabeceras de tenant/forwarded host. Tokens ligados al contexto resuelto. Cada petición usa una sesión nueva y delimitada; las consultas y escrituras verifican tenant además del alcance clínico actual. Mantener el piloto como organización inicial y migrar todas las filas históricas sin eliminar información.

La gestión de identidad compartida (correo/contraseña/nombre) no se delegará a un admin de uno de varios tenants: requerirá un flujo global futuro. El bloqueo y los roles dentro del tenant sí son propios de su membresía.

## Implementación y límites

- `organizations` representa la entidad propietaria de datos. `care_centers` conserva la ubicación asistencial y ahora tiene `organization_id`. Un usuario puede tener varias membresías; cada membresía tiene estado, roles y restricciones propios. Los catálogos `Role` y `Permission` siguen siendo únicos y no se duplican por tenant.
- Los registros clínicos, operativos, catálogos editables, notificaciones y auditorías tienen `organization_id` obligatorio. Las consultas ORM y relaciones se filtran en una sesión ligada al host antes de autenticar; las escrituras verifican referencias y rechazan cambios de propietario. Las tablas de asociación de centros y especialidades se delimitan por sus entidades relacionadas. El backend siempre comprueba membresía activa y permisos efectivos del contexto.
- `security_audits` y `clinical_audit_logs` guardan `organization_id`; agregan `center_id` cuando la operación se refiere a un centro o a una historia con centro. La migración rellena la organización del historial y el centro de auditorías clínicas ligadas a una historia.
- Los hosts se configuran solo en el backend. `TENANT_HOSTS_JSON` relaciona nombres exactos con `slug` de organización; `PLATFORM_HOSTS_JSON` enumera hosts de plataforma. Ejemplo de laboratorio: `TENANT_HOSTS_JSON={"one.example.test":"pilot","two.example.test":"second"}` y `PLATFORM_HOSTS_JSON=["admin.example.test"]`. No representan dominios comerciales. El proxy debe conservar `Host`; Vite ya lo hace. El reverse proxy de producción debe validar y enrutar esos hosts y usar HTTPS. `X-Tenant` y `X-Forwarded-Host` no seleccionan contexto.
- El piloto que accede por la IP de su PC debe añadir esa IP exacta en `TENANT_HOSTS_JSON` junto a `localhost` antes de actualizar. Así se conserva su forma de acceso sin aceptar hosts arbitrarios.
- JWT de acceso y refresh incluyen `scope` y `org`; un token de plataforma no abre rutas clínicas, y un token de tenant no abre la lista de organizaciones. Un superadministrador de plataforma necesita además membresía activa y rol local para operar dentro de un tenant. La pantalla de plataforma presenta solo el inventario; la pantalla de tenant muestra la organización actual.
- El worker de recordatorios itera organizaciones activas y abre una sesión aislada para cada una. Una falla de envío no debe cambiar el contexto de otra sesión.
- La migración `0035_organizations` crea la organización inicial con `slug=pilot`, asigna las filas existentes y copia roles/restricciones a membresías. Incrementa la versión de sesión de todos los usuarios: deberán iniciar sesión nuevamente. Conservar un respaldo verificado antes de actualizar; desplegar backend/frontend juntos. El downgrade solo sirve en base desechable de un tenant y se niega si ya hay otra organización.

### Provisionamiento y límites explícitos

6C4 establece la separación y los contextos; crear una segunda organización, vincular una identidad existente a ella o designar un superadministrador de plataforma requiere un procedimiento operativo controlado fuera de la API pública. No hay autoservicio de altas, invitaciones verificadas ni cambio de tenant mediante parámetro de URL. Nunca se debe vincular a una persona por coincidencia de correo sin verificar su control de la cuenta. Los nombres y contraseñas de identidad son globales; la API de un tenant rechaza cambios de esos campos cuando la identidad pertenece a más de una organización o tiene autoridad de plataforma. La revocación de sesión por cambio de membresía afecta conservadoramente todas las sesiones de la identidad.

El aislamiento en esta fase se aplica a las sesiones de la aplicación. Mantenimiento SQL con privilegios directos debe ejecutarse con control de acceso y auditoría operativa; no existe todavía una política PostgreSQL RLS para usuarios de base arbitrarios. Los catálogos de países y divisiones territoriales son referencia común de solo lectura HTTP. No hay todavía un esquema configurable de catálogo por país para cada tenant ni una interfaz de altas de plataforma. La configuración regional y los catálogos clínicos son propiedad del tenant.

## Validación

La suite `test_organization_isolation.py` comprueba hosts permitidos, tokens de plataforma/tenant, membresía, roles distintos, lectura de pacientes y centros, y rechazo de referencias cruzadas. Se mantienen las pruebas de seguridad administrativa anteriores. La validación de migración usa PostgreSQL desechable con un paciente y un usuario sintéticos antes de `0035`, y comprueba upgrade, downgrade y nuevo upgrade.
