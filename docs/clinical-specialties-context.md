# Especialidades en el contexto clínico

## Decisión de modelo

`specialties` continúa siendo el catálogo central. `doctor_profiles.specialty_id` conserva la especialidad principal para compatibilidad con el catálogo clínico existente y `doctor_specialties` representa la relación normalizada de todas las especialidades asignadas al médico. La especialidad principal siempre debe formar parte de esa relación.

La administración es la única autorizada para cambiar especialidades. Una cita guarda su propia `specialty_id`; al iniciar la consulta, ese valor se copia a `clinical_histories.specialty_id`. Los esquemas ordinarios de consulta no aceptan campos de contexto y, después de iniciarse la consulta, la cita tampoco permite cambiar paciente, médico, centro o especialidad.

## Migración de datos históricos

La migración `0024_clinical_specialties` agrega las especialidades iniciales y una entrada inactiva llamada `No especificada (registro histórico)`. Primero infiere la especialidad desde `doctor_profiles` cuando existe la asignación única que soportaba el modelo anterior. Las citas o consultas que no pueden inferirse con seguridad se vinculan a la entrada histórica explícita. No se asigna silenciosamente una especialidad clínica real.

La entrada histórica no se devuelve en el catálogo activo ni puede elegirse en citas nuevas. Al terminar el backfill, PostgreSQL exige `specialty_id NOT NULL` tanto en citas como en consultas.

## Coberturas

Esta fase no cambia las reglas de cobertura validadas. Una transferencia conserva la especialidad histórica de la cita. Deuda técnica prevista: si el producto requiere limitar una cobertura por especialidad, debe agregarse una relación explícita entre cobertura y especialidad, y validar que el sustituto tenga esa especialidad antes de transferir; no se debe inferir desde una selección global de Dashboard.

## Preparación para plantillas

La especialidad de la cita/consulta es la fuente de contexto para futuros catálogos y plantillas. La arquitectura permite relacionar configuraciones futuras con `specialties.id` sin separar la historia longitudinal del paciente ni crear una especialidad activa global por médico.
