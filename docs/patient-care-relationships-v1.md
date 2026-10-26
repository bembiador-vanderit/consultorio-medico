# Patient Care Relationships V1 — 0059

## Alcance y activación

Implementación posterior a `0058_patient_safety`, sin activación en la base
oficial durante esta microfase. Revisión nueva: `0059_patient_care`, una sola
cabeza. El paciente sigue siendo único: no se copian expedientes por médico.

No existía una entidad longitudinal persistida. `patient_scope.py` deriva el
acceso actual de citas, historias, documentos y coberturas. `CareContext` es
configuración de centros, no un episodio clínico. Ninguno de esos mecanismos
de autorización se sustituye por la nueva relación.

El código tolera el esquema 0058: el hook de finalización no escribe relaciones
si falta la tabla; capabilities devuelve `enabled=false`. Bootstrap solo añade
el catálogo y los permisos nuevos cuando existe el esquema. No hay activación
automática mediante esta entrega; el target local Alembic sigue en 0058.

## Modelo e identidad

`PatientCareRelationship` pertenece a una organización. Unicidad permanente por
`organization_id + patient_id + doctor_id`, incluidos registros finalizados.
Reactivar actualiza la misma relación y conserva el historial de auditoría.

- Tipos: `treating`, `consultant`, `specialist_followup`, `primary`.
- Estados: `active`, `follow_up`, `historical`, `ended`.
- Histórica es un estado, no un segundo tipo redundante.
- Orígenes operativos V1: `consultation`, `administrative_assignment`.
- El esquema reserva `referral`, `migration`, `emergency`, `inpatient` e
  `interconsultation`. No existen endpoints que fabriquen esos episodios.
- Centro y especialidad son opcionales, dentro de la organización y relaciones
  válidas del médico. Representan la referencia más reciente, no una lista de
  todas las sedes atendidas. Los cambios quedan auditados.
- `started_at` indica inicio de la asociación. `first_seen_at`/`last_seen_at`
  indican atención clínica real y son nulos en una asignación sin atención.
- Contexto canónico opcional: primera y última `clinical_history_id`.
- Actores, timestamps, revisión optimista y `ended_at` quedan persistidos.

La migración crea solo la tabla, nueve FKs RESTRICT, seis checks, tres índices
de consulta y una constraint única. No modifica pacientes, citas, historias,
documentos ni Safety; no infiere relaciones históricas mediante backfill.
Eso requerirá una microfase explícita con criterios de evidencia y revisión.
El downgrade se permite con tabla vacía; con relaciones existentes se bloquea
para evitar pérdida silenciosa de datos asistenciales/auditoría.

## Creación y continuidad

Solo la transición autorizada y condicional de una historia clínica a
`completed` genera/actualiza automáticamente la relación. La creación,
actualización y auditoría participan en la misma transacción de finalización.
Un fallo SQL revierte también la finalización; no queda una mitad del cambio.

Buscar, abrir ficha, leer historial, crear borrador, firmar un documento aislado,
cancelar una cita o modificar su estado administrativamente NO generan relación.
No se reinterpretan consultas antiguas durante lecturas.

La misma evidencia repetida es idempotente. Otra atención actualiza primera y
última atención de forma monotónica; la más reciente actualiza centro/especialidad
no nulos. Se preservan tipo, origen inicial y seguimiento explícito. Una atención
posterior al cierre administrativo reactiva la relación; una atención antigua
procesada tarde no revierte un cierre posterior.

Los escritores bloquean el paciente con `SELECT FOR UPDATE` antes de localizar
o crear la relación. La constraint única es la protección final en PostgreSQL.
El mismo paciente puede tener relaciones distintas con varios médicos; esto
no duplica al paciente. Un POST repetido devuelve la relación existente, sin
reabrirla ni cambiarla silenciosamente.

## API y asignación manual

Prefijo `/api/v1/patient-care`:

- `GET /capabilities`: disponibilidad y capacidad administrativa efectiva.
- `GET /patients/{id}/relationships`: metadatos de médicos relacionados.
- `POST /patients/{id}/relationships`: asignación administrativa, motivo requerido.
  Devuelve 201 al crear y 200 si ya existe la misma asociación.
- `PUT /patients/{id}/relationships/{relationship_id}`: tipo/estado/centro/especialidad,
  motivo y revisión requeridos; revisión obsoleta devuelve 409.
