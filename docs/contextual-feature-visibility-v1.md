# Visibilidad contextual de capacidades V1 — 0062

## Regla arquitectónica

**FEATURE ≠ VISIBILITY ≠ PERMISSION ≠ ENTITLEMENT.**

- Feature: capacidad técnica existente.
- Visibility: composición visual en una interfaz/contexto para una audiencia.
- Permission: autorización real para leer/modificar un recurso concreto.
- Entitlement: contratación comercial futura; **no implementada** en esta fase.

El resolver de visibilidad nunca participa en las decisiones de autorización de
Safety, Shared Access, pacientes, consultas o documentos. Ocultar no revoca un
permiso y mostrar no lo concede. Las APIs de Safety y Sharing permanecen intactas.
La existencia de una relación asistencial tampoco concede acceso clínico.

## Inspección y arquitectura reutilizada

Rama `feat/complete-care-context`, HEAD inicial
`3646b6bd7689d7f49941a8254ec327c3eda5682e`. Current/head iniciales:
`0061_cardiology_workspace`.

Se reutilizan `TenantOwned`, la frontera de sesión SQLAlchemy por organización,
las membresías y roles efectivos, `users:manage`, la reautenticación administrativa,
`ClinicalAuditLog`, la página Seguridad y administración, los controles UI Atlas,
PatientSafetyProfile y el gateway de lectura compartida 0060. No existía un
almacén genérico de visibilidad; las flags Vite previas son controles de entrega,
no configuración contextual modificable por una organización.

`CareContext` actual es un directorio de atención/configuración, no un episodio
ni un enum de contexto operativo. No se reutiliza como si fuera Emergencia.

## Modelo y revisión

Revisión nueva: **`0062_feature_visibility`**, padre
`0061_cardiology_workspace`. Solo crea `feature_visibility_settings`:

- organization_id obligatorio;
- center_id opcional;
- feature_code, context_code, audience;
- visibility_mode: `hidden` o `visible`;
- revision, actor actualizado, motivo, created_at y updated_at.

FK a organización, centro y usuario; check de modo y revisión positiva; índice
por organización; dos índices únicos parciales PostgreSQL que manejan NULL:

1. organización + feature + contexto + audiencia cuando center_id IS NULL;
2. organización + centro + feature + contexto + audiencia cuando center_id IS NOT NULL.

No seeds, backfill, cambios de permisos ni cambios a registros clínicos. El
downgrade se niega si hay configuración guardada, para no descartarla sin una
preservación explícita. El roundtrip de validación usa únicamente la base temporal.

## Registro de códigos y defaults

V1 acepta exclusivamente:

| Feature | Contexto | Médicos | Secretarías |
| --- | --- | --- | --- |
| clinical_safety_full | ambulatory | hidden | hidden |
| clinical_safety_critical_alert | ambulatory | hidden | hidden |

El modelo admite evolución mediante códigos estables. El registro central rechaza
por API features/contextos/audiencias no implementados, en vez de mostrar módulos
vacíos o aceptar códigos arbitrarios del navegador.

Audiencia resuelta por servidor desde `User.roles` de la membresía activa:
doctor → doctor; secretary → secretary; admin → administrator; otros →
other_clinical. En cuentas mixtas se prioriza doctor sobre secretaria y admin.
V1 permite configurar solo doctor y secretary. No se confía en una audiencia
declarada por el cliente. Administrator no recibe permisos clínicos por esta pieza.

Futuras audiencias nurse/other_clinical y futuros contextos emergency/inpatient
requieren integración explícita. La intención futura para estos dos contextos es
Safety completo y alerta visibles, siempre sujetos a autorización; **hoy no se
aceptan ni se crean pantallas o flujos para ellos**.

Los nombres advanced_followup, internal_messaging, emergency_module,
inpatient_module y advanced_analytics son únicamente contratos de extensión
documentados: no capacidades comercialmente habilitadas ni entradas de navegación.

## Resolución y ámbito por centro

Precedencia: **center override → organization setting → system default**.

