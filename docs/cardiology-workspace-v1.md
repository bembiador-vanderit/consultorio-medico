# 0061 — Workspace cardiológico V1 (6C2B)

## Alcance y activación

Implementación preparada sobre `0060_clinical_sharing`; nueva revisión única
`0061_cardiology_workspace`. Esta fase **no aplica 0061 a la base oficial**.
La composición se habilita cuando el contexto tiene especialidad con código
estable `cardiology` y existe el esquema 0061. No depende del nombre del médico.
Mientras la base permanezca en 0060, continúa la composición previa y la nueva
bandeja estructurada se declara no disponible, sin consultar tablas inexistentes.

La reanudación no reconstruyó el trabajo anterior. Corrigió los contratos de
navegación de secretaría y la fixture PostgreSQL para reutilizar la especialidad
Cardiología ya sembrada. Añadió cobertura explícita de sharing y evidencia visual.

## Contexto canónico y datos

En la arquitectura actual, el episodio real es `ClinicalHistory` vinculado a una
`Appointment`. `CareContext.tsx` configura centros/especialidades y no es una
entidad de encuentro clínico. Se reutiliza el episodio existente: no se crean
otro paciente, otra consulta ni una agenda paralela.

| Dato | Fuente de verdad |
| --- | --- |
| Paciente, médico, centro, fecha y especialidad | Cita e historia canónicas |
| Motivo administrativo original | `Appointment.reason`, no se sobrescribe |
| Motivo clínico, enfermedad actual, medicamentos revisados y narrativa | Campos existentes de `ClinicalHistory` |
| Alergias, reacciones y alertas longitudinales | Patient Safety Profile existente |
| Signos vitales y presión sistólica/diastólica | `VitalSigns` existente |
| Diagnósticos | Catálogo CIE-10 y `Diagnosis` existentes |
| Recetas, órdenes y documentos | Módulos y permisos existentes |
| Síntomas, antecedentes cardiovasculares, examen, impresión, plan y estudios revisados | `CardiologyAssessment`, una por historia |
| Continuidad médico–paciente | `PatientCareRelationship` 0059 |

Los síntomas y antecedentes permiten `present=true/false/null` y detalle opcional.
No responder no equivale a negar un síntoma. El examen combina hallazgos breves;
frecuencia cardíaca y TA se registran solo en Signos vitales. Los antecedentes
estructurados están preparados para un futuro enlace a Problem List, pero no
constituyen todavía una lista longitudinal de problemas.

No hay un catálogo nuevo de medicamentos activos. Se reutiliza la lista narrativa
revisada por el médico y el módulo de Recetas. Una receta antigua no se interpreta
automáticamente como tratamiento activo.

## Signos y observaciones reutilizables

`clinical_observations.vital_observations()` es un adaptador de lectura genérico
sobre `VitalSigns`: TA sistólica/diastólica, FC, FR, SatO2, peso y talla conservan
valor, unidad, fuente, ID, historia y fecha de observación. No duplica persistencia
ni restringe esos datos a Cardiología. IMC conserva su cálculo existente a partir
de peso y talla. La API longitudinal de tendencias queda para otra fase.

## Flujo médico

1. Abrir la consulta mediante el flujo existente de una cita autorizada.
2. Revisar cabecera y seguridad clínica.
3. Registrar motivo e historia, diferenciados del motivo administrativo.
4. Usar las secciones Historia, Síntomas, Antecedentes, Examen, Plan y Seguimiento.
5. Reutilizar Signos vitales, Diagnósticos CIE-10, Recetas, Órdenes y Documentos.
6. Guardar narrativa y evaluación. Los cambios pendientes participan en la guarda
   existente de navegación/finalización; un error no descarta la captura local.
7. Finalizar explícitamente mediante el cierre existente de la consulta.

`CardiologyAssessment.revision` y el bloqueo de su historia padre serializan las
escrituras. Una revisión obsoleta responde 409. Los estados clínicos siguen siendo
`in_progress` y `completed`; no se inventa una segunda firma. Después del cierre,
no se permite edición ordinaria destructiva.

## Estudios

Categorías V1: ECG, ecocardiograma, Holter, MAPA, laboratorio, radiografía, prueba
de esfuerzo y otros. Cada referencia indica revisado, solicitado o pendiente,
con observación y vínculo opcional a `StudyOrder`. El backend valida que una
orden referenciada pertenezca a la misma consulta. Registrar una referencia como
solicitada **no emite una orden formal**: esa acción sigue en Órdenes clínicas.
No hay integración con equipos, PACS ni resultados automáticos.

## Seguimiento estructurado sin segundo sistema de tareas

La indicación se guarda en la evaluación y solo al completar la consulta se crea
el `FollowUp` existente, con una extensión `ClinicalFollowUpPlan` única por tarea
y por historia. Todo ocurre en la misma transacción que el cierre y la actualización
de PatientCareRelationship. Un rollback no deja una tarea ni una relación parcial.