- `GET /patients/{id}/relationships/{relationship_id}/history`: auditoría autorizada.
- `GET /my-patients`: asociaciones del médico autenticado, filtros `status`,
  `center_id`, paginación `limit` (máximo 200) y `offset`.

No se admite cambiar paciente, médico, organización, origen, contexto, fechas
de atención ni actores desde el payload administrativo. No hay DELETE.
La asignación/edición manual queda disponible por API a administradores con
permiso explícito, no en la ficha general ni para secretaría automáticamente.

## Seguridad y auditoría

Lectura: usuario activo, rol médico/administrador y permisos efectivos
`patients:view` + `patient_care:view`, además del scope de paciente existente.
Gestión: administrador con ambos anteriores + `users:manage` +
`patient_care:manage`. Las denegaciones individuales tienen precedencia.
En bootstrap inicial tras activación, médico/admin reciben lectura y solo admin
gestión; reinicios posteriores no restauran permisos retirados del catálogo.
Secretaría no recibe permisos por defecto. Platform admin no obtiene acceso.

Cada request mantiene el tenant resuelto por host y validado por sesión. Lecturas,
escrituras, FKs y actores pasan por la infraestructura TenantOwned existente.
No existe sharing cross-org ni selección arbitraria de doctor/centro/especialidad.

**Relationship discovery ≠ clinical record access.** Mis pacientes entrega solo
identidad mínima (id/nombre), metadatos de su propia relación y
`clinical_access_granted=false`. Esa respuesta no autoriza abrir ficha, historias,
documentos o Safety; cada recurso conserva sus validaciones independientes.
Los nuevos registros nunca se consultan desde los servicios de scope clínico.

Se reutiliza `ClinicalAuditLog`, recurso `patient_care_relationship`, acciones
`created`, `manual_assigned`, `updated`, `status_changed`, `ended`, `reactivated`.
Incluye actor, paciente/médico, fecha servidor, contexto, revisión, before/after y
motivo administrativo. Leer/no-op no se audita como modificación. La auditoría
genérica clínica excluye este recurso para no eludir su autorización específica.

## UI y evolución futura

Ficha del paciente: bloque compacto (máximo tres relaciones relevantes, con
preferencia por activas/seguimiento), estado vacío explícito y modal de solo
lectura con todos los metadatos. No se presentan controles de modificación.
El detalle usa dos columnas en desktop/tablet y una en móvil; nombres largos
se ajustan. La comprobación visual usa fixture DEV sintético, sin acceso HTTP
a la base oficial. No equivale a activar 0059 en esa instancia.

Una relación habitual, incluso `primary`, NO asigna responsabilidad por el
episodio actual. Emergency/Inpatient deberán modelar sus asignaciones de episodio
por separado y podrán utilizar este servicio con contexto y actor reales.
No se implementan camas, enfermería, avisos, turnos ni esos módulos ahora.

Historial compartido es otra política futura: organización/centro, episodio,
lectura temporal y eventual break-glass requerirán permisos y auditoría propios.
La relación por sí sola nunca concederá lectura clínica global.

## Validación reproducible

- `python -m pytest -q tests/test_patient_care.py` (regresión HTTP/servicio).
- `python tests/validate_patient_care_postgres.py` SOLO en PostgreSQL desechable:
  exige host `atlas-0059-care-qa-*` y base `atlas_0059_qa` antes de cualquier DDL.
  Verifica roundtrip 0058→0059→0058→0059, hashes de siete tablas históricas,
  constraints, aislamiento y dos escritores concurrentes automáticos/manuales.
- `node --test tests/patient-care.test.mjs`, suite frontend y build.
- Fixture visual DEV: `tests/fixtures/patient-care-preview.html`, datos sintéticos.
- Nunca ejecutar downgrade en la base oficial para estas pruebas.

### Ajuste de fixture de especialidades

La suite completa detectó que
`test_specialty_cannot_change_after_consultation_starts_or_completes` invocaba
directamente la función de cierre con un rol médico sin `clinical:access`.
Esa llamada evitaba la dependencia HTTP que ya exige dicho permiso. Se reprodujo
el fallo de forma aislada y se añadió el permiso únicamente a la identidad
sintética de esa prueba. No se relajó el hook ni la autorización productiva;
siguen intactas las expectativas de conflicto al cambiar especialidad después
del inicio/cierre. Especialidades + relaciones: 63 pruebas aprobadas.

## Archivos de esta microfase

Nuevos:

