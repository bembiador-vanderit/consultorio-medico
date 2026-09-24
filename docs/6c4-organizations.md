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
