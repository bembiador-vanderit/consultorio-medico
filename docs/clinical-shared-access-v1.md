# Clinical Shared Access Policy V1 — 0060

## Activación separada y default conservador

Base oficial durante implementación: `0059_patient_care`. Única nueva cabeza:
`0060_clinical_sharing`, posterior a 0059. **No aplicar en la base oficial en esta fase.**
La revisión crea únicamente `clinical_sharing_policies` y un índice de búsqueda
de auditoría sobre `clinical_audit_logs`. No modifica filas previas, no crea
relaciones, no hace backfill y no siembra una política que amplíe acceso.

Sin tabla, sin fila o con modo `assigned`, los endpoints actuales conservan
exactamente su autorización por autoría, cita y cobertura. Los tres recursos
compartibles tienen default false. El frontend oculta el visor hasta disponer
de capacidades afirmativas; Seguridad indica activación pendiente en 0059.
Downgrade temporal con tabla vacía permitido; con políticas configuradas falla
de forma explícita para no destruir decisiones administrativas auditadas.

## Arquitectura encontrada y decisiones

`patient_scope` separa identidad de contenido. `clinical_access` controla autoría
y coberturas temporales/con continuidad; las escrituras tienen bloqueo y revisión.
Documentos y Safety tienen permisos y authorizers propios. `CareContext` es un
directorio de centros, **no** un episodio ni un encuentro. El contexto clínico
canónico actual es `ClinicalHistory`, enlazado opcionalmente con Appointment.

Se conserva esa capa de escritura sin ampliar `can_access_history`,
`require_patient_clinical_scope`, `_clinical_doctor` ni la semántica de 0059.
El nuevo servicio central `clinical_sharing.decide` solo decide **lectura**.
Devuelve allow/deny, razón, revisión de política y read_only. No deduce permisos
de PatientCareRelationship. La relación es una señal opcional de una política
expresamente habilitada y no asigna responsabilidad del episodio actual.

## Políticas

Una fila por organización, revisión optimista y cambios con motivo obligatorio:

- `assigned`: acceso actual, sin ampliación. El hook de contexto reconoce al
  médico asignado a una ClinicalHistory canónica del mismo paciente/centro.
- `active_relationship`: exige relación active/follow_up, no historical/ended.
- `same_center`: exige centro activo del recurso y asignación del médico allí.
- `organization`: permite recursos de la organización, nunca de otra.

`limit_to_same_center` limita adicionalmente relación/organización. En same_center
siempre se exige el centro, aunque el booleano se hubiera guardado false.
Un centro nulo no satisface una política limitada por centro. Se evalúa el
centro persistido de cada registro; un query parameter no puede inventarlo.
Safety es longitudinal y no tiene centro: se exige evidencia paciente/centro
en citas válidas, historias, documentos o relaciones, no un centro arbitrario.

## RBAC, horarios y aislamiento

Siempre: contexto tenant ligado al host, membresía activa, médico activo,
`patients:view`, `clinical:access`. Documentos requieren además
`clinical_documents:view`; Safety requiere `patient_safety:view`. Las
denegaciones efectivas prevalecen, incluida la compatibilidad de patients:access.
current_user conserva session_version, validación de organización y lease de
horario. El servicio verifica además la ventana de acceso de la membresía.
Platform admin y administrador no clínico no adquieren contenido clínico.
No hay sharing cross-org aunque el mismo médico sea miembro de ambas.

## Recursos y solo lectura

Recursos V1 independientes: clinical_history, clinical_documents, patient_safety.
El visor explícito muestra consultas finalizadas, documentos completados/firmados
y entradas longitudinales Safety (incluido su estado). No comparte borradores
ajenos. No exporta PDF ni altera renderer/diseñador o PDF existentes.
Diagnósticos, prescripciones, resultados, órdenes y enmiendas estructuradas no
se abren indirectamente: continúan sujetos a sus rutas y permisos actuales.
La proyección de historial contiene los campos canónicos ClinicalHistoryBase;
los documentos reutilizan rótulos de su versión de plantilla o del catálogo legacy.

