# Patient Safety Profile V1 — 0058 (activado en la instancia local oficial)

La activación requiere respaldo y verificación de preservación. El informe
histórico y los registros sintéticos QA específicos se conservan fuera del repositorio.

El perfil de seguridad clínica es LONGITUDINAL: pertenece al paciente dentro de
su organización, no a una consulta, especialidad, médico o formulario.

## Arquitectura y compatibilidad

No existía una estructura longitudinal equivalente: `ClinicalHistory.allergies`
era texto libre y las plantillas incluían campos de alergia/riesgos alérgicos.
Se conservan íntegros, sin importación, inferencia ni sincronización automática.
Clinical Form **no** es la fuente definitiva del perfil longitudinal.

`PatientSafetyEntry` constituye el perfil como colección por paciente; no se crea
una tabla contenedora redundante. Guarda organización, paciente, tipo, agente,
reacción, severidad, estado, inicio opcional, observaciones, procedencia y actores
con fechas del servidor. Tipos: `allergy`, `adverse_reaction`,
`contraindication`, `intolerance_avoid`. Severidades: `unknown`, `mild`,
`moderate`, `severe`, `critical`. Estado: `active`, `inactive`, `entered_in_error`.

Tipo y procedencia se eligen explícitamente. Severidad inicia como desconocida:
el sistema no infiere alergia ni gravedad del texto. Referido por paciente o
familiar nunca se convierte automáticamente en confirmado por médico.

El CareContext existente es configuración de centros, no un encuentro clínico.
Por ello se admite `clinical_history_id` opcional como procedencia canónica, con
verificación de paciente y acceso clínico. No determina la propiedad ni limita
la visibilidad longitudinal a ese encuentro. No puede reasignarse por edición.

## Permisos y aislamiento

Lectura: `patients:view` + `clinical:access` + `patient_safety:view`, rol médico y
relación clínica autorizada con el paciente según el servicio existente.
Escritura agrega `patient_safety:edit`. Las denegaciones individuales prevalecen.
El médico con permiso de lectura retirado tampoco puede modificar.

Secretaría y administrador no clínico no reciben acceso por editar demografía.
El administrador de plataforma no sustituye la membresía, tenant o rol clínico.
Los identificadores de entrada y contexto se validan dentro del paciente y
organización activos. No hay sharing entre organizaciones. La protección es de
la aplicación y ORM, no sustituye controles de acceso directo al servidor SQL.

El bootstrap incorpora permisos médicos una sola vez después de que exista la
tabla; no los restaura tras una retirada administrativa. No agrega estos permisos
con esquema 0057. `/patient-safety/capabilities` permite desplegar código staged
sin consultar una tabla inexistente: la UI permanece inactiva en la base 0057.

## API y trazabilidad

- `GET /patient-safety/capabilities`
- `GET/POST /patient-safety/patients/{patient_id}`
- `PUT /patient-safety/patients/{patient_id}/entries/{entry_id}`
- `GET /patient-safety/patients/{patient_id}/entries/{entry_id}/history`

La identidad, actores y timestamps no son editables por payload. Actualizar exige
`revision`; bloqueo de fila y conflicto 409 evitan sobrescribir otra edición.
Guardar sin cambios no altera revisión ni genera auditoría. El perfil no tiene
endpoint DELETE. Desactivar o registrar por error exige motivo; un registro por
error queda terminal y se añade otro correcto en vez de borrar su historia.

Se reutiliza `ClinicalAuditLog` en la misma transacción: actor, paciente, entrada,
hora, acción, anterior, nuevo y motivo. Sus snapshots clínicos solo se consultan
por el endpoint médico protegido del registro. El visor administrativo genérico
excluye esta categoría incluso si un médico también administra usuarios.
No hay edición/borrado del audit log en la UI normal. Las respuestas de error SQL
de escritura son genéricas, sin volcar payloads clínicos en logs de aplicación.
La retención, cifrado y protección frente a administradores SQL privilegiados
siguen siendo responsabilidades operativas existentes, no una garantía nueva.

## UI

Resumen compacto en la ficha, alerta informativa visible de alergias activas
severas/críticas, sin decisiones ni bloqueo automático de acciones médicas.
Procedencia visible, incluso en la alerta. Ausencia de entradas no equivale a
ausencia de alergias; un error de carga tampoco se presenta como perfil vacío.
Modal inicialmente de lectura; Agregar/Editar explícitos y Guardar/Cancelar.
El bloque está al principio del cuerpo desplazable de la ficha, sin acordeón;
no aumenta el encabezado fijo hasta ocultar otros datos en pantallas bajas.
Conserva entradas inactivas/por error, actores, fechas y trazabilidad. La ficha
solo muestra un resumen; el detalle conserva las descripciones completas.

## Migración y pruebas

`0058_patient_safety` depende de `0057_clinical_draft_identity`. Crea una tabla,
5 FKs, 6 checks y 2 índices. No modifica registros históricos. La implementación
se validó primero sin activación oficial; posteriormente se aplicó en la tarea
controlada documentada arriba. Downgrade permitido únicamente con tabla vacía:
si contiene entradas, falla explícitamente antes de perderlas.

