# Documentos clínicos independientes (0055)

La evaluación médica preoperatoria y el examen físico independiente son dos
registros longitudinales distintos. Ambos pertenecen a la organización,
paciente, médico y centro; la cita y la historia clínica son vínculos opcionales.
La evaluación preoperatoria conserva íntegra su propia sección de examen
físico. El formulario de examen físico independiente reutiliza los mismos
campos de interfaz, pero no el mismo registro.

El contenido libre refleja las dos caras de la hoja suministrada por la clínica.
Se aplicaron las correcciones confirmadas: **Hepatitis**, **Otros** en la línea
sin rótulo, **Glicemia** y **Creatinina**. Las abreviaturas **PCB** e **IVY** se
mantienen literalmente, sin expansión clínica pendiente de validación por el
médico. Ningún valor clínico se infiere ni se calcula en esta microfase.

El ciclo es `draft → pending_evaluation → completed → signed`. La secretaría
autorizada puede crear y preparar el campo administrativo de procedimiento; no
puede leer ni modificar contenido clínico, completar o firmar. El médico
tratante con `clinical:access` puede completar y firmar explícitamente. La
firma registra usuario, fecha/hora y un snapshot administrativo del paciente y
contexto. Un documento firmado es inmutable; las enmiendas clínicas futuras
requieren un flujo auditado separado. Creación, edición y transiciones se
registran en `clinical_audit_logs`. La impresión PDF distingue documentos
firmados de los no firmados y usa el médico/centro reales.

Un índice único parcial limita a un borrador o pendiente por tipo, paciente,
médico, centro y fecha. Los documentos completados o firmados permanecen en el
historial; una evaluación posterior es un registro nuevo. Las actualizaciones
requieren `expected_revision` para evitar sobrescritura silenciosa.

La interfaz está protegida por `VITE_CLINICAL_DOCUMENTS_ENABLED=false` por
defecto. No habilitarla antes de aplicar oficialmente 0055 en una tarea
separada. El backend devuelve 503 para estos endpoints si las tablas aún no
existen. Esta implementación y sus pruebas **no migran la base oficial 0054**.

El flujo desde Paciente permite crear sin cita para preparación. El flujo de
Consulta asocia cita e historia clínica si esta ya existe. No se creó una
consulta directamente desde la ficha porque el ciclo de consulta actual exige
una cita vinculada; se conserva `Agendar cita` como acceso a ese flujo.
El documento preparado extiende la visibilidad de identidad del paciente para
la secretaría asignada a ese médico/centro, incluso antes de agendar; no
extiende la lectura del contenido clínico.
No se vinculan documentos nuevos a una consulta ya finalizada; los documentos
previamente asociados siguen disponibles en modo de lectura/continuación según
su propio estado.