El buscador existente de Pacientes incorpora descubrimiento de identidades
con evidencia de recursos expresamente compartibles. No hay buscador paralelo.
Solo los GET/count usan ese predicado: PUT conserva el scope previo.
La ficha compartida devuelve identidad básica, no documentos de identidad,
contactos de emergencia, grupo sanguíneo ni demografía extendida. Se marca
shared_read_only; el formulario de ficha oculta edición en ese caso.
Compartir lectura no habilita creación de citas/consultas o edición demográfica.
Esas operaciones conservan selección y contexto autorizados propios.

## API y UI

Prefijo `/api/v1/clinical-sharing`:

- GET /policy: admin del tenant con users:manage.
- PUT /policy: mismo permiso, reautenticación de una sola operación existente,
  motivo y revisión (0 cuando no hay fila); 409 si cambió concurrentemente.
- GET /patients/{id}/capabilities: solo metadatos afirmativos por recurso, sin
  contenido ni auditoría de apertura. Sin capacidad, resources vacío.
- GET /patients/{id}/records/{resource}: apertura explícita, paginación 25/50,
  centro opcional restrictivo, reevaluación servidor y `Cache-Control: no-store`.
  No existen métodos de modificación en el gateway compartido.

Seguridad → Acceso clínico entre médicos: cuatro opciones y tres recursos,
sin matriz de roles nueva. La reautenticación usa el diálogo global existente.
Ficha → Historial compartido en modo solo lectura: botones únicamente para
recursos permitidos. Modal de texto/valores, sin inputs, guardado o firma.
No se carga contenido al renderizar, al descubrir relación ni mediante polling.
Un cambio de paciente o una denegación descarta contenido previo. La configuración
se revalida al abrir: una capacidad antigua no equivale a una autorización vigente.

## Auditoría y concurrencia

Se reutiliza ClinicalAuditLog, sin sistema paralelo. policy_updated registra actor,
organización, timestamp, motivo, before/after y revisión. Lecturas usan acción
clinical_sharing.read y tipo shared_{resource}, con paciente, actor, centro filtro
si existe, recurso, revisión, razones y read_only; nunca copia contenido clínico.
Abrir un recurso puede abarcar varios centros solo si esa política lo permite;
center_id nulo en auditoría representa esa consulta agregada, no un centro ficticio.
Una apertura explícita produce auditoría, deduplicada por actor/paciente/recurso/
centro/revisión durante cinco minutos. No se registran renders como modificaciones.
Se bloquea la fila de organización para serializar primera configuración, cambios
de política y lecturas auditadas. Así dos procesos no duplican la auditoría y
un cambio ya confirmado no deja una lectura posterior autorizada por caché.
La auditoría y la lectura fallan juntas si no puede persistirse el evento.

## Futuro: episodios y break-glass (no implementados)

`future_episode_access` reserva la interfaz doctor/patient/organization/context/
resource, y siempre devuelve deny en V1. Un futuro adaptador comprobará
episode_participant/responsible/consultant/on_call, vigencia y alcance, antes de
producir una decisión. Una relación previa no reemplazará esa responsabilidad.

Break-glass futuro deberá aportar doctor/patient, motivo, resource_scope,
started_at/expires_at, context_id, estado y evento de auditoría, con autorización
específica, revisión de uso y expiración servidor. No hay tabla, endpoint,
política configurable, bypass, Emergencia ni Hospitalización operativos ahora.

## Validación y límites V1

Pruebas sintéticas host-bound: default, relaciones activas/históricas, centro,
organización, recursos independientes, RBAC/denegaciones/horario, modificación
prohibida, lectura y configuración auditadas, revocación, contexto, ausencia de
tabla y no exposición cross-tenant. PostgreSQL temporal: roundtrip, huellas de
86 tablas previas, constraints, índices y dos lecturas concurrentes/un audit.

La proyección pagina la respuesta después de filtrar autorización; actualmente
evalúa registros del paciente en memoria, como el historial previo. Grandes
expedientes requerirán paginación/cursor a nivel SQL y revisión de rendimiento.
Los accesos directos SQL privilegiados siguen fuera de la protección RBAC de UI.
No hay cifrado por campo nuevo ni política nueva de retención. El indicador
de lectura no es una garantía de permiso futuro: cada petición se reautoriza.

