# Regresiones multi-especialidad: caso Dr. Osiris Valdés

## Objetivo

Estas pruebas protegen el modelo clínico existente para un único médico con
Cardiología y Medicina Interna activas. Confirman que el mismo usuario, perfil
médico, paciente y centro pueden sostener episodios separados por especialidad.

## Escenarios protegidos

- Dr. Osiris conserva una sola cuenta, un solo `DoctorProfile`, dos
  especialidades activas y una especialidad principal válida.
- Dos citas del mismo médico pueden coexistir con Cardiología y Medicina
  Interna, sin mezclar sus `specialty_id`.
- Cada historia copia el contexto de su cita y conserva médico, paciente,
  centro y especialidad.
- Cambiar la especialidad principal o retirar una especialidad activa del
  médico no reasigna citas ni historias ya creadas.
- Una especialidad activa no asignada y una especialidad inactiva se rechazan
  al crear citas.
- Una cita no permite cambiar de especialidad después de iniciar consulta.
- La especialidad principal debe pertenecer a las especialidades asignadas.
- La selección automática para médicos con una sola especialidad sigue cubierta
  por `test_single_specialty_is_selected_automatically`.

## Correcciones de integridad

Las dos brechas detectadas por las regresiones preventivas quedaron corregidas:

1. El acceso a una historia vinculada exige que paciente, médico, centro y
   especialidad coincidan con su cita. El contexto inconsistente se rechaza
   antes de evaluar acceso normal, delegado o continuidad del principal.
2. La transferencia por cobertura exige que el médico sustituto tenga asignada
   y activa la especialidad de la cita. Puede ser una especialidad secundaria;
   no necesita ser la principal del sustituto.

Las pruebas que documentaban ambas brechas ya no usan `xfail`.

## Qué no implementan

No agregan Medicina Interna, Pediatría, plantillas de especialidad, campos
clínicos nuevos, cambios de autorización, rediseño frontend ni cambios en el
App Shell.

## Validación

- Prueba dirigida multi-especialidad: `27 passed`.
- Regresiones dirigidas de cobertura: `18 passed`.
- Suite backend completa: `178 passed`.
- Los dos antiguos `xfail` son pruebas normales y pasan.
- No se ejecutaron pruebas frontend porque esta misión no modifica la interfaz.