Opciones: ninguno, días, semanas, meses, cuando tenga estudios o fecha específica.
Se conserva motivo y condición/documentos previos al retorno. La fecha parte de
`consultation_date`; los meses respetan calendario y el último día válido del mes.
Para estudios sin fecha, `due_at=NULL`: no se inventa fecha ni hora.

Estados operativos: `pending`, `contacted`, `scheduled`, `completed`, `cancelled`.
Los seguimientos manuales previos continúan en su flujo existente; las tareas
estructuradas se presentan una sola vez en la nueva bandeja.

### Secretaría y Agenda

La bandeja exige permisos efectivos `patients:view` y `patients:access`, centro
asignado y alcance real de secretaría sobre el médico en ese centro. El médico
responsable además requiere `clinical:access`. No se concede acceso clínico por
mostrar una tarea; un administrador no obtiene acceso clínico implícito.

Los contactos se agregan a `FollowUpContactAttempt`, sin API de edición/borrado:
contactado, no respondió, reintentar, estudios realizados, estudios pendientes,
no desea agendar y cita agendada. Conservan actor, fecha y nota. No modifican
diagnósticos, plan, evolución ni la indicación original.

**Agendar cita** abre el `AppointmentForm` real con paciente, médico, centro y
especialidad. `follow_up_id` se valida en backend y el vínculo/status `scheduled`
se confirma en la misma transacción que crea la cita. Se mantienen validaciones
de modalidad, disponibilidad, conflictos, tenant y permisos. Un segundo vínculo
o un contexto distinto se rechaza; no se cambia la numeración de turnos.

El médico responsable puede completar la tarea solo cuando la cita vinculada
tiene una historia de retorno completada y coinciden paciente, médico y centro.
No se intenta correlacionar automáticamente por nombre o proximidad de fechas.
La ruta antigua `/follow-ups/{id}/complete` delega las mismas validaciones y
devuelve el modelo `FollowUpRead` que ya prometía. La prueba de compatibilidad
detectó y corrigió un `ResponseValidationError` al devolver antes el DTO operativo;
no se relajaron permisos ni requisitos clínicos de cierre.

## API añadida

- `GET/PUT /clinical-history/{id}/cardiology`
- `GET /follow-ups/inbox` (filtro opcional `status`)
- `GET/POST /follow-ups/operational/{id}/contacts`
- `POST /follow-ups/operational/{id}/complete`
- Creación existente `POST /appointments`, con `follow_up_id` opcional.

Prefijo habitual `/api/v1`. El contexto de consulta expone `cardiology_enabled`;
la decisión de autorización sigue en backend, no en la composición visual.

## Seguridad, lectura compartida y auditoría

La escritura utiliza `require_history_access(write=True)`: médico responsable,
centro y contexto válidos, historia abierta, bloqueo del padre y tenant activo.
El DTO de seguimiento contiene solo los datos operativos necesarios.

La política 0060 no cambia: la proyección de historia compartida añade los campos
cardiológicos autorizados y sigue siendo `read_only`. No usa esa concesión para
autorizar endpoints de escritura. Relación asistencial no equivale a acceso
clínico, ni a responsabilidad automática sobre otro episodio.

Se reutiliza `clinical_audit_logs`: creación/edición de historia, signos,
diagnósticos, recetas y órdenes conservan sus eventos; se añaden `cardiology.save`,
`follow_up.indicated`, `follow_up.contact`, `follow_up.appointment_linked` y
`follow_up.completed`. Contextos técnicos con IDs/revisión/resultado, sin copiar
narrativa sensible. Leer no genera un evento de modificación; sharing conserva
su auditoría diferenciada de lectura.

## Migración y validación temporal

0061 crea tres tablas aditivas con FKs, índices por organización/contexto,
unicidad de evaluación por historia y plan por historia/tarea, y checks de revisión,
tipo, intervalo y resultado del contacto. `FollowUp.due_at` pasa a nullable para
el retorno condicionado por estudios. No cambia datos históricos ni siembra tareas.

El downgrade se niega a descartar datos de las tablas nuevas o seguimientos sin
fecha: exige reconciliación explícita. El roundtrip se prueba vacío sobre las
tablas nuevas y conserva datos sintéticos previos, nunca en la base oficial.

`tests/validate_cardiology_postgres.py` rechaza hosts/bases que no sean temporales
0061. Reutiliza exactamente una especialidad `cardiology`; si el catálogo no es
único, falla. Preserva huellas de 87 tablas durante `0060 → 0061 → 0060 → 0061`.
En PostgreSQL real, guardado concurrente y cierre concurrente resultan `200/409`,
con una evaluación, una tarea, una relación y un evento de indicación.