- `backend/alembic/versions/0059_patient_care.py`
- `backend/app/models/patient_care.py`
- `backend/app/schemas/patient_care.py`
- `backend/app/services/patient_care.py`
- `backend/app/api/routes/patient_care.py`
- `backend/tests/test_patient_care.py`
- `backend/tests/validate_patient_care_postgres.py`
- `frontend/src/types/patientCare.ts`
- `frontend/src/components/patients/PatientRelatedDoctors.tsx`
- `frontend/src/components/patients/patientRelatedDoctors.css`
- `frontend/tests/patient-care.test.mjs`
- `frontend/tests/fixtures/patient-care-preview.html`
- `frontend/tests/fixtures/patient-care-preview.tsx`
- Este documento.

Integraciones acotadas en archivos existentes (sus otros cambios locales previos
se preservan):

- `backend/app/models/__init__.py`: registro del modelo.
- `backend/app/main.py`: registro del router.
- `backend/app/api/routes/clinical_history.py`: hook transaccional de cierre y
  exclusión de la auditoría de relaciones del endpoint genérico.
- `backend/app/services/administration.py`: denegaciones/permisos nuevos.
- `backend/app/services/bootstrap.py`: catálogo/grants iniciales condicionados al esquema.
- `backend/tests/test_clinical_specialties_context.py`: permiso del médico sintético
  en la prueba que invoca directamente el cierre.
- `frontend/src/pages/Patients.tsx`: bloque con clave por paciente seleccionado.
- `frontend/src/pages/AdministrationSecurity.tsx`: rótulos de las denegaciones nuevas.

No se modifica en esta fase `patient_scope.py`, Safety, Agenda, Queue, finanzas,
Form Designer, `.env`, dependencias ni datos oficiales.

## Resultado de validación — 15/10/2026

- Rama: `feat/complete-care-context`; HEAD sin cambiar:
  `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
- Alembic inicial current/head: `0058_patient_safety`.
- Final: current oficial `0058_patient_safety`, head código `0059_patient_care`.
- Backend específico de relaciones: **36 passed**.
- Relaciones + especialidades: **63 passed**.
- Regresión focal inicial de relaciones/ciclo clínico/Safety/aislamiento:
  **197 passed** (antes de incorporar tres casos adicionales de continuidad/rollback).
- Backend completo final: **528 passed, 29 skipped, 0 failed**, 11162 warnings.
- Los 29 skips son opt-in PostgreSQL de otras validaciones: administración (2),
  ARS (1), concurrencia clínica (5), identidad de borradores 0057 (1), finanzas (5),
  seguros (2), identidad de paciente (5), pausas (1), orden de agenda (1),
  política de llamada (2), Queue V2 (2), Queue V3 (1), salas de espera (1).
  No se declaran ejecutadas esas pruebas dentro de esta microfase.
- Frontend focal relaciones/pacientes/Safety: **73 passed**.
- Frontend completo final: **432 passed, 0 skipped, 0 failed**.
- Build frontend y compile Python: PASS; `docker compose config --quiet`: PASS.
- PostgreSQL 16 temporal: roundtrip y constraints PASS; dos observadores del
  mismo evento obtienen `[1,1]`, con una sola relación y una sola auditoría de
  creación; dos asignadores obtienen el mismo id y `created=false/true`.
- Dos médicos distintos pueden relacionarse con el mismo paciente: PASS.
  Siguen existiendo dos pacientes sintéticos, no tres. Las huellas SHA-256 de
  pacientes (2), citas (2), historias (2), preoperatorias (1), exámenes físicos (1),
  Safety (1) y auditoría previa (1) coinciden en cada paso.
- Downgrade con relaciones pobladas: bloqueado de forma segura, según diseño.
- UI sintética revisada a 1440, 768 y 390 px: sin overflow horizontal; detalle
  de solo lectura y botón móvil de 44 px. No se activó la UI oficial 0059.
- `git diff --check`: PASS; 14 archivos nuevos sin whitespace final. Git advierte
  de LF/CRLF en `AgendaMonthPanel.tsx`, cambio previo ajeno que no se modificó.
- Advertencias: deprecaciones existentes de `utcnow`, Starlette/AnyIO/ReportLab
  y chunk principal de Vite >500 kB (664.23 kB). No se añadieron dependencias.
- Contenedor PostgreSQL QA, validadores `--rm` y volúmenes anónimos eliminados;
  se reutilizó la red existente, sin crear ni borrar redes oficiales.
- Sin commit, push, deploy, downgrade ni migración de la base oficial.
