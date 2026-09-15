# Caracterización de Consulta — Phase 6B1

## Propósito

Phase 6B1 crea una red de seguridad alrededor de la Consulta actual antes de cualquier modularización. No modifica backend, API, base de datos, lifecycle, seguridad ni diseño visual.

## Suite directa

`frontend/tests/consultation-ui.test.mjs` importa y renderiza `Consultation.tsx` con Node test, JSDOM, Vite y un adapter Axios falso. Sus fixtures son deterministas y ficticios en `frontend/tests/fixtures/clinical.mjs`.

La suite caracteriza:

- consulta nueva: contexto de cita, módulos bloqueados hasta el primer guardado y vuelta a Agenda;
- primer `POST /clinical-history/patients/{patient_id}`: payload clínico más `appointment_id`, sin `doctor_id`, `center_id`, `specialty_id` ni `patient_id` del cliente;
- consulta `in_progress`: bootstrap actual de aproximadamente 11 GET entre autenticación, contexto, catálogos, recursos clínicos y órdenes;
- vitales, diagnósticos, receta, requested tests legacy y órdenes estructuradas;
- `POST /clinical-history/{history_id}/complete`, modo de solo lectura, documentos y errores 409/403;
- lectura de una historia previa y su cierre por el botón existente.

La Historia previa actual no incorpora handlers de Escape ni backdrop en `Consultation.tsx`; la caracterización no los presenta como capacidades existentes.

## Contratos compartidos

`frontend/src/types/clinical.ts` contiene los contratos estables comprobados contra los schemas backend actuales:

- `ConsultationContext`;
- `ClinicalHistory`, `ClinicalHistoryContent` y `ClinicalHistoryStatus`;
- `Diagnosis`, `Prescription`, `PrescriptionInput`, `RequestedTest`, `VitalSigns` y `MedicalStudy`.

`types/clinicalHistory.ts` y `types/clinicalOrder.ts` reexportan contratos para preservar los consumidores existentes. `Consultation.tsx` deja de mantener sus DTOs clínicos propios. `Appointment.specialty_id`, `ConsultationContext.specialty_id` y `ClinicalHistory.specialty_id` se representan como `number | null`, como permiten los schemas legacy del backend. No se crea una especialidad de fallback.

## Lifecycle preservado

1. La Agenda entrega una cita; el backend valida acceso y deriva el contexto.
2. La primera persistencia crea la historia vinculada a la cita como `in_progress`.
3. Los recursos hijos requieren `historyId`.
4. El cierre usa `POST /clinical-history/{history_id}/complete` y el servidor actualiza History y Appointment.
5. Una historia `completed` queda solo lectura; documentos siguen permitidos. Addenda y órdenes adicionales conservan sus reglas backend existentes.

## Endpoints caracterizados

- `GET /auth/me`
- `GET /clinical-history/appointments/{appointment_id}/context`
- `POST /clinical-history/patients/{patient_id}`
- `PUT /clinical-history/{history_id}`
- `POST /clinical-history/{history_id}/complete`
- recursos de vitales, diagnósticos, prescripciones, requested tests, órdenes, catálogos y PDFs ya usados por la UI.

## Deuda conocida, fuera de 6B1

- UNIQUE DB Appointment/History: pendiente 6B2.
- Optimistic concurrency: pendiente 6B2.
- Carrera update-vs-complete: pendiente 6B2.
- Bootstrap fragmentado: pendiente 6B3.
- Cancelación de requests/respuestas tardías: pendiente 6B3. La UI actual no dispone de cancelación ni generación de request; no se corrigió silenciosamente en esta fase.
- `ConsultationWorkspace`: pendiente 6B4.
- Plantillas y versionado por especialidad: pendiente 6C.

## Límites explícitos

No hay autosave, locks, ETag, `If-Match`, cambios de endpoints, migraciones, módulos de Cardiología/Pediatría, registry de especialidad, reapertura de consulta ni cambios visuales en Phase 6B1.
