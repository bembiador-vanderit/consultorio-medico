# Patient Identity & Clinical Demographics

Intervención independiente anterior a Phase 6B9. Base exacta:
`feat/complete-care-context@24d796453a21bdf52d46ef4bffc853010bbfd2a5`.
Rama: `feat/patient-identity-clinical-demographics`. Destino del PR:
`feat/complete-care-context`; sin merge, sin cambios a `main` ni PR #4.

## Auditoría previa

- `Patient` contenía nombre, apellido, nacimiento, `phone`, correo y fecha de alta.
  No había documento, dirección, sexo ni tipo sanguíneo que reutilizar.
- POST/PUT, selección mínima y acceso directo están centralizados en
  `api/routes/patients.py` y `services/patient_scope.py`.
- PR #32 (`5012dfce894b63710745246d6d634c15b75bb078`) preserva el scope administrativo,
  la prueba de selección firmada por usuario/paciente/contexto, los locks por
  nacimiento/contacto y la transacción de identidad/seguro. No se modifica ese
  servicio, la prueba ni las rutas de citas.
- Seguro utiliza afiliaciones; no se añade un campo alternativo en `Patient`.
  Omisión/null conserva, false explícito desactiva y un objeto válido agrega una
  afiliación como antes. Se conserva el manejo frontend de carga fallida.
- `Locality` es un catálogo plano compartido por centros, sin jerarquía provincial.
  Se reutiliza mediante FK nullable; provincia es texto opcional, sin inventar
  un catálogo nacional ni inferir provincia a partir de la localidad.
- Las notas y antecedentes ya pertenecen a la historia clínica: no se crea otra
  fuente de verdad en pacientes. Observaciones generales quedan fuera de alcance.

## Contrato y migración

### Evolución territorial posterior

La migración `0031_country_territory` mantiene `province` y `locality_id` como
legacy y añade, de forma nullable, `country_code`, `territorial_unit_id` y
`sector_locality` a paciente. No reutiliza `Locality`: ese catálogo plano sigue
siendo el de centros de atención. El catálogo nuevo separa `Country`,
`TerritorialLevel`, `TerritorialUnit` y `RegionalSettings`; la unidad territorial
más profunda guarda su padre, por lo que la ficha reconstruye la ruta y usa los
labels del país, sin columnas específicas por geografía.

República Dominicana es el país inicial de operación y propone sus niveles
`Provincia` y `Municipio` a los pacientes nuevos. La migración carga las 32
unidades provinciales y los 158 municipios del corte de la fuente; `Sector /
Localidad` sigue siendo texto libre. La fuente versionada es ONE, *División
Territorial 2020* (edición 2021, consulta 2026-09-20), que describe las unidades
territoriales vigentes de ese corte. Los nombres y relaciones quedan versionados
en la migración para que una publicación posterior de ONE cambie filas del
catálogo, nunca columnas de `Patient`. Un país adicional se incorpora insertando
país, niveles y unidades; Puerto Rico no se declara cargado en esta fase.

`RegionalSettings.default_country_code` es persistente y solo `users:manage`
puede actualizarlo. No determina el país de residencia ni la nacionalidad del
paciente. La API mantiene listados mínimos libres de esos datos; la ficha incluye
país, unidad final y `territorial_path`. Pacientes legacy continúan mostrando
provincia/localidad hasta que se migren manualmente desde Editar.

`0030_patient_demographics`, posterior a `0029_clinical_concurrency`, añade columnas
nullable sin modificar los valores existentes. No almacena edad ni rellena datos
supuestos. La migración no necesita operaciones sobre volúmenes Docker.

| Campo | Decisión |
| --- | --- |
| `document_type`, `document_number` | Cédula (`cedula`), Pasaporte (`passport`), Otro (`other`); par opcional |
| `phone`, `home_phone` | `phone` mantiene nombre/API/datos anteriores y se muestra como celular; casa es independiente |
| `registered_sex` | `female`, `male`, `other`, `unknown` o NULL; sexo registrado para fines clínicos |
| `blood_type` | Ocho valores ABO/Rh; desconocido/sin registrar se representa con NULL |
| `address`, `province`, `locality_id` | Dirección, provincia y FK al catálogo existente |
| `nationality`, `occupation` | Texto opcional y limitado |
| `emergency_contact_*` | Nombre, parentesco, celular y casa opcionales |
| `guardian_*` | Nombre, parentesco, celular y casa opcionales |

PUT conserva los campos nuevos omitidos por clientes antiguos; NULL explícito
limpia el campo. Los campos de identidad anteriores conservan su semántica de
PUT completo. Para cambiar documento se envía el par; limpiar explícitamente
uno de los miembros con NULL (sin otro valor) limpia ambos. La localidad inactiva
existente puede conservarse; una asignación nueva requiere localidad activa.
La UI conserva el ID existente si falla cargar el catálogo.

