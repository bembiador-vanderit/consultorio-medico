# Historical / post-close boundary — Phase 6B8B

## Alcance auditado

Phase 6B8B unifica la lectura histórica en un modelo tipado compartido sin modificar contratos de backend. La base es `ec5d387c6632acdebb577687ab435b6e402f6253` (`feat/complete-care-context`). `ConsultationWorkspace` y `ClinicalHistoryPanel` usan el mismo loader y `HistoricalConsultationProjection` para representar el episodio completo en solo lectura.

## Fuentes de verdad y endpoints

| Recurso | Fuente actual | Lectura | Escritura y ciclo de vida | Propietario frontend |
| --- | --- | --- | --- | --- |
| `ClinicalHistory` activa | `useConsultationBootstrap` desde `ConsultationWorkspace` | `GET /clinical-history/appointments/{appointment_id}/context`; la historia de la cita se identifica por `appointment_id` | `POST /clinical-history/patients/{patient_id}`, `PUT /clinical-history/{history_id}` con `expected_revision`, `POST /clinical-history/{history_id}/complete` | `ConsultationWorkspace` + `AnamnesisModule` |
| `ClinicalHistory` anterior | `context.previous_consultations` | Incluida en la respuesta de contexto, con el alcance autorizado del backend | El modal no escribe | `ConsultationWorkspace` / `PreviousConsultationModal` local |
| Signos vitales | Carga del bootstrap para la historia activa; petición local al abrir historia anterior | `GET /clinical-history/{history_id}/vital-signs` | `PUT /clinical-history/{history_id}/vital-signs`; bloqueado tras cierre | `VitalSignsModule` / modal de solo lectura |
| Diagnósticos | Bootstrap activo; petición local histórica | `GET /clinical-history/{history_id}/diagnoses` | `POST` y `DELETE` bajo la historia; bloqueado tras cierre | `DiagnosesModule` / modal de solo lectura |
| Prescripciones | Bootstrap activo; petición local histórica | `GET /clinical-history/{history_id}/prescriptions` | `POST`, `PUT`, `DELETE`; bloqueado tras cierre | `PrescriptionsModule` / modal de solo lectura |
| Legacy `RequestedTest` | Bootstrap activo; petición local histórica | `GET /clinical-history/{history_id}/requested-tests` | Crear/eliminar solo en historia abierta; histórico/completado es lectura y PDF | Workspace / modal |
| `LaboratoryOrder` | `ClinicalOrdersSection` en la consulta activa, incluso si está completada | `GET /clinical-history/{history_id}/laboratory-orders` | Crear/actualizar antes del cierre; `POST .../laboratory-orders/additional` después del cierre cuando el backend lo autoriza | `ClinicalOrdersSection` |
| `StudyOrder` | `ClinicalOrdersSection` en la consulta activa, incluso si está completada | `GET /clinical-history/{history_id}/study-orders` | Crear/actualizar antes del cierre; `POST .../study-orders/additional` después del cierre cuando el backend lo autoriza | `ClinicalOrdersSection` |

Las dos órdenes estructuradas conservan snapshots de sus ítems y tienen PDFs propios: `GET /laboratory-orders/{order_id}/pdf` y `GET /study-orders/{order_id}/pdf`.

## Diferencia entre consulta activa y consulta anterior

### Consulta activa

El workspace monta los módulos clínicos con el `historyId` de la cita. Una historia abierta permite las mutaciones existentes y conserva la revisión/`expected_revision`. `ClinicalOrdersSection` carga catálogos y ambos recursos estructurados; una historia completada muestra los órdenes existentes en modo de solo lectura y, únicamente cuando `allowAdditional` es verdadero para el médico responsable activo, ofrece las rutas append-only `/additional`.

### Consulta completada mostrada como consulta activa

`status === "completed"` oculta guardar, finalizar, editar y eliminar en los módulos existentes. El resumen de consulta, receta, órdenes estructuradas y sus PDFs siguen siendo legibles/descargables. Una orden adicional crea una fila nueva con `is_additional=true`; no cambia la historia, la revisión ni las filas anteriores.

### Proyección histórica compartida

`loadHistoricalConsultationDetails(historyId, { signal })` reúne en paralelo signos vitales, diagnósticos, prescripciones, `RequestedTest`, addenda, `LaboratoryOrder` y `StudyOrder`. `HistoricalConsultationProjection` presenta esos snapshots, incluidos los PDFs estructurados, sin controles de mutación. El modal de `ConsultationWorkspace` conserva su PDF de resumen; el wrapper de `ClinicalHistoryPanel` conserva los PDFs de resumen, receta y `RequestedTest`, además de sus acciones autorizadas de addenda y órdenes adicionales.