`tests/validate_patient_safety_postgres.py` exige host y base QA específicos antes
de cualquier migración; verifica roundtrip, huellas de datos, restricciones,
aislamiento y rechazo de downgrade poblado en PostgreSQL desechable. No ejecutar
contra la base oficial ni copiar credenciales oficiales a ese entorno.

## Future Emergency / Inpatient integration

Futuros EmergencyEpisode, InpatientEpisode, Interconsultation y MedicationOrder
deben consultar esta colección por paciente con tenant y autorización propios,
sin copiar ni dar propiedad de las entradas al episodio. Pueden referenciar el
contexto de documentación mediante una evolución explícita del esquema; no se
crean esos módulos ni sharing institucional en V1.

Deuda: vincular campos clínicos relevantes de formularios al Safety Profile
mediante **binding controlado**, conservando procedencia, autorización, revisión
y auditoría. No sincronizar texto antiguo como alergias confirmadas. Prescripción,
interacciones y bloqueos automáticos quedan fuera de alcance.

## Archivos de esta microfase

Nuevos:

- `backend/alembic/versions/0058_patient_safety.py`
- `backend/app/models/patient_safety.py`
- `backend/app/schemas/patient_safety.py`
- `backend/app/services/patient_safety.py`
- `backend/app/api/routes/patient_safety.py`
- `backend/tests/test_patient_safety.py`
- `backend/tests/validate_patient_safety_postgres.py`
- `frontend/src/types/patientSafety.ts`
- `frontend/src/components/patients/PatientSafetyProfile.tsx`
- `frontend/src/components/patients/patientSafety.css`
- `frontend/tests/patient-safety.test.mjs`
- `frontend/tests/fixtures/patient-safety-preview.html`
- `frontend/tests/fixtures/patient-safety-preview.tsx`
- Esta documentación.

Integraciones acotadas sobre archivos con cambios previos conservados:

- `backend/app/models/__init__.py`, `backend/app/main.py`: registrar modelo/router.
- `backend/app/services/bootstrap.py`: permisos solo con esquema listo.
- `backend/app/services/administration.py`: permisos efectivos/denegaciones.
- `backend/app/api/routes/clinical_history.py`: excluir snapshots clínicos del
  visor administrativo genérico.
- `frontend/src/pages/Patients.tsx`: incluir resumen en la ficha.
- `frontend/src/pages/AdministrationSecurity.tsx`: etiquetas de restricciones.

La fixture visual es exclusivamente DEV, con un adapter en memoria que no envía
peticiones al backend. No autentica usuarios ni habilita la función oficial.
Permite reproducir la revisión de escritorio/tablet/móvil sin datos reales.

## Validación previa a la activación — 2026-10-15

- Rama `feat/complete-care-context`, HEAD
  `3646b6bd7689d7f49941a8254ec327c3eda5682e`, sin cambios de rama/commit.
- Current/head inicial: `0057_clinical_draft_identity`.
- Current final oficial: `0057_clinical_draft_identity`; única cabeza del código:
  `0058_patient_safety`. Tabla nueva ausente y cero permisos `patient_safety:*`
  en la base oficial; target de arranque confirmado en 0057.
- Backend focal `tests/test_patient_safety.py`: **24 passed**.
- Backend completo `python -m pytest -q`: **492 passed / 29 skipped / 0 failed**,
  10481 warnings, 672.45 s. Los skips son suites históricas de PostgreSQL y
  concurrencia opt-in; no son pruebas Safety V1 omitidas.
- Frontend focal Safety + Patients: **60 passed** (12 Safety + 48 Patients).
- Frontend completo: **419 passed / 0 skipped / 0 failed**.
- Build frontend, Python compile, `docker compose config --quiet` y
  `git diff --check`: **PASS**.
- PostgreSQL temporal real: **0057 → 0058 → 0057 → 0058 PASS**. Huellas y conteos
  idénticos de 2 pacientes, 1 cita, 2 historias, 1 evaluación preoperatoria y 1
  examen físico sintéticos. 5 FKs, 6 checks, 2 índices; 9 escrituras inválidas
  rechazadas. Aislamiento y auditoría comprobados; downgrade poblado bloqueado.
- Revisión visual del componente con fixture sintética: 1440, 768 y 390 px;
  sin overflow horizontal, modal read-first y guardado en memoria verificado.
  No equivale a una activación/smoke con datos oficiales de 0058.
- PostgreSQL QA `atlas-0058-safety-qa-20261015101617` y su volumen anónimo
  eliminados; validator `--rm` eliminado; no se creó red adicional. La pestaña
  QA se cerró y se restauró el viewport. Se conservó la pestaña oficial.
- Instancia oficial: PostgreSQL healthy, backend `/api/v1/health` en 8001 y
  frontend 5174 HTTP 200; sin firmas de errores SQL/startup en logs revisados.

Warnings: deprecaciones de `datetime.utcnow`, AnyIO/Starlette y ReportLab;
advertencias de claves duplicadas en pruebas de AgendaMiniCalendar (área no
modificada), bundle principal aproximado de 660 kB y aviso CRLF de un archivo
de Agenda con cambios previos. No se corrigieron áreas ajenas a esta microfase.

En esa validación quedó pendiente la activación controlada oficial 0058 y binding
clínico futuro. El informe de activación posterior actualiza el estado operativo.
Durante la implementación no se modificaron datos clínicos oficiales, formularios ni PDFs.
Sin commit, push o deploy.