### Documento y duplicados

La API normaliza Unicode NFKC, mayúsculas y elimina espacios y guiones de formato
(`-`, `‐`, `‑`, `–`, `—`). Conserva el resto de signos; no impone longitud de cédula,
dígito verificador, nacionalidad ni formato dominicano a pasaportes/otros.
Rechaza controles invisibles, valores sin caracteres alfanuméricos, pares incompletos
y números normalizados mayores de 100 caracteres.

Se guarda el número canónico como única fuente. El índice único
`uq_patients_document(document_type, document_number)` admite múltiples NULL;
checks SQL exigen el par completo y enumeraciones válidas. La comprobación previa
da un 409 genérico; el índice resuelve carreras entre altas/ediciones y su error se
traduce al mismo 409 con rollback, sin revelar el paciente coincidente.
El mismo número en tipos diferentes es válido. No se introduce identidad global
por país emisor; nacionalidad no equivale a emisor del documento.

La regla de PR #32 de nacimiento + celular/contacto anterior o correo permanece
vigente, incluidos sus locks. Casa, teléfonos de familiares y tutor no se usan
como identificadores únicos: pueden ser compartidos. No se normalizan teléfonos
con reglas nuevas ni se reparan duplicados históricos.

## Privacidad por superficie

| Respuesta | Información nueva |
| --- | --- |
| GET `/patients`, `/count` | Ninguna; listado conserva el contrato anterior |
| GET `/patients/identity-search` | Ninguna; DOB + contacto exacto, enmascarado y prueba firmada como PR #32 |
| GET `/patients/{id}` | Ficha ampliada, solo bajo scope administrativo existente |
| POST/PUT `/patients` | Ficha ampliada al escritor autorizado; POST mantiene `selection_token` |
| GET `/patients/localities` | Catálogo activo de localidades, bajo `patients:access`, sin identidades |
| Citas, agenda y selección | Sin documento, domicilio, contactos adicionales ni sangre |
| Contexto de consulta | Sangre actual declarada/registrada, después de los controles clínicos existentes |
| Historia clínica autorizada | Nacimiento desde el paciente maestro para calcular edad en la fecha del episodio |

La ficha maestra contiene datos demográficos registrados, también para el personal
administrativo autorizado; esto no concede acceso a episodios clínicos. El contexto
clínico sigue rechazando secretaria, admin sin autorización clínica y médico ajeno,
y conserva las condiciones de cobertura. Documento/dirección no se incorporan a JWT,
logs, PDFs ni a endpoints de selección. Se elimina el `console.error` del formulario
que podía registrar payloads de Axios con identidad.

El listado permite documento **exacto normalizado** dentro del scope ya visible,
además de nombre y teléfonos. No se abre búsqueda global por documento. La ficha
carga el detalle al seleccionar; bloquea edición ante fallo y descarta respuestas
de selecciones anteriores. Una búsqueda o un detalle no sustituyen permisos backend.

## UI y edad

Nuevo/Editar paciente presenta dos secciones lógicas accesibles: Datos personales
(identidad, contacto, domicilio, emergencia, tutor y seguro existente) y Datos
clínicos (sexo registrado y sangre). La ficha muestra los mismos campos. No se
añaden diagnósticos, antecedentes ni personalización programable.

`services/patientAge.ts` trabaja con fechas de calendario, valida fechas imposibles
y rechaza fechas futuras respecto a la referencia. Alta/edición/ficha usan la fecha
local actual. La consulta usa la fecha del formulario, incluso antes de guardar;
la proyección histórica usa `consultation_date`. Nacimiento se lee de `Patient`,
sin duplicarlo ni persistir edad en el episodio.

Presentación pediátrica: días antes del primer mes completo, meses completos antes
de los dos años, luego años. El aniversario de 29 de febrero se cumple el 1 de marzo
en años no bisiestos; meses completos comparan día calendario (31 de enero a 28 de
febrero sigue expresándose en días). No se usa división por 365 ni hora UTC para
decidir un cumpleaños local. Correcciones futuras de nacimiento recalculan edades;
no se crea un snapshot histórico de demografía.

La sangre se etiqueta como declarada/registrada, sin confirmación de laboratorio.
En consulta se explicita **ficha actual** y no se presenta como resultado histórico.

## Archivos por responsabilidad