El contexto cardiológico entrega el center_id real de su cita. La ficha general
del paciente no inventa un centro a partir de sus médicos o de una cita histórica:
sin centro activo canónico usa organización/default. Cuando exista contexto global
de centro podrá pasarse por el mismo contrato, sin crear otro almacén.

La API valida que el centro sea activo, de la organización actual y esté en el
alcance del usuario; un administrador tenant usa su alcance administrativo actual.
No existe sharing entre organizaciones.

## Endpoints

- `GET /api/v1/feature-visibility/resolved?context_code=ambulatory&center_id=...`:
  metadatos de presentación del usuario autenticado, sin información clínica.
- `GET /api/v1/feature-visibility/settings?center_id=...`: configuración efectiva
  y local, revisiones y centros de la organización; administración autorizada.
- `PUT /api/v1/feature-visibility/settings?center_id=...`: cambios por clave,
  revisión esperada y motivo. Requiere admin tenant, permiso efectivo
  `users:manage` y reautenticación existente (428 si falta).

Un valor null en PUT elimina solo el override actual y retoma herencia. No es un
tercer modo de visibilidad. La acción queda auditada, incluidos before/after.
El bloqueo estable de la fila Organization serializa inserción inicial, cambios
y restauración de herencia. Una revisión obsoleta responde 409. No-op no genera
una modificación auditada ficticia.

### Trazabilidad de revisión en auditoría

`feature_visibility.updated` reutiliza `ClinicalAuditLog`: actor (`user_id`),
organización, centro opcional, recurso y timestamp permanecen en las columnas
existentes. Su `context` JSON conserva feature, audiencia, contexto operativo,
before, after y motivo, y añade:

- `previous_revision`: revisión local previa al cambio (0 si no existía fila).
- `revision`: revisión local resultante, la misma que devuelve la configuración
  persistida. Crear produce 1; actualizar incrementa la revisión existente.

Al eliminar un override, `revision` es 0 porque ya no existe configuración local;
`previous_revision` conserva la revisión eliminada. No representa la revisión de
la configuración heredada ni un contador global monotónico entre eliminaciones
y recreaciones. Ejemplo de creación, actualización y eliminación: 0→1, 1→2, 2→0.

Los metadatos se capturan dentro de la misma transacción que modifica la
configuración, no se reconstruyen consultando su estado posterior. Lecturas,
no-op y conflictos 409 no generan auditoría de modificación exitosa; un batch
rechazado revierte también cualquier auditoría pendiente de cambios anteriores.
No requiere cambio de esquema ni modificación de la migración 0062.

## UI administrativa y clínica

Seguridad y administración → **Visibilidad de funciones clínicas**:

- contexto Consulta ambulatoria;
- toda la organización o centro específico;
- Panel completo: Médicos / Secretarías;
- Alertas críticas: Médicos / Secretarías;
- motivo obligatorio, Guardar visibilidad, Heredar organización o Restablecer
  predeterminados.

No se muestran precios, planes, pagos, módulos futuros ni suscripciones.

El wrapper `ContextualSafetyProfile` se utiliza en Cardiología y Pacientes:

- full hidden + critical hidden: no renderiza Safety ni consulta su contenido;
- full hidden + critical visible: solo advertencia compacta si hay alergia
  grave/crítica activa y la lectura está autorizada; no expone agente, reacción,
  observaciones ni edición;
- full visible: reutiliza panel/modal original, con todos sus controles de
  autorización y edición; los banners críticos siguen el switch independiente.

Secretaría conserva las restricciones clínicas actuales. Su checkbox puede estar
visible y aun así no aparecer Safety porque **no existe autorización para leerlo**.
No se amplió la semántica de Safety para hacer que ese checkbox otorgue acceso.

La UI compartida 0060 filtra Safety según visibilidad sin tocar policy ni permisos.
Cuando solo la alerta compacta compartida está visible, lee por el gateway 0060
autorizado y auditado; recorre páginas si es necesario, sin renderizar detalles.
Historia y documentos compartidos no se ocultan por un switch de Safety.

## Actualización y cache

