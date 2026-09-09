# Órdenes clínicas estructuradas

Atlas conserva las solicitudes libres existentes en `requested_tests` como formato legado. Las órdenes nuevas de laboratorio y de estudios/procedimientos se almacenan en estructuras independientes; no se convierten ni sobrescriben registros anteriores de forma implícita.

## Modelo y contexto

- `laboratory_tests` es el catálogo global de pruebas activas agrupadas por categoría.
- `laboratory_orders` y `laboratory_order_items` guardan cada orden y sus pruebas.
- `study_orders` y `study_order_items` guardan estudios/procedimientos, modalidad, región, contraste y observaciones clínicas.
- Las órdenes derivan `appointment_id`, paciente, médico, centro y especialidad exclusivamente de la historia clínica padre. El cliente no puede enviar ni sustituir ese contexto.
- Los nombres clínicos y administrativos relevantes se copian como instantáneas en la orden para que el documento histórico permanezca interpretable aunque cambie un catálogo o nombre posterior.

Cada guardado crea una orden explícita. Editar una orden solo modifica la orden elegida; nunca reemplaza otras órdenes de la consulta.

## Seguridad y ciclo de vida

Los endpoints pasan por la autorización de la historia clínica:

- solo el médico responsable con acceso clínico normal puede crear o editar mientras la consulta está `in_progress`;
- secretaria, administrador sin autoridad clínica, médico ajeno e IDs manipulados no conceden escritura;
- una cobertura delegada mantiene únicamente lectura según las reglas existentes;
- al completar la consulta, crear o editar devuelve conflicto y las órdenes existentes continúan visibles e imprimibles.

Una prueba o estudio inactivo no puede utilizarse en una orden nueva. Las órdenes existentes conservan sus ítems y sus instantáneas históricas.

## API

- `GET /laboratory-tests`
- `GET|POST /clinical-history/{history_id}/laboratory-orders`
- `PUT /clinical-history/{history_id}/laboratory-orders/{order_id}`
- `GET /laboratory-orders/{order_id}/pdf`
- `GET|POST /clinical-history/{history_id}/study-orders`
- `PUT /clinical-history/{history_id}/study-orders/{order_id}`
- `GET /study-orders/{order_id}/pdf`

Los PDF incluyen centro, paciente, médico, especialidad, fecha/hora, número de orden, indicaciones persistidas, observaciones y espacio de firma/sello. La historia longitudinal recupera las órdenes por consulta y permite reimprimir cada documento.

## Migración

`0026_clinical_orders` crea los catálogos y órdenes, carga el catálogo inicial de laboratorio y agrega estudios/procedimientos iniciales por especialidad activa. `medical_studies.seed_key` identifica únicamente los estudios agregados por esta migración, de modo que el downgrade no borra contenido previo del catálogo.