- Modelo/migración: `backend/app/models/patient.py`, `backend/app/models/regional.py`, migraciones `0030_patient_demographics.py` y `0031_country_territory.py`.
- API/validación: schemas y rutas de pacientes/regional, `services/patient_demographics.py`.
- Proyección clínica: modelo/schema/ruta de historia clínica; autorización sin cambios.
- UI: PatientForm, PatientDemographicFields, PatientDemographicDetails, Patients, CareContext y CSS.
- Edad/contexto: patientAge, AnamnesisModule, ConsultationWorkspace,
  HistoricalConsultationProjection y tipos patient/clinical.
- Pruebas: patient_demographics, patient_identity_concurrency, patient-age,
  patients-ui, patient-selection-contract, consultation-ui e historical-editability.
- Estabilidad de regresiones: `test_clinical_specialties_context.py` fija el reloj
  únicamente en tres casos de transferencia. Los tres fallaban también en el SHA
  base exacto porque su cobertura ficticia del 14–16 de septiembre había vencido.
  Conservan sus aserciones y la política de cobertura de producción sin cambios.
- Documentación: este informe y `patient-visibility-scope.md`.

### Inventario exacto

- `backend/alembic/versions/0030_patient_demographics.py`
- `backend/app/api/routes/clinical_history.py`
- `backend/app/api/routes/patients.py`
- `backend/app/models/clinical_history.py`
- `backend/app/models/patient.py`
- `backend/app/schemas/clinical_history.py`
- `backend/app/schemas/patient.py`
- `backend/app/services/patient_demographics.py`
- `backend/tests/test_clinical_specialties_context.py`
- `backend/tests/test_patient_demographics.py`
- `backend/tests/test_patient_identity_concurrency.py`
- `docs/patient-identity-clinical-demographics.md`
- `docs/patient-visibility-scope.md`
- `frontend/src/components/consultation/AnamnesisModule.tsx`
- `frontend/src/components/consultation/ConsultationWorkspace.tsx`
- `frontend/src/components/consultation/HistoricalConsultationProjection.tsx`
- `frontend/src/components/patients/PatientDemographicDetails.tsx`
- `frontend/src/components/patients/PatientDemographicFields.tsx`
- `frontend/src/components/patients/PatientForm.tsx`
- `frontend/src/pages/Patients.tsx`
- `frontend/src/pages/patients.css`
- `frontend/src/services/patientAge.ts`
- `frontend/src/types/clinical.ts`
- `frontend/src/types/patient.ts`
- `frontend/tests/consultation-ui.test.mjs`
- `frontend/tests/historical-editability.test.mjs`
- `frontend/tests/patient-age.test.mjs`
- `frontend/tests/patient-selection-contract.test.mjs`
- `frontend/tests/patients-ui.test.mjs`

## Verificación

### Runtime local del PR #44

La comprobación de `localhost:5174` verificó el contenedor temporal
`consultorio-44-manual`, su bind mount
`C:\\proyectoconsultorio\\consultorio-medico\\frontend => /app`, la rama y el
HEAD `ac1c19d7cb5656adcce126ee5a20717e8f8c4839`. Aunque el HTML respondía
`Cache-Control: no-cache`, Vite conservaba en memoria módulos transformados de la
versión anterior porque Chokidar no recibió los cambios del bind mount de Docker
Desktop para Windows. El archivo en `/app` ya contenía las carpetas, pero el módulo
servido aún contenía `activeTab` y `patient-form-tabs`. No hubo service worker,
otro frontend en ese puerto ni un montaje desactualizado. Se reinició solamente el
contenedor frontend, sin eliminar su volumen, y `vite.config.ts` activa polling
para que las modificaciones futuras invaliden esa caché de transformación.

El ajuste posterior aplica `min(96rem, calc(100vw - 2rem))`, conserva el footer
del diálogo y muestra las dos carpetas en paralelo desde 1180 px; por debajo se
apilan antes de comprimir sus controles. En escritorio grande, contacto y los
contactos de emergencia/tutor usan tres columnas; en ancho intermedio, celular y
casa comparten fila y correo ocupa una fila completa. Las acciones rápidas de la
ficha están inmediatamente tras la identidad; en el drawer móvil forman dos
columnas desde 360 px y una columna en 320 px para evitar desborde y mantener
objetivos táctiles de 44 px.

La corrección visual posterior al contraste con la maqueta aprobada elimina las
tarjetas anidadas de cada grupo: cada carpeta conserva su borde externo y los
grupos internos se presentan como encabezados con icono y cuadrícula. El diálogo,
las dos carpetas, identificación, contacto, dirección, información adicional,
datos clínicos, seguro, emergencia y tutor usan iconos SVG locales, sin añadir una
dependencia ni iconos de texto. Se unificaron las etiquetas visibles de edad,
teléfonos, correo, sexo, seguro y afiliación con la maqueta; el aviso de sangre se
presenta una sola vez y mantiene que es un dato declarado, susceptible de
confirmación posterior. La pregunta de seguro y sus opciones Sí/No comparten fila
en escritorio para conservar la altura; `Plan` permanece debajo porque forma parte
del contrato vigente de la afiliación. Tutor conserva el tratamiento visual
opcional y el footer permanece fijo. No se añade `Observaciones`: el modelo de paciente no tiene ese
campo y las notas pertenecen a la historia clínica, por lo que mostrar un control
sin persistencia o crear otra fuente clínica de verdad sería incorrecto.