## Validación visual y límites

Fixture DEV `tests/fixtures/cardiology-preview.html`, con interceptación de todas
las peticiones y datos sintéticos, sin usar sesiones ni datos oficiales. Se revisan
escritorio 1440 px y móvil 390 px, navegación por teclado, Safety visible, captura
por secciones, consulta completada y contactos de secretaría. Las capturas y logs
de ejecución se guardan fuera del repositorio en `<LOCAL_EVIDENCE_DIR>`.

Deudas explícitas: API longitudinal de observaciones/tendencias; Problem List;
reconciliación de medicamentos activos; selección visual del vínculo opcional a
órdenes/resultados; enriquecimiento futuro de la proyección compartida de estudios;
mejoras de trazabilidad granular de cambios; carga paginada de la bandeja a gran
escala; corrección explícita del vínculo si se cancela una cita de retorno;
mensajería interna futura (sin WhatsApp/SMS/chat en V1). Las enmiendas existentes
append-only no se amplían a una edición estructurada de la evaluación cerrada.

No se construyen Emergencia, Hospitalización, integración Holter/MAPA ni un sistema
paralelo de prescripción/agenda. La activación oficial 0061 requiere otra tarea con
backup y autorización; no forma parte de este cierre.

## Evidencia de reanudación — 16/10/2026

- Branch `feat/complete-care-context`, HEAD
  `3646b6bd7689d7f49941a8254ec327c3eda5682e`.
- Current oficial inicial: `0060_clinical_sharing`; head único del código:
  `0061_cardiology_workspace`.
- Frontend focal (Cardiology, App Shell y Foundation): **39/39**.
- Frontend completo: **458 passed / 0 skipped / 0 failed**.
- Build frontend, Python compile y Compose config: PASS.
- Regresión clínica/sharing/PatientCare: **124 passed**, sin fallos.
- Backend focal final: **28 passed**. Backend completo final: **581 passed /
  29 skipped / 0 failed**, 12 858 warnings, 790,22 s. Resultado recuperable en
  `backend-full-final.log`, fuera del repositorio.
- PostgreSQL temporal: roundtrip, 87 huellas y constraints PASS; carreras de
  evaluación y cierre `200/409`, una sola tarea y relación.
- Fixture visual: escritorio 1440 px y móvil 390 px sin overflow; alerta Safety,
  modal de seguridad de solo lectura y contactos de secretaría legibles. Tab
  avanza Sí → No. Consulta completada: cero controles clínicos habilitados,
  contando también `fieldset:disabled`.
- Datos oficiales comprobados: pacientes 18, citas 44, historias 19, preoperatorias
  13, exámenes físicos 4, entradas Safety 2, relaciones 2, política sharing 1.
  Sin tablas 0061 en la base oficial.

La suite backend final se ejecuta sobre una copia de `app`, `tests` y Alembic en
`/tmp/atlas-0061-validation-final` del mismo contenedor e imagen de dependencias,
para evitar la latencia de acceso repetido al bind mount Windows. No se copia ni
se restaura la base oficial. Sus fixtures siguen usando datos sintéticos aislados.
La copia y sus logs son temporales y se eliminan después de recoger resultados.

Warnings conocidos a informar: deprecaciones `datetime.utcnow`, AnyIO/ReportLab,
avisos de claves repetidas en fixtures de calendario y bundle JS mayor de 500 kB.
La advertencia Git LF/CRLF de `AgendaMonthPanel.tsx` es previa y no es error de
`diff --check`.

Los 29 skips son pruebas que requieren seleccionar expresamente su PostgreSQL
desechable: administración (2), ARS (1), concurrencia clínica (5), identidad de
borradores (1), finanzas (5), seguros (2), identidad de paciente (5), pausas (1),
orden de agenda (1), política de llamadas (2), Queue V2 (2), Queue V3 (1) y salas
de espera (1). No se presentan como ejecutadas. El roundtrip y las dos carreras
PostgreSQL **propias de 0061 sí se ejecutaron aparte y pasaron**, sin skips.

### Cierre

`RESULT=PASS` para implementación y validación, **no activación oficial**.
Current final oficial `0060_clinical_sharing`, head único `0061_cardiology_workspace`.
Los conteos de la validación histórica permanecieron iguales y no existía la tabla de
evaluaciones cardiológicas en esa base. Los servicios respondieron correctamente;
sin errores SQL/startup en la ventana final revisada.

Se eliminaron el contenedor y la red QA 0061, sin volumen persistente (PostgreSQL
usó tmpfs), así como la copia de código de prueba en `/tmp` tras exportar su log.
Inventarios Docker por etiqueta QA vacíos. Se preservaron el volumen oficial,
backups y otros proyectos. No se creó 0062; no commit, push ni deploy.