Sin cache servidor: cada resolución consulta la configuración vigente. Las
respuestas usan `Cache-Control: no-store`. El hook vuelve a resolver al montar,
cambiar organización/rol/centro/contexto, recuperar foco o visibilidad de pestaña,
recibir un guardado administrativo y cada 60 segundos mientras la pestaña está
visible. Una respuesta vieja no reemplaza otra más reciente.

La identidad de contexto evita mostrar por un render una decisión de otro centro.
Al ocultar el panel se desmonta el detalle abierto. Ante error del resolver se
aplican defaults hidden, no se infieren permisos desde una UI anterior.

## Auditoría y datos

`feature_visibility.updated` en ClinicalAuditLog existente contiene actor,
organización, centro, feature, contexto, audiencia, before/after, motivo y hora.
Leer configuración no genera auditoría de modificación. La lectura compartida
sigue su auditoría 0060; no se copia a otro sistema.

Los datos de Safety, Clinical Forms, relaciones asistenciales, Sharing y
Cardiología/seguimientos no son editados por esta infraestructura.

## Activación y convivencia con 0061

**La nueva migración NO se aplica a la base oficial en esta microfase.**
El pin de arranque local sigue siendo 0061. Con esquema 0061, el resolver devuelve
los defaults hidden sin consultar una tabla inexistente. Administración indica
pendiente de activación y no permite guardar; un PUT directo responde 503.

Cambiar la configuración sin restart/deploy funciona después de activar 0062 en
una tarea oficial separada. Aquí se verificó con persistencia temporal y la UI
aislada. No se presenta la fixture como una configuración oficial guardada.

## Validación — 16/10/2026

- Backend focal: **95 passed**, 2507 warnings (visibilidad, Safety, Sharing,
  Cardiología).
- Backend completo: **599 passed / 29 skipped / 0 failed**, 13263 warnings,
  1028,25 segundos. Ejecutado sobre copia temporal del código con fixtures
  aisladas, no sobre datos oficiales; log completo exportado fuera del repositorio.
- Frontend focal: **55/55** (visibilidad/Safety/Sharing/Cardiología) y **65/65**
  (visibilidad/Pacientes); grupos con solapamiento, no se suman.
- Frontend completo final: **475 passed / 0 skipped / 0 failed**.
- Primera ejecución completa frontend: siete expectativas antiguas de dos
  peticiones fallaron por la nueva consulta de metadatos. Se actualizó la fixture
  y ahora se exigen los tres endpoints concretos sin permitir peticiones clínicas
  adicionales; la segunda ejecución completa pasa.
- Build TypeScript/Vite: PASS, 201 módulos; aviso de bundle principal >500 kB.
- Python compile, Compose config y diff check: PASS.
- PostgreSQL temporal real: **0061 → 0062 → 0061 → 0062 PASS**; **90 huellas
  previas idénticas**, incluyendo documentos, Safety, Sharing, Cardiología,
  seguimientos, relaciones y auditorías. FK e índices parciales verificados;
  cuatro rechazos por constraints/duplicados. Dos guardados de servicio
  concurrentes: **200/409**, una sola configuración y un evento auditado.
- Puerto temporal 15462, base atlas_0062_qa, contenedor/red etiquetados 0062,
  almacenamiento tmpfs sin volumen oficial. Runner y PostgreSQL retirados;
  red retirada; inventarios por etiqueta vacíos.
- Smoke real de componentes en fixture DEV con todas las peticiones interceptadas:
  A hidden, B solo alerta, C full visible, volver a hidden, Pacientes y secretaría
  sin permiso, desktop 1440 px y móvil 390 px sin overflow. No se usó la sesión
  oficial ni se modificaron datos/políticas oficiales para este smoke.
- Base oficial comprobada nuevamente: **0061_cardiology_workspace**, 90 tablas
  con idénticos conteos y huellas frente al precheck, sin tabla 0062.
- Evidencia externa en `<LOCAL_EVIDENCE_DIR>`.

