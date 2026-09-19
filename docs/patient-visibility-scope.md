# Scope y privacidad de pacientes

## Principio

Atlas conserva un único registro organizacional por paciente. La existencia de ese registro no concede acceso automático a su información clínica. La identidad administrativa y la historia clínica tienen reglas de autorización distintas.

## Administrador

El administrador puede listar, localizar y actualizar datos de identidad del paciente para tareas organizativas y prevención de duplicados. El rol `admin`, por sí solo, no permite abrir consultas, leer historias clínicas, descargar documentos clínicos ni administrar seguimientos clínicos.

Una cuenta que tenga simultáneamente los roles `admin` y `doctor` conserva únicamente el alcance clínico que le corresponde como médico responsable.

## Médico

El listado habitual muestra pacientes relacionados con el médico mediante una cita vigente/completada o una consulta histórica propia. El médico puede abrir la atención de una cita cuyo responsable actual sea él.

Una cita nueva permite atender esa cita, pero no revela automáticamente consultas realizadas por otros médicos. Los accesos directos mediante `patient_id`, `history_id` o `appointment_id` se validan nuevamente en backend.

## Secretaria

La secretaria visualiza identidades asociadas a citas incluidas en su alcance configurado de centro y médicos. Puede realizar una búsqueda mínima para preparar una cita únicamente indicando un centro y médico que tenga autorizado. No recibe acceso a historia clínica, diagnósticos, recetas, signos vitales, estudios ni seguimientos clínicos.

## Cobertura clínica

La cobertura continúa siendo una autorización explícita y concreta. Requiere principal, sustituto, centro, vigencia y una cita transferida. Solo la transferencia del paciente concreto permite consultar el historial previo autorizado; no abre los demás pacientes del médico principal. El acceso delegado previo es de solo lectura y conserva la auditoría existente.

Una cobertura programada permite transferir anticipadamente una cita cuya fecha y hora estén dentro del período autorizado. La cita aparece de inmediato en la agenda del suplente, pero esa visibilidad administrativa no adelanta el acceso clínico: iniciar la consulta y consultar historia ajena siguen exigiendo que la cobertura esté vigente.

Mientras la cobertura permanezca vigente, completar la cita transferida no elimina el acceso delegado al historial previo de ese paciente. Cuando expira o se revoca, el suplente pierde dicho acceso ajeno, aunque sus propios episodios permanecen registrados con su autoría real. El médico principal conserva acceso de solo lectura a los episodios realizados bajo la transferencia concreta para continuidad asistencial.

Una secretaria puede ver y ejecutar la transferencia anticipada cuando su configuración autoriza al médico principal en el centro de la cobertura. Esa cobertura explícita limita su gestión a las citas concretas del principal transferidas al suplente: no le concede alcance general sobre la agenda del suplente ni acceso a información clínica. Puede reprogramar una cita transferida solo dentro del mismo período de cobertura y mientras no se haya iniciado una consulta; paciente, centro, especialidad y médicos de origen/destino permanecen inmutables.

## Búsqueda restringida y duplicados

`GET /api/v1/patients/identity-search` exige fecha de nacimiento y teléfono o correo exacto. No admite el nombre como único identificador. La respuesta contiene solamente identificador, nombre, fecha de nacimiento y contacto enmascarado; nunca incluye información clínica.

Antes de crear un paciente, el backend rechaza una coincidencia exacta de fecha de nacimiento más teléfono o correo. La pantalla de cita permite seleccionar esa identidad existente sin crear otro registro.

## Selección de paciente para citas — Phase 5, misión 2

La causa raíz del acceso por ID directo era comprobar únicamente que el paciente
existiera al crear la cita. Esa cita fabricaba la relación que permitía leer y
editar después su identidad completa. Ahora POST de citas exige identidad en el
scope vigente del usuario o una prueba de selección firmada por backend.
Cambiar el paciente de una cita editable exige la misma regla. La prueba no
sustituye permisos, asignación válida de centro/médico/especialidad, scope
secretarial ni reglas de cobertura/contexto inmutable.

`POST /patients` devuelve `selection_token` adicional al creador autorizado.
Así el paciente nuevo, incluso sin contacto y todavía fuera del listado normal,
puede recibir su primera cita sin conceder visibilidad por creación a todos los
pacientes. `GET /patients/identity-search` devuelve también `selection_token`
junto a la identidad mínima. No concede lectura completa por buscarla.

