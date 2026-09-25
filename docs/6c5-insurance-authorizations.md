# 6C5 — Seguros / ARS, coberturas y autorizaciones

## Base y alcance

PR #50 integrado en `feat/complete-care-context` mediante `3b7c92e37e1676eed654122bd090f2ee4daf633a`, después de comprobar ausencia de conflictos y CI aprobada para `2c577d3`. Rama `feat/6c5-insurance-authorizations`. Sin cambios en main ni despliegue. Cardiología sigue pausada.

## Modelo y decisiones

- `insurance_companies`: catálogo existente, exclusivo de organización, con nombre, código y estado; se amplía su edición/desactivación. Nombres/códigos únicos dentro del tenant.
- `insurance_plans`: organización, aseguradora, nombre, código, descripción y estado. Nombre único por aseguradora y organización. Un plan no cambia de aseguradora. Desactivar no elimina las afiliaciones ni las coberturas.
- `patient_insurances`: se conservan todas las filas y `plan_name` previos. Se añaden plan de catálogo opcional, titular, relación, vigencia desde/hasta y notas administrativas. No se transforma texto histórico en planes inventados. Estado activo/inactivo; las fechas determinan elegibilidad para una cita. Principal es una preferencia explícita, no una renovación automática. Al designar otro principal se retira esa marca del anterior, conservando ambos registros activos. Las escrituras se serializan bloqueando el paciente en PostgreSQL. Desactivación lógica; no hay eliminación HTTP.
- `appointment_insurance_coverages`: una cobertura financiera por cita, independiente de `AppointmentCoverageTransfer` (sustitución de médicos). Relación opcional con afiliación; copia de nombre de ARS/plan, afiliado, titular, relación y vigencia. Servicio/procedimiento en texto administrativo, moneda de tres letras (DOP por defecto), tarifa base, monto ARS, copago y autorización. Permite particular, sin seguro y con monto ARS cero.
- La fotografía se toma al seleccionar una afiliación distinta. Cambiar el catálogo o afiliación posteriormente NO recalcula ni refresca esa fotografía. Editar importes/autorización tampoco la refresca. Para nueva afiliación se valida aseguradora/plan activos, paciente y vigencia en la fecha de cita.
- Una cita con cobertura no se elimina ni cambia de paciente/médico/centro; puede cancelarse conservando trazabilidad. Reprogramar respeta la vigencia guardada. Citas completadas/canceladas/ausentes no admiten seleccionar otra afiliación; los ajustes administrativos explícitos de importes/autorización siguen auditados.

## Importes y autorización

`Numeric(12,2)` y `Decimal`, no aritmética binaria de punto flotante en backend. Montos finitos, no negativos, hasta dos decimales. `base_amount = covered_amount + patient_copay`. `expected_insurer_balance = covered_amount`: monto esperado bruto; no es cuenta por cobrar, saldo contable, aprobación de ARS ni pago. El monto autorizado es opcional e independiente para registrar autorizaciones parciales; no modifica automáticamente la distribución. No se incluye deducible en esta fase.

Estados publicados por `GET /insurance/authorization-states`: `pending` (Pendiente), `authorized` (Autorizada), `rejected` (Rechazada), `not_required` (No requerida). Autorizada exige número; fecha/hora opcional con zona horaria, monto autorizado opcional y observaciones. Sin flujo automático ni contacto con ARS. El catálogo se centraliza en el contrato backend; columna textual sin enum PostgreSQL, de modo que ampliar estados requiere un cambio de contrato y pruebas, no un enum de base. No se permite inventar estados desde el cliente. La UI muestra la fecha en hora local del dispositivo y envía offset UTC.

Bloqueo de cita más revisión optimista: creación con `revision=0`, actualización con la revisión devuelta. Conflicto responde 409; la UI obliga a recargar para evitar sobrescribir cambios de otro usuario. La clave única por cita refuerza el bloqueo. Conservación histórica significa independencia frente a cambios de afiliación/catálogo; el operador autorizado puede corregir explícitamente la cobertura. No se implementa libro contable inmutable ni historial completo de cada valor anterior.

