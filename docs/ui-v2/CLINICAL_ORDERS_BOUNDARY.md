# Clinical orders boundary — Phase 6B7A

## Purpose and compatibility

Atlas currently has three separate ways to record a request from a clinical history. They coexist intentionally. Phase 6B7A characterizes and protects those contracts; it does not delete, migrate, reinterpret, or visually replace `RequestedTest`.

| Concept | Current UI owner | Source of truth | Intended current role |
| --- | --- | --- | --- |
| Legacy `RequestedTest` | `ConsultationWorkspace` → **Estudios y análisis** | `requested_tests` | Free-text compatibility and historical requests |
| `LaboratoryOrder` | `ClinicalOrdersSection` | `laboratory_orders` + item snapshot rows | Structured multiple laboratory tests |
| `StudyOrder` | `ClinicalOrdersSection` | `study_orders` + item snapshot rows | Structured multiple study/procedure items |

The two structured concepts overlap with the broad idea of requesting studies, but do not share records with `RequestedTest`. A free-text requested test is neither converted into nor rendered as a structured order. Existing `RequestedTest` data remains readable, printable and independently protected.

## Legacy RequestedTest

`RequestedTest` has `id`, `clinical_history_id` and `test_name`. The workspace receives its initial canonical list from `useConsultationBootstrap`, which calls `GET /clinical-history/{history_id}/requested-tests` with the other episode resources. The workspace owns the free-text input, duplicate-name check within the loaded list, create/delete UI and its PDF action.

- **Read/list:** `GET /clinical-history/{history_id}/requested-tests`, ordered by record ID.
- **Create:** `POST /clinical-history/{history_id}/requested-tests` with `{ test_name }`; the frontend trims before sending and adopts the returned item.
- **Delete:** `DELETE /clinical-history/requested-tests/{test_id}`; there is no update endpoint.
- **PDF:** `GET /clinical-history/{history_id}/requested-tests/pdf`, generated from the history, patient, doctor, center and stored test names. The workspace downloads it as `orden-estudios-{historyId}.pdf`.
- **Lifecycle:** normal create/delete requires a writable history. A completed history is readable and its PDF remains available, while its free-text mutation controls are hidden. No legacy post-close/additional route exists.
- **Authorization:** `require_history_access` is authoritative for list, PDF, create and delete; the write paths enforce the normal lifecycle. Client-side disabling is only presentation.
- **Race and privacy:** it participates in the bootstrap generation/AbortController guard. It has no independent module GET, no persistent cache, storage, analytics or logging. Its historical display is the workspace list and previous-history modal.

Backend coverage includes `test_requested_tests_pdf.py` and lifecycle/scope assertions in `test_clinical_security_lifecycle.py`; frontend characterization now explicitly checks visibility, completed read-only state and PDF behavior.

## Structured LaboratoryOrder

`ClinicalOrdersSection` owns laboratory catalog loading, query filtering, selected IDs, general notes, edit mode, order list, mutation feedback and PDF button. It owns no history bootstrap: the workspace supplies `historyId`, `specialtyId`, `completed` and, when allowed, `allowAdditional`.

- **Catalog:** `GET /laboratory-tests` returns active catalog entries only, ordered by category, sort order and name. The frontend filters the loaded active list by name/category; it supports multiple selected IDs.
- **Read/list:** `GET /clinical-history/{history_id}/laboratory-orders`, ordered by creation time and ID.
- **Create:** `POST /clinical-history/{history_id}/laboratory-orders` with `{ items: [{ laboratory_test_id }], notes }`. The UI sends trimmed notes or `null`; it sends no patient, doctor, center or specialty IDs.
- **Update:** `PUT /clinical-history/{history_id}/laboratory-orders/{order_id}` with that same payload. Editing restores selected test IDs and notes. There is no delete route.
- **PDF:** `GET /laboratory-orders/{order_id}/pdf`, downloaded as `orden-laboratorio-{orderId}.pdf`.
- **Stored context:** the backend derives history/appointment/patient/doctor/center/specialty, snapshots display values and test item values, and records `is_additional`.
- **Lifecycle:** regular create/update use `require_history_access(..., write=True)`, so completed histories reject them. Existing completed orders stay readable and printable.

