# Phase 6C2 — plan de Cardiología

## Límite clínico

Atlas es una herramienta de registro. No diagnostica, recomienda tratamientos, interpreta ECG automáticamente ni sustituye el criterio médico. Los campos especializados se implementarán únicamente después de validarlos con el cardiólogo del piloto.

## 6C2A — identidad técnica y validación clínica

Esta fase agrega `Specialty.code` como identidad técnica estable. El nombre sigue siendo la etiqueta administrativa y puede cambiar según las reglas actuales; el código no cambia al renombrar.

El backend genera el código y resuelve colisiones. `SpecialtyCreate` y `SpecialtyUpdate` no aceptan `code`; las respuestas sí lo incluyen como solo lectura. La migración asigna códigos a todas las especialidades existentes, garantiza `NOT NULL` y unicidad, y conserva DoctorProfile, asignaciones many-to-many, citas, historias, plantillas, estudios y órdenes.

La hoja [Validación clínica previa a 6C2B](cardiology-pilot-validation.md) organiza la sesión con el Dr. Osiris. Todas sus listas están marcadas como propuestas y no crean aprobación implícita.

## 6C2B — assessment cardiológico aprobado

Después de documentar la aprobación clínica se podrá diseñar la persistencia por episodio, schemas, permisos, API, componentes y pruebas del assessment. El análisis inicial contempla un posible `CardiologyAssessment` uno-a-uno con `ClinicalHistory`, sin decidir todavía sus campos.

Antes de publicar una plantilla nueva se deben registrar todos sus módulos en backend y frontend y garantizar lectura histórica. `cardiology.assessment` no forma parte del registry ni de una plantilla en 6C2A.

## 6C2C — ECG, historial y presentación

Si la validación lo aprueba, esta fase podrá cubrir el registro manual del ECG, su cardinalidad, presentación longitudinal y salidas PDF. Un posible `Electrocardiogram` uno-a-muchos con `ClinicalHistory` se confirmará con el flujo real. No se presuponen mediciones, formatos ni interpretación automática.

## 6D — equipos y archivos

Las integraciones con ECG, Holter, MAPA, ecocardiograma, prueba de esfuerzo u otros equipos se diseñarán después de conocer dispositivos, software, formatos exportados y flujo del consultorio. Los archivos médicos permanecerán fuera de Git y separados de sus metadatos.

## Cobertura core que se conserva

Anamnesis, signos vitales, diagnósticos, recetas y órdenes clínicas siguen siendo fuentes de verdad compartidas. Cardiología no duplicará esos datos. `Appointment.specialty_id`, el snapshot de `ClinicalHistory`, `SpecialtyTemplate` versionado, preferencias futuras del médico y datos clínicos continúan como conceptos separados.

## Fuera de 6C2A

- formulario cardiovascular y campos definitivos;
- NYHA, CCS, scores o protocolos;
- recomendaciones, cálculos o inferencias diagnósticas;
- modelos de assessment o ECG;
- cambios en el workspace o PDF clínico;
- registro de módulos cardiológicos;
- plantilla v2 de Cardiología;
- cambios de catálogos basados en suposiciones.