La validación posterior de la ficha detectó un segundo problema de layout: antes
de resolver `GET /patients/{id}`, el resumen tenía espacio por contener solo la
carga breve; al llegar `PatientDemographicDetails`, su `clientHeight` se reducía
a `0` mientras su `scrollHeight` quedaba en `404`, y el detalle completo elevaba
el `scrollHeight` del contenedor a `1057`. Era una contracción de Flexbox, no una
regla de permisos ni un cambio de estado de las acciones. El detalle ahora separa
`patients-detail-fixed` (identidad y acciones, `flex: 0 0 auto`) de
`patients-detail-body` (única región desplazable, `flex: 1 1 auto`). Las pruebas
diferidas verifican ambas transiciones: éxito y error de la ficha conservan las
acciones en la zona fija; solo el cuerpo se actualiza.

Las comprobaciones se ejecutan en contenedores aislados con datos ficticios, sin
usar la base clínica. PostgreSQL desechable ejecuta además las pruebas concurrentes
de pacientes y consultas. Se comprueba la cadena Alembic completa y la actualización
desde `0029_clinical_concurrency` con dos registros anteriores (con/sin contacto):
datos originales intactos y extensiones en NULL.

Las pruebas frontend cubren formularios reales en jsdom, foco y vista móvil,
teléfonos independientes, hidratación de edición, fallo/reintento de ficha,
respuestas obsoletas, contrato de seguro/prueba de selección, cumpleaños,
29 de febrero, fechas inválidas, límites pediátricos y fecha histórica. No se
afirma validación humana en un dispositivo móvil ni despliegue del cambio.

Resultados finales:

- Backend completo: **271 passed, 0 failed, 0 skipped** (incluye ambas variables
  PostgreSQL habilitadas: 5 casos de identidad y 5 de concurrencia clínica).
- Regresiones focalizadas PR #32: **52 passed**; demografía final: **30 passed**.
- Frontend completo: **233 passed, 0 failed**.
- TypeScript (`tsc -b`) y Vite build: **PASS**.
- Alembic/PostgreSQL y compatibilidad de registros anteriores: **PASS**.
- `git diff --check` y revisión del diff staged: **PASS**.
- Avisos backend: deprecaciones de dependencias y `datetime.utcnow` preexistentes;
  no impiden los resultados y no se modifica esa deuda en esta intervención.

### Validación de la evolución territorial

- Demografía y territorio: **33 passed** en SQLite aislado.
- Suite backend en el entorno disponible: **264 passed, 10 skipped**. Los diez
  omitidos requieren URLs PostgreSQL específicas de concurrencia que no se usan
  contra la base clínica.
- Formulario territorial focalizado: **2 passed**; cubre país principal, limpieza
  al cambiar provincia, hidratación de edición y conservación legacy.
- Suite frontend serial: **241 passed, 0 failed**.
- TypeScript y Vite: **PASS**.
- PostgreSQL desechable: se actualizó una base hasta `0030`, se insertó un
  paciente legacy y se aplicó `0031`; el resultado fue 158 municipios, provincia
  legacy intacta, país principal `DO` y versión `0031_country_territory`.

Comandos reproducibles: `python -m pytest -q --disable-warnings` en backend
(con `DATABASE_URL`, `SECRET_KEY`, `PATIENT_SECURITY_POSTGRES_URL` hacia una base
**desechable** llamada `patient_security_test` y `CLINICAL_CONCURRENCY_POSTGRES_URL`
hacia `clinical_concurrency_test`); `npm test` y `npm run build` en frontend.
No usar las bases clínicas para estas pruebas, que crean y eliminan sus tablas.

## Fuera de alcance

Reclasificar teléfonos antiguos (no se infiere si eran casa/celular), MPI o fusiones
de pacientes, país emisor de documento, distritos municipales/barrios/parajes,
normalización telefónica internacional, verificaciones de laboratorio, nuevos
permisos de historia, snapshots de datos maestros, notas clínicas adicionales y
Phase 6B9. Importaciones SQL externas deben usar la misma normalización; el índice
garantiza unicidad de valores canónicos, no corrige números crudos insertados fuera
de la API. La estructura de seguro y sus deudas previas no cambian.