For an additional laboratory order, `POST /clinical-history/{history_id}/laboratory-orders/additional` creates a new append-only row with `is_additional=true`. It is only valid for a completed history and the active responsible doctor with normal history access. It cannot edit or reopen an older order. The frontend only reveals this existing path when `allowAdditional` is true; the workspace calculates that presentation flag for the active doctor and completed history. The backend remains authoritative and also rejects secretary, administrative-only, inactive, foreign or delegated read-only access.

The backend rejects empty/duplicate/nonexistent/inactive tests for new writes. Historical item snapshots remain readable even if a catalog entry later becomes inactive. No retries are implemented, so a failed POST/PUT cannot be duplicated automatically.

## Structured StudyOrder

`ClinicalOrdersSection` also owns structured study/procedure selection and its per-item fields. It performs its own catalog/list reads rather than receiving those resources from the consultation bootstrap.

- **Catalog:** `GET /clinical-catalog/studies?include_all=true&specialty_id={specialtyId?}`. It returns active master catalog entries. The section shows items recommended for the active specialty first as a visual recommendation; recommendation is not authorization and does not change the history specialty.
- **Read/list:** `GET /clinical-history/{history_id}/study-orders`, ordered by creation time and ID.
- **Create:** `POST /clinical-history/{history_id}/study-orders` with `{ items: [{ medical_study_id, region_description, contrast, clinical_notes }], notes }`.
- **Update:** `PUT /clinical-history/{history_id}/study-orders/{order_id}` with the same contract. Editing restores selected IDs, region/description, contrast, clinical notes and general notes. There is no delete route.
- **Field semantics:** optional text is trimmed or `null`; `contrast` is exactly `yes`, `no`, or `not_applicable`; multiple distinct studies are supported.
- **PDF:** `GET /study-orders/{order_id}/pdf`, downloaded as `orden-estudios-{orderId}.pdf`.
- **Lifecycle and authority:** normal writes are history-scoped and reject a completed history. `POST /clinical-history/{history_id}/study-orders/additional` has the same completed/responsible-doctor append-only restrictions as laboratory additional orders.

The backend rejects duplicate, missing, inactive, or no-longer-master catalog studies for a new write. The order holds snapshot names, modality and context, so historical display/PDF remains coherent when catalog availability changes. Legacy or null/inactive specialty histories retain their historical specialty and may receive a permitted additional order without changing it.

## Security and lifecycle invariants

All order and document endpoints use backend clinical permission and history-access checks. The backend derives order context from the history and validates resource-to-history membership on updates/PDFs. It audits reads and writes where the existing access services require it. The frontend never sends authority fields and does not convert 403/409/422 into success.

Completed consultation behavior is deliberately split:

- legacy `RequestedTest`: immutable and readable; legacy PDF remains available;
- existing structured orders: immutable, readable and printable;
- structured additional orders: new append-only rows only through existing `/additional` endpoints and only for the responsible active doctor.

No clinical order, request, catalog selection, error, or document data is persisted in localStorage, sessionStorage, IndexedDB, analytics or a persistent client cache. Catalog cache use elsewhere remains limited to non-PHI bootstrap catalogs.

## Episode/race findings and 6B7A safety fix

Before 6B7A, `ClinicalOrdersSection` had independent `Promise.all` loads keyed by `historyId`/`specialtyId`, but no stale-result guard and no editor reset. Therefore a late load failure or success from history A could replace B state, and selections, notes and edit IDs could leak from A into B.

The minimal 6B7A fix adds a local request generation. A history/specialty change clears queries, selections, details, notes, edit mode, feedback and additional-choice state, then loads the new resource. Load, mutation follow-up, callback, error, busy and PDF completion paths publish only while their generation remains current. Cleanup invalidates the generation on unmount. This does not add a second bootstrap, modify HTTP endpoints, abort a write already sent to the server, retry, cache PHI, or redesign the UI.

Focused tests cover A → B reset, late-A success, late-A error, and unmount. A document request initiated for A is not downloaded or allowed to update UI after B becomes current; the request itself is not retried or transformed.

## Approved next direction, not implemented here

Phase 6B7B may make structured orders the preferred compact workflow: show summaries, offer **New order**, then choose **Laboratory** or **Study / Procedure** in a focused panel. That change must continue to use these contracts. Legacy `RequestedTest` remains compatibility/history and is not deleted or migrated by this phase.