El cliente envía esa prueba en `patient_selection_token` de POST/PUT de cita.
Es opcional para identidades ya visibles. La prueba vence a los 30 minutos, está
ligada a usuario y paciente y, en búsqueda, al centro/médico indicados. Para doctor
sin médico explícito en búsqueda queda ligada a su propio ID. El alta nueva
permite elegir el contexto que el usuario tenga autorizado en ese momento.
El servidor vuelve a comprobar la asignación al guardar; revocar un scope no
puede evitarse con una prueba anterior. Si vence antes de la primera cita,
repetir búsqueda exacta cuando haya contacto; sin contacto, un admin puede
programarla por su scope organizacional. No crear un duplicado para renovar prueba.

JWT usa audiencia `patient-selection`, distinta del token de sesión; no contiene
contacto ni datos clínicos, no debe registrarse en logs y no sirve para autenticar
ni abrir historia. ID ajeno sin prueba, ID distinto, prueba manipulada/vencida o
de otro usuario/contexto responden 404 de paciente no encontrado. La prueba no
se persiste en Appointment ni se devuelve como atributo de cita.

La precedencia administrativa sigue siendo admin → secretary → doctor en
identidad, y admin → doctor → secretary en identity-search. No se modifica la
política clínica: admin solo no lee episodios; admin+doctor conserva su autoría,
centro y cobertura clínica concreta. Los pacientes transferidos ya visibles
pueden seleccionarse, pero eso no adelanta acceso clínico de cobertura futura.

## Edición e integridad de identidad

POST y PUT comparten chequeo DOB exacta + teléfono exacto o email sin distinguir
mayúsculas. Nombre/apellido no participan. Teléfono se recorta en las escrituras;
no se normalizan guiones ni prefijos ni se introducen criterios MPI nuevos.
PUT excluye su propio ID y comprueba conflicto al cambiar DOB/contacto. Conflicto
devuelve el mismo 409 genérico del alta, sin identidad del coincidente. Ediciones
de nombre o identidad sin cambios y registros legacy sin contacto permanecen
permitidos bajo el scope existente; no se reparan duplicados legacy por accidente.

PostgreSQL serializa chequeos concurrentes mediante advisory locks transaccionales
por DOB/identificador, tomados en orden estable y retenidos hasta commit/rollback.
La edición bloquea además la fila para obtener su estado actual. No requiere
migración. Esta garantía cubre escrituras de identidad a través de estos endpoints;
no garantiza integridad de SQL/importaciones externas. SQLite sirve para tests
funcionales; la regresión de concurrencia se ejecuta aparte en PostgreSQL desechable.

## Actualización de seguro por PUT de paciente

PUT conserva el contrato de identidad completa, pero diferencia intención de
seguro mediante campos realmente presentes (`model_fields_set`):

| Payload de seguro | Resultado |
| --- | --- |
| Ambos campos omitidos | Conservar afiliaciones |
| `insurance: null`, sin false explícito | Conservar afiliaciones |
| `has_insurance: true`, insurance omitido/null | Conservar; compatible con PatientForm sin cambios |
| Objeto `insurance` válido, con true o sin flag | Agregar afiliación y desmarcar principales previas, como el flujo existente |
| `has_insurance: false`, insurance omitido/null | Desactivar explícitamente todas las activas y conservar filas |
| false + objeto insurance | 422 contradictorio, sin cambios |

Compañía activa, estructura y afiliado no vacío se validan antes de mutar paciente
o afiliaciones. Identidad y seguro se confirman juntos; un fallo de commit hace
rollback explícito. No se añade PATCH ni edición destructiva de una afiliación.
Cambiar seguro conserva la semántica anterior: filas previas pueden seguir activas
sin ser principales, y no se inventa un snapshot de cobertura por consulta.

Compatibilidad frontend: solo se añade transporte del token de selección en
PatientForm/AppointmentForm y tipo Patient. Patients.tsx y layout no cambian.
Los clientes anteriores siguen funcionando con pacientes visibles/admin; para
paciente recién creado o localizado fuera de scope deben enviar la prueba nueva.
Ocultar IDs en frontend nunca reemplaza estas comprobaciones.

## No revelación

Los accesos a identidades fuera del scope responden como paciente no encontrado. Los accesos directos a una historia existente mantienen el rechazo auditado del servicio clínico. Esta combinación evita confirmar innecesariamente recursos ajenos y conserva la trazabilidad existente.

## Límites conocidos

- La prevención de duplicados es deliberadamente básica: fecha de nacimiento más teléfono o correo exacto.
- El modelo todavía no incluye documento/cédula normalizado.
- No existe acceso de emergencia (`break-glass`) ni consentimiento electrónico en esta fase.
- La política descrita es una decisión de seguridad y producto; no constituye una conclusión legal.