## Permisos, alcance y auditoría

Se reutiliza 6C3: `insurance:manage` para admin y secretaria, nunca para doctor solo. Admite denegación individual en Seguridad. Escrituras exigen también `patients:access`, alcance de paciente o de cita/centro/médico según 6C4. Lectura clínica con `patients:access` dentro del alcance ya autorizado; no amplía acceso a expedientes. Catálogo editable con `users:manage` y reautenticación existente. Plataforma no obtiene acceso por su sola autoridad global.

La ruta histórica `POST/PUT /patients` también aplica la nueva capacidad cuando modifica afiliaciones, usa el mismo servicio y conserva operaciones de identidad sin cambios de seguro. La UI de ese formulario bloquea edición de seguro sin permiso y omite ese payload.

Todos los modelos son `TenantOwned`. La sesión HTTP ligada al host delimita lecturas, búsquedas, relaciones y escrituras; IDs foráneos no permiten seleccionar un tenant. Las referencias deben pertenecer al mismo tenant; plan a su aseguradora y seguro al paciente de la cita. Se mantiene el límite de 6C4: no hay RLS para SQL manual privilegiado.

Auditoría en `security_audits`, en la transacción del cambio: actor, organización, acción y entidad identificada; centro de la cita en cobertura/autorización. Incluye altas/ediciones/desactivaciones de afiliación, sustitución de principal, catálogos, coberturas y autorización. Consulta desde Seguridad. No copia números de afiliado/autorización, titulares, notas, contraseñas ni payloads a auditoría. No es un almacén inviolable contra un administrador de base ni registra todos los valores previos.

## API y UI

- `/insurance/companies`: GET (opcional `include_inactive`), POST y PUT `/{id}`.
- `/insurance/plans`: GET (filtro `insurance_company_id`, `include_inactive`), POST y PUT `/{id}`.
- `/insurance/patients/{patient_id}`: GET histórico, POST; PUT/DELETE `/{insurance_id}` (DELETE desactiva).
- `/insurance/appointments/{appointment_id}/coverage`: GET nullable, PUT con revisión.
- Navegación administrativa «Aseguradoras / ARS» para catálogo y planes; Pacientes → Seguro → «Seguros» para afiliaciones; Agenda → detalle de cita → «Cobertura / Autorización». Componentes y tokens Atlas existentes, sin cambio de tema.

## Migración y operación

`0037_insurance_coverage`, posterior a `0036_access_schedules`. Añade tablas, columnas opcionales y restricciones sin reescribir seguros existentes ni sembrar ARS/planes/coberturas del piloto. Agrega capacidad a roles existentes y el arranque mantiene esa matriz. No requiere inventar datos para Dr. Osiris.

Antes de actualizar la instalación, respaldo comprobado y despliegue coordinado de backend/frontend; ejecutar `alembic upgrade head`. Esta PR no despliega. Downgrade solo para base desechable: elimina estructura de 6C5, por lo que no es recuperación del piloto con datos de la fase. `scripts/check_insurance_migration.py` rechaza bases no vacías, crea afiliación sintética en 0036 y comprueba preservación, upgrade, downgrade y re-upgrade.

## Límites y siguientes fases

6C6: Caja, facturación, pagos y sus asientos; 6C7: reclamaciones, cuentas por cobrar ARS y conciliación. Ninguno implementado aquí. Tampoco Device Hub ni Cardiología específica.

Límites menores: una cobertura/servicio por cita, sin coordinación entre varios pagadores; sin tarifas automáticas de planes, deducibles, conversión monetaria ni validación externa de autorización. Catálogos sin paginación por ahora. Vigencia no cambia automáticamente el booleano activo ni promueve otro principal. Para cambios históricos de afiliación se recomienda desactivar la anterior y registrar otra; editar corrige el registro actual sin conservar versiones completas. Verificación de UI automatizada mediante DOM simulado; revisión visual manual pendiente.