## Resultado ejecutado — 15/10/2026

**RESULT=PASS — implementación y validación temporal, NO activación oficial.**

- Rama: `feat/complete-care-context`; HEAD sin cambiar:
  `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
- Current/head iniciales: `0059_patient_care`. Cabeza de código final única:
  `0060_clinical_sharing`. Base oficial final: **0059**, sin tabla de políticas.
- Backend específico: **25 passed**; focal con pacientes/Care/Safety: **152 passed**.
- Backend completo final: **553 passed / 29 skipped / 0 failed**, 11887 warnings,
  740.70 segundos. Los skips son PostgreSQL/concurrencia opt-in previos; no se
  activaron contra la base oficial. La validación PostgreSQL 0060 se ejecutó aparte.
- Frontend específico: **14 passed**; focal con Patients/Care/Safety: **87 passed**.
- Frontend completo final: **446 passed / 0 skipped / 0 failed**.
- Build final PASS, Python compile PASS, Compose config quiet PASS y
  `git diff --check` PASS.
- Avisos: deprecaciones existentes utcnow/Starlette/AnyIO/ReportLab,
  chunk principal Vite 670.87 kB (>500 kB) y LF/CRLF previo en AgendaMonthPanel.

PostgreSQL desechable en `<LOCAL_EVIDENCE_DIR>`, con puerto y base QA efímeros,
almacenamiento tmpfs independiente, sin volumen oficial.
Roundtrip **0059 → 0060 → 0059 → 0060 PASS**, con huellas de las 86 tablas
anteriores idénticas. Dos FKs, dos checks, unicidad por organización e índice
de auditoría comprobados; valores inválidos y configuración duplicada rechazados.
Dos lecturas concurrentes correctas, **una** auditoría de lectura. Otra comprobación
PostgreSQL del buscador existente encontró un paciente y devolvió identidad
shared_read_only, sin demografía extendida. Contenedor/base temporal eliminados;
los runners --rm también retirados. Sin red o volumen temporal persistente.

Smoke visual con componentes reales en fixture DEV enteramente sintético, sin
HTTP a API ni sesión/datos oficiales: desktop 1440 px y móvil 390 px PASS.
Modal móvil 352 px, ancho interior/scroll 350 px, página 390 px; cero controles
editables, sin overflow horizontal. Viewport restaurado y pestaña QA cerrada.
Evidencia fuera del repo en `<LOCAL_EVIDENCE_DIR>`.

Lectura oficial final: **18 pacientes, 2 relaciones, 2 entradas Safety**, current
0059, tabla nueva ausente. PostgreSQL healthy; health API, docs y frontend HTTP
200; sin errores SQL/startup recientes detectados. No cambios de configuración
real, datos clínicos, permisos persistentes, nuevas cuentas, commit, push o deploy.

### Archivos de esta microfase

Nuevos backend:
`alembic/versions/0060_clinical_sharing.py`, `app/models/clinical_sharing.py`,
`app/schemas/clinical_sharing.py`, `app/services/clinical_sharing.py`,
`app/api/routes/clinical_sharing.py`, `tests/test_clinical_sharing.py`,
`tests/validate_clinical_sharing_postgres.py`.

Integración backend: `app/main.py`, `app/models/__init__.py`,
`app/api/routes/patients.py`, `app/schemas/patient.py`.

Nuevos frontend: `src/components/ClinicalSharingPolicySettings.tsx`,
`src/components/patients/SharedClinicalAccess.tsx`,
`src/components/patients/sharedClinicalAccess.css`, `src/types/clinicalSharing.ts`,
`tests/clinical-sharing.test.mjs`, `tests/fixtures/clinical-sharing-preview.html`
y `tests/fixtures/clinical-sharing-preview.tsx`.

Integración frontend: `src/pages/Patients.tsx`,
`src/pages/AdministrationSecurity.tsx`, `src/types/patient.ts`.
Documentación: este archivo. Cambios previos del workspace preservados.