Los 29 skips requieren otras bases PostgreSQL desechables explícitas:
administración 2, ARS 1, concurrencia clínica 5, identidad de borradores 1,
finanzas 5, seguros 2, identidad de paciente 5, pausas 1, orden de agenda 1,
política de llamadas 2, Queue V2 2, Queue V3 1 y salas de espera 1. No se consideran
ejecutados por la suite general. La validación PostgreSQL propia de 0062 sí pasó.

Warnings no bloqueantes: deprecaciones anteriores `datetime.utcnow` y dependencias,
bundle principal de 693,59 kB (>500 kB) y aviso Git LF/CRLF previo de
AgendaMonthPanel.tsx. `git diff --check` termina sin errores.

## Límites y deudas explícitas

- Contexto global de centro todavía no existe: no se crea en login ni se infiere.
- Audiencias futuras y contextos no ambulatorios no se habilitan en V1.
- No hay entitlements, suscripciones, pagos, mensajería ni módulos hospitalarios.
- La revisión de visibilidad no es una barrera de seguridad ni sustituye permisos.
- Se conservan las deudas clínicas anteriores, sin rediseñar formularios ni
  ampliar enmiendas posteriores a firma.

No commit, push, deploy, downgrade ni nueva migración aplicada oficialmente.

## Cierre

**RESULT=PASS para implementación + validación temporal.**

Current oficial inicial/final: **0061_cardiology_workspace**. Head de código final:
**0062_feature_visibility**, una sola cabeza. El pin local de arranque se conserva
en 0061; no se habilitó guardar configuración oficial 0062. Las 90 tablas oficiales
mantienen exactamente los mismos conteos y huellas del precheck.

PostgreSQL oficial healthy, health API 8001, `/docs` y frontend 5174 HTTP 200.
Sin nuevos errores SQL/startup asociados a esta fase en los logs revisados. Sin
recursos Docker QA 0062 restantes; copia temporal de pruebas retirada tras exportar
el log. La pestaña de fixture se cerró y se restauró el viewport, conservando la
pestaña/sesión original del usuario.

NO entitlements, NO suscripciones, NO pagos, NO commit, NO push, NO deploy.
DETENERSE.

## Microfix audit revision trace — 16/10/2026

RESULT=PASS. Cambio limitado al snapshot JSON del servicio, sus pruebas y esta
documentación. Sin cambios frontend, de modelo o de migración. No se activó 0062.

- Backend focal: **21 passed**, 498 warnings.
- Backend completo repetido: **602 passed / 29 skipped / 0 failed**,
  13354 warnings, 848,48 segundos. Los 29 skips siguen requiriendo otras bases
  PostgreSQL desechables explícitas; no se presentan como pruebas ejecutadas.
- Frontend focal: **17/17**. Frontend completo: **475/475**, sin skips ni fallos.
- Build frontend: PASS; se conserva el aviso de bundle principal >500 kB.
- Python compile, Compose config y git diff --check: PASS. Se conserva el aviso
  LF/CRLF anterior de AgendaMonthPanel.tsx, no un error de diff.
- PostgreSQL real temporal: **0061 → 0062 → 0061 → 0062 PASS**, cuatro rechazos
  por constraints y 90 huellas históricas preservadas, incluyendo auditorías
  anteriores. Se añaden únicamente las auditorías sintéticas del escenario.
- Concurrencia de guardado: **200/409**, una configuración y una sola auditoría
  del cambio ganador, `revision=1` igual a la fila persistida. Lectura, no-op y
  stale write no añaden auditorías. Actualización/eliminación conservan la traza
  `(previous_revision, revision)`: **(0,1), (1,2), (2,0)**. Un batch con conflicto
  revierte también los cambios y auditorías pendientes anteriores.
- Base oficial inicial/final: **0061_cardiology_workspace**; head del código:
  **0062_feature_visibility**. Las 90 tablas oficiales conservan conteos y huellas.
  PostgreSQL healthy; API health, docs y frontend HTTP 200.
- Contenedor y red temporales `atlas-0062-visibility-qa-audit-*` retirados;
  almacenamiento tmpfs, sin volumen persistente ni uso del volumen oficial.
  Log de pytest exportado fuera del repositorio antes de retirar su copia temporal.
