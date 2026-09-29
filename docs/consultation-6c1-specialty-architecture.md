# Phase 6C1 — arquitectura de consulta por especialidad

## Decisión

Atlas determina la experiencia clínica desde la especialidad de la cita. La especialidad principal del perfil del médico sigue siendo un valor administrativo y un valor predeterminado; no reemplaza `Appointment.specialty_id` cuando una cita ya seleccionó otra especialidad asignada al mismo médico.

La cadena autorizada es:

```text
User/Doctor
   │
   ├── Cardiología
   └── Pediatría
          │
Appointment.specialty_id
          │
          ▼
SpecialtyTemplate (version)
          │
          ▼
SpecialtyTemplateModule
          │
          ▼
Consultation Module Registry
          │
          ▼
Clinical Modules
```

No existe una especialidad global de sesión. El contexto clínico no depende de `localStorage`, del último selector utilizado ni de un cambio temporal del perfil del médico. Dos citas con especialidades diferentes pueden abrirse sucesivamente con el mismo usuario autenticado.

## Infraestructura reutilizada

Antes de 6C1 Atlas ya disponía de:

- `Specialty` y el catálogo administrativo para crear, renombrar y activar especialidades;
- `DoctorProfile.specialty_id` como especialidad principal administrativa;
- la relación many-to-many `doctor_specialties` y `User.specialties` para las especialidades activas del médico;
- validación en `clinical_specialties.py` para resolver una única especialidad automáticamente o exigir selección explícita cuando hay varias;
- `Appointment.specialty_id` como selección autorizada de la cita;
- `ClinicalHistory.specialty_id` como snapshot del contexto clínico;
- alcance de citas, transferencias de cobertura y permisos que verifican la especialidad asignada;
- `MedicalStudy.recommended_specialties` y filtrado del catálogo por especialidad.

6C1 conserva estos contratos. Agrega la versión de estructura usada por cada episodio.

## Plantillas versionadas

`SpecialtyTemplate` contiene `specialty_id`, `version`, `status`, `created_at` y `published_at`. Los estados válidos son `draft`, `published` y `retired`. Una restricción única protege la pareja especialidad/versión y un índice único parcial permite una sola plantilla publicada por especialidad.

`SpecialtyTemplateModule` persiste una key estable y su posición. Las restricciones impiden repetir una key o una posición dentro de una plantilla. Los nombres de componentes React nunca se guardan en la base de datos.

La publicación ocurre en el servicio central `specialty_templates.py`: valida todas las keys, bloquea la especialidad durante el cambio, retira la versión publicada anterior y publica el borrador. Los borradores nunca son resueltos para consultas. No se expone un editor de plantillas en 6C1.

Cada especialidad existente recibe por migración una plantilla v1 publicada con este orden, que reproduce el workspace anterior:

1. `core.anamnesis`
2. `core.vital-signs`
3. `core.diagnoses`
4. `core.prescriptions`
5. `core.clinical-orders`

El servicio usado por administración crea la misma plantilla base al crear una especialidad nueva.

## Registro de módulos

El registro backend define las keys conocidas, la etiqueta y el indicador `required`. Crear o publicar una plantilla con keys desconocidas produce un error explícito. El registro frontend relaciona esas mismas keys con componentes React tipados y usa `position` para renderizarlos.

El frontend también se protege ante datos incompatibles: muestra un error controlado con la key desconocida y no la ignora silenciosamente. Los cinco componentes existentes conservan sus contratos de guardado, errores, conflictos de revisión, estado dirty, finalización, navegación protegida, modales y `beforeunload`.

## Snapshot histórico

`ClinicalHistory.specialty_template_id` es una FK nullable y no forma parte de los schemas de escritura del cliente. Al crear una historia, el backend deriva médico, centro, especialidad y plantilla publicada desde la cita autorizada. Ni `specialty_id` ni `specialty_template_id` pueden enviarse en el payload.

El valor queda inmutable durante la vida de la historia. `ConsultationContext` usa siempre la plantilla del snapshot si la historia ya existe, incluso cuando luego se publica otra versión. Las consultas finalizadas conservan el mismo snapshot y siguen siendo de solo lectura.

La migración asocia historias existentes a la plantilla base v1 solamente cuando tienen un `specialty_id` que coincide con una especialidad existente. Una historia sin especialidad válida conserva `specialty_template_id = NULL`. Esos registros legacy siguen siendo legibles mediante el orden histórico de los cinco módulos, y la respuesta identifica la ausencia de una versión real con `template_id` y `template_version` nulos.

## Tres conceptos separados

1. **Specialty Template:** estructura estándar, versionada y publicada para una especialidad.
2. **Doctor Specialty Preferences:** punto futuro para preferencias conocidas, limitadas y validadas de un médico dentro de una especialidad.
3. **Clinical data:** datos reales y tipados de cada consulta.

Las preferencias futuras no deben convertirse en un JSON abierto. Los datos clínicos especializados tendrán modelos, schemas, validaciones y componentes propios.

## Extensión para 6C2 y 6C3

Cardiología podrá agregar keys como `cardiology.assessment` o `cardiology.ecg` después de registrar primero su definición backend, persistencia clínica, validaciones, permisos, API, componente frontend y pruebas. Luego se creará y publicará una nueva versión de la plantilla de Cardiología.

Pediatría seguirá el mismo proceso con módulos tipados, por ejemplo crecimiento o vacunación. La utilidad de edad pediátrica y los datos de cada episodio permanecerán separados de la configuración de la plantilla.

No se debe implementar esta extensión mediante condicionales dispersos `if specialty == ...`, un JSON clínico universal, campos arbitrarios no-code, SQL configurable, nombres de componentes persistidos ni contexto clínico en `localStorage`.

El catálogo de estudios continúa usando `MedicalStudy.recommended_specialties`; 6C1 no cambia su semántica ni el catálogo de laboratorio.
