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

## Brechas conocidas expuestas sin cambios funcionales

Dos pruebas usan `xfail(strict=True)` para hacer visible el comportamiento
actual sin modificar producción:

1. `has_normal_history_access` compara paciente, médico y centro entre cita e
   historia, pero no `specialty_id`. Una discrepancia de datos creada fuera del
   flujo ordinario sigue obteniendo acceso normal.
2. Una transferencia por cobertura no confirma que el médico sustituto tenga
   asignada la especialidad de la cita transferida.

Ambas pruebas deben pasar sin `xfail` únicamente cuando una misión específica
de integridad y cobertura apruebe el cambio de producción y actualice esta
documentación.

## Qué no implementan

No agregan Medicina Interna, Pediatría, plantillas de especialidad, campos
clínicos nuevos, cambios de autorización, rediseño frontend ni cambios en el
App Shell.

## Validación

- Prueba dirigida: `22 passed, 2 xfailed` en 18.62 s.
- Suite backend completa: `173 passed, 2 xfailed` en 187.61 s.
- Los dos `xfail` corresponden exclusivamente a las brechas descritas arriba.
- No se ejecutaron pruebas frontend porque esta misión no modifica frontend.
