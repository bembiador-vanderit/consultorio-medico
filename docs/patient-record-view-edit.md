# Ficha del paciente: consulta y edición explícita

La ficha completa reutiliza `PatientForm`. Los pacientes existentes se abren en
modo lectura con un `fieldset disabled`; no se envía PUT al abrir/cerrar. La
creación de pacientes conserva su flujo anterior. El país predeterminado solo
se propone para registros nuevos, nunca al consultar un paciente existente.

Editar captura los valores originales. Cancelar restaura también seguro y
ubicación; si existen cambios efectivos solicita confirmación. Cerrar mediante
X/Escape utiliza la misma protección. El diálogo nativo mantiene inerte el
listado de pacientes de fondo, evitando cambiar de paciente durante la edición.
La recarga/salida de página con cambios utiliza la advertencia del navegador.
Guardar sin cambios vuelve a lectura sin PUT; guardar con éxito actualiza la
ficha y vuelve a lectura. Un error conserva el formulario y sus valores.

## Autorización

GET de pacientes exige `patients:view`; POST/PUT exige `patients:edit`, que solo
es operativo junto con `patients:view`. Un usuario view-only puede consultar la
ficha, pero no ve Editar ni Nuevo paciente y recibe 403 al intentar PUT directo.
Los controles existentes de tenant y alcance no cambian. Seguro mantiene
`insurance:manage` independiente; edad sigue calculada y no editable.

La transición desde `patients:access`, el bootstrap y la política de privacidad
están descritos en [Patient Access & Audit Hardening](patient-access-audit-hardening.md).

## Auditoría

Las modificaciones reales se guardan ahora en `ClinicalAuditLog`, recurso
`patient`, acción `patient.update`, con diferencias demográficas before/after.
Los valores clínicos se redactan. Los eventos anteriores de `SecurityAudit`
permanecen intactos; no se convierten ni se borran. GET y PUT sin diferencias
no generan auditorías de modificación. Seguro mantiene su auditoría existente.

No hay migración ni cambios de estructura de datos.