- Evidencia: `<LOCAL_EVIDENCE_DIR>` (logs y snapshot de
  preservación oficial). No 0063; no upgrade/downgrade oficial, commit, push o deploy.

## Continuación y cierre preactivación — 16/10/2026

Esta revisión reutiliza la implementación y el microfix anteriores: no reconstruye
0062, no cambia lógica ni UX, no repite el ajuste de auditoría y no activa la base.
Solo se amplía este registro de validación. Rama `feat/complete-care-context`, HEAD
`3646b6bd7689d7f49941a8254ec327c3eda5682e`; current oficial inicial:
`0061_cardiology_workspace`; head de código: `0062_feature_visibility`.

### Contratos confirmados

- **FEATURE ≠ VISIBILITY ≠ PERMISSION ≠ ENTITLEMENT.** No integración comercial.
  Una integración comercial futura deberá resolver entitlements por separado;
  no reinterpretará estos switches como contratación ni como autorización RBAC.
- Registro V1: `clinical_safety_full` y `clinical_safety_critical_alert`;
  contexto real `ambulatory`; audiencias configurables `doctor` y `secretary`.
  Se resuelven mediante códigos RBAC estables y membresía efectiva, no por nombres
  visibles de personas, médicos o centros. Emergency/Inpatient no se implementan.
- Ambos switches tienen default hidden para ambas audiencias. El resolver central
  conserva **centro > organización > default**; eliminar override retoma herencia.
  Tenant y centro se validan; no se modifican permisos ni política Sharing 0060.
- Administración conserva cuatro switches, ámbito organización/centro, motivo y
  revisión esperada. Requiere administración autorizada, `users:manage` y la
  reautenticación existente; configurar visibilidad no concede acceso clínico.
- Auditoría existente comprobada, no rehecha: actor, organización, centro opcional,
  feature, contexto, audiencia, before/after, motivo, timestamp,
  `previous_revision` y `revision` resultante local. Al eliminar la fila, revisión
  local 0; no es la revisión heredada. Lecturas/no-op/409 no crean modificaciones.
- Refresh por montaje, cambio de ámbito/identidad, foco, evento de guardado y
  reevaluación periódica; API sin cache. No requiere logout, restart o deploy.
- Patient page y Cardiología usan la misma integración contextual. Shared Access
  sigue autorizando y auditando lecturas por el gateway 0060, aunque Safety esté
  oculto en la UI. La alerta compacta no muestra agente/reacción ni ofrece bypass.
- Seguimientos/contactos, Agenda, relaciones asistenciales, documentos e historias
  no cambian. La regresión focal de Cardiología incluye bandeja/contactos y el
  agendamiento de retorno existente; las suites completas cubren el resto.

### Smoke visual repetido sin activar la base oficial

Se usó la fixture DEV existente `tests/fixtures/feature-visibility-preview.html`
con **componentes reales y todas las peticiones interceptadas por un adapter
sintético**. Sus guardados son exclusivamente en memoria; no prueban por sí solos
la persistencia o auditoría del backend, verificadas separadamente en las pruebas
y PostgreSQL. La sesión oficial estaba vencida y no se manipuló su autenticación.
No se presenta este smoke como una sesión administrativa oficial con 0062 activa.

- Desktop 1440×1000: administración; A ambos hidden; B solo alerta crítica;
  C full visible y modal de Safety autorizado en solo lectura.
- Móvil 390×844: A/B/C, administración, modal Safety y ficha Patient. Ancho del
  documento no supera el viewport; modal Safety de 352 px con scroll interno;
  labels de switches con área táctil de 44 px. Sin overflow horizontal observado.
- Secretarías: aun marcando ambos switches visible en la fixture, la cuenta
  sintética sin permiso clínico no muestra panel/alerta ni contenido Safety.
- Ficha médica conserva Historia clínica; ficha de secretaría no añade esa acción.
  Plan, estudios y seguimiento cardiológico continúan navegables en móvil.