La proyección no carga catálogos ni crea recursos. `RequestedTest` sigue siendo compatibilidad/historial; no se migra a órdenes estructuradas.

### Historia del paciente en `ClinicalHistoryPanel`

Existe una segunda superficie histórica desde Pacientes. `ClinicalHistoryPanel` obtiene `GET /clinical-history/patients/{patient_id}` y, al seleccionar o expandir una historia, carga en paralelo diagnósticos, prescripciones, `RequestedTest`, signos vitales, `GET /clinical-history/{history_id}/addenda`, `GET /clinical-history/{history_id}/laboratory-orders` y `GET /clinical-history/{history_id}/study-orders`. Renderiza `ClinicalOrdersHistory` con los dos tipos de orden y sus PDFs, muestra addenda inmutables para historias completadas y expone **Agregar nota adicional** / **Nueva orden adicional** solo cuando el propio frontend identifica al médico responsable activo; el backend vuelve a autorizar cada escritura.

Sus detalles se guardan por `historyId`. El loader mantiene controladores AbortController y una generación por ciclo del panel: cambio de paciente/historia, respuesta tardía y desmontaje no pueden publicar en otro episodio. Las acciones de mutación siguen fuera de la proyección y mantienen su autorización existente.

## Legacy frente a órdenes estructuradas

`RequestedTest` conserva su tabla, endpoints y PDF independiente. No se convierte en `LaboratoryOrder` ni en `StudyOrder`, y no se elimina ni se migra. `LaboratoryOrder` y `StudyOrder` son el modelo estructurado preferido para nuevas solicitudes y para adicionales autorizadas. Sus payloads, snapshots, estado `ordered` y PDFs actuales permanecen sin cambios.

## Autorización y ciclo de vida

Todos los GET históricos y PDFs pasan por `require_history_access` y el alcance clínico existente. Las escrituras normales rechazan historias completadas; las rutas adicionales exigen historia completada, usuario activo, médico responsable y acceso normal, y rechazan cobertura delegada, secretaría, administración, historias ajenas o contextos inválidos. La UI solo refleja `allowAdditional`; no sustituye la autorización del backend.

La finalización usa la revisión actual y deja la historia inmutable. Se conserva el comportamiento 409 de revisión obsoleta y de consulta ya finalizada. No se agregan estados, campos, endpoints, persistencia PHI ni reintentos.

## Guards de carreras del historial previo — Phase 6B8B

Antes de 6B8A, `viewPrevious` usaba `Promise.all` sin generación propia: una respuesta o error tardío podía publicar sobre el modal después de cambiar de consulta o desmontar el workspace. El bootstrap activo y `ClinicalOrdersSection` ya tenían sus propios guards.

`ConsultationWorkspace` conserva `previousRequestGeneration`, abortado y limpieza al cambiar de cita o desmontar. `ClinicalHistoryPanel` aplica el mismo aislamiento por generación a su loader compartido. Solo la generación vigente puede publicar detalles, error o estado de carga; no se abortan escrituras, no hay reintentos automáticos y no se inicia un segundo bootstrap. Las pruebas cubren:

- A → B → éxito tardío de A: no aparece A en B;
- A → B → error tardío de A: no aparece el error de A;
- petición pendiente → desmontaje: no publica estado después del unmount.

## PDFs y privacidad

El resumen histórico conserva `GET /clinical-history/{history_id}/summary/pdf`. Receta, `RequestedTest`, laboratorio y estudio conservan sus endpoints blob y nombres/descargas existentes. No se añade persistencia, caché persistente, logging de PHI ni analítica clínica; los datos permanecen en memoria React.

## Alcance exacto de Phase 6B8B

6B8B implementa esa proyección compartida. No unifica formularios ni introduce una nueva pantalla histórica: cada wrapper conserva su contexto, acciones autorizadas y composición visual. El seguimiento (`/follow-ups`) sigue siendo un workflow separado y no forma parte del snapshot histórico porque no existe un endpoint de lectura histórica para él.

## Intencionalmente sin cambios

- Backend, migraciones, esquema, payloads y endpoints.
- Autorización, cobertura clínica, especialidades y revisión de `ClinicalHistory`.
- Modelo y PDF legacy `RequestedTest`.
- Modelo estructurado, rutas `/additional` y PDFs de laboratorio/estudio.
- UI compacta 6B7B y la deuda visual pendiente del acordeón de laboratorio.