- Tablet 768×1024: administración legible y sin overflow. Se reinició la fixture
  para descartar ajustes en memoria, se cerró su pestaña y se restauró el viewport;
  se conservó la pestaña original del usuario.

### Validación técnica repetida

- Backend focal (visibilidad, Safety, Sharing, Cardiología): **98 passed**,
  2598 warnings.
- Backend completo repetido: **602 passed / 29 skipped / 0 failed**,
  **13354 warnings**, 972,40 segundos. Los skips requieren bases PostgreSQL
  desechables específicas de otras fases, detalladas más arriba y en el log;
  la concurrencia PostgreSQL propia de 0062 sí fue ejecutada y pasó.
- Frontend focal de las mismas áreas: **55 passed / 0 failed / 0 skipped**.
- Frontend completo: **475 passed / 0 failed / 0 skipped**.
- Build TypeScript/Vite: PASS, 201 módulos; aviso previo de bundle >500 kB.
- Python compile, Compose config y git diff --check: PASS; aviso LF/CRLF anterior.
- PostgreSQL real temporal repetido: **0061 → 0062 → 0061 → 0062 PASS**;
  90 huellas preservadas; cuatro rechazos por constraints/duplicados; FK e índices
  únicos parciales comprobados. Guardados concurrentes **200/409**, una auditoría
  efectiva; revisión persistida y snapshot coinciden. Lectura/no-op/stale sin
  auditoría nueva. Trazas local anterior/resultante: (0,1), (1,2), (2,0).
- PostgreSQL temporal en puerto 15462, base `atlas_0062_qa`, tmpfs y red propios;
  runner/contenedor/red `atlas-0062-visibility-qa-close-*` retirados, sin volumen
  persistente. No se usó la base ni el volumen oficial para pruebas.
- Evidencia externa: `<LOCAL_EVIDENCE_DIR>`.

### Resultado de cierre

**RESULT=PASS para implementación y validación preactivación.**

Current oficial final: **0061_cardiology_workspace**, head único de código:
**0062_feature_visibility**. Las **90 tablas** oficiales conservan exactamente los
conteos y huellas iniciales: Safety, Sharing 0060, Cardiología 0061, seguimientos,
pacientes/citas/historias, relaciones, documentos, plantillas y auditoría histórica
intactos. No se crearon configuraciones ni cuentas QA oficiales.

PostgreSQL oficial healthy; API health 8001, docs y frontend 5174 HTTP 200.
Sin errores SQL/startup detectados en los logs oficiales revisados. Recursos
Docker QA retirados, sin volúmenes persistentes; copia `/tmp/atlas-0062-close-tests`
retirada tras exportar el log completo. Backups existentes conservados.

Se verificaron sin cambios las huellas de 480 archivos de código y pruebas; la
única edición de este cierre es documental. Se conservaron los cambios previos
del workspace. `git diff --check` pasa; advertencias no bloqueantes: deprecaciones
anteriores, bundle principal >500 kB y aviso LF/CRLF previo.

0062 queda lista para una activación oficial posterior y expresamente autorizada;
este cierre no equivale a haberla aplicado ni a haber probado guardados 0062 en
una sesión oficial. No se rehízo el microfix de auditoría.

NO activación 0062, NO 0063, NO entitlements, NO suscripciones, NO pagos,
NO commit, NO push, NO deploy. DETENERSE.

## Activación oficial posterior — 16/10/2026

Las secciones anteriores conservan el resultado histórico de implementación y
cierre previo, sin activación. En una tarea posterior expresamente autorizada
se aplicó `0062_feature_visibility` a la base local oficial, partiendo de 0061.
Backup válido, preservación de datos, roundtrip y concurrencia aislados,
administración real, sesión médica y secretaría: PASS. Los overrides QA fueron
retirados conservando sus auditorías; panel y alerta Safety vuelven a ocultos
por default. No se cambiaron permisos, Sharing ni datos clínicos.

La activación oficial 0062 y sus limitaciones de cobertura visual quedaron en
la evidencia histórica local, fuera del repositorio.
