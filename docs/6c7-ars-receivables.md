# 6C7 — Reclamaciones y cuentas por cobrar ARS

## Alcance y modelo

La reclamación nace **solo** de una cobertura 6C5 en DOP con monto ARS positivo y aseguradora identificada. Una cita puede tener una reclamación; repetir la creación devuelve conflicto. Si ya existe una factura 6C6 vigente, se usa su importe ARS y su fotografía histórica, aunque la cobertura se haya editado después; el operador confirma la revisión histórica de la factura. De lo contrario se copia la cobertura vigente de la cita, con revisión optimista. La reclamación conserva organización, centro, paciente, cita, cobertura, aseguradora/plan, fecha del servicio, nombre del paciente, servicio, importes, autorización y fotografía de afiliación. Cambios posteriores de catálogos o cobertura no reescriben esta copia. Una factura posterior no puede contradecir una reclamación vigente y una factura vigente no puede anularse antes de cancelar la reclamación; ambos flujos se serializan por cita. No hay backfill: la migración agrega tablas vacías.

`ars_claims` contiene el estado de trámite y los importes acumulados. `ars_claim_events` conserva actor, momento, transición, código, motivo e importe de cada evento. `ars_remittances` registra el pago recibido de la aseguradora, referencia única por ARS y organización, fecha, importe y saldo sin aplicar. `ars_applications` reparte la remesa entre reclamaciones y registra sus reversos sin borrar filas. Ninguna de estas entidades usa caja, movimientos de caja ni el saldo del paciente. Todos los montos son DOP decimales de dos posiciones; el API los entrega como cadenas.

## Estados y correcciones

Flujo permitido:

```text
borrador → pendiente de enviar → enviada → recibida/en revisión
                                  ↘ glosada o rechazada → corregida → reenviada → recibida/en revisión
```

Una enviada o reenviada también puede recibir glosa/rechazo directamente. Cualquiera de los estados de trámite, salvo cancelada, puede cancelarse **solo sin pagos aplicados** y con motivo. No se salta de borrador a enviada ni se corrige una reclamación no glosada/rechazada. El estado de pantalla `pago parcial` o `pagada` se deriva de los pagos; el estado de trámite permanece para conservar el historial. Al revertir un pago reaparece el estado de trámite anterior. El reenvío actualiza la fecha de último envío; eventos anteriores permanecen.

Reclamado = aprobado + glosado cuando la ARS emite una decisión. Si aún no hay aprobación, el cobrable provisional es reclamado menos glosado. Pendiente = cobrable menos pagado, nunca negativo. Una glosa o corrección no puede reducir aprobado por debajo de pagos ya aplicados. La corrección cambia el aprobado y glosado con motivo e historial; no modifica el reclamado original, la factura ni la cobertura. No se editan campos financieros mediante un `PUT` libre.

## Pagos, conciliación y reportes

La remesa identifica aseguradora y opcionalmente centro. Una remesa sin centro solo la registra y consulta un administrador; permite repartir entre centros de la misma organización. Cada aplicación exige misma aseguradora, centro coherente cuando la remesa lo tiene, reclamación enviada/recibida/glosada con saldo, y monto positivo que no exceda el saldo de la reclamación ni de la remesa. Se bloquea primero la remesa y luego las reclamaciones en orden de ID para serializar aplicaciones concurrentes. Un reverso marca la aplicación, devuelve el saldo a remesa y reclamación, conserva el original y exige motivo. Sobrantes permanecen **sin aplicar** en la remesa; no son crédito automático a pacientes ni a reclamaciones futuras.

`GET /api/v1/ars/claims` ofrece filtros por aseguradora, estado, paciente, centro y fechas de servicio; detalle incluye cobertura original, eventos y aplicaciones. `GET /receivables` lista saldos abiertos, fecha, paciente, centro, estado y aging 0–30, 31–60, 61–90, 90+ días. `GET /reconciliation` agrupa por aseguradora y período **de fecha de servicio**, con reclamado, aprobado explícito, cobrable provisional, pagado, glosado y pendiente. La ausencia de aprobación no se reporta como monto aprobado. Una remesa recibida en un período posterior se atribuye en ese resumen al período de servicio de sus reclamaciones; el listado de remesas usa su propia fecha de recepción. Los reportes son operativos, no asientos de contabilidad ni reconocimiento fiscal.

## Permisos, aislamiento y auditoría

Se agregan `ars:read`, `ars:claim`, `ars:send`, `ars:glosa`, `ars:payment`, `ars:reconcile` y `ars:report`. El administrador recibe estas capacidades; médico y secretaría no las heredan automáticamente. 6C3 permite denegación individual. Cada ruta exige su capacidad y el backend aplica el contexto de organización del host; listas y búsquedas se limitan además a centros autorizados. Las referencias cruzadas se validan antes de escribir y `TenantOwned` refuerza organización en cada FK. Los eventos y `security_audits` registran actor, organización, centro, tipo de operación y entidad sin copiar números de afiliación o autorización a la auditoría de seguridad.

## Migración y límites

`0039_ars_receivables` agrega cuatro tablas, índices, restricciones y capacidades; no modifica filas 6C5/6C6 ni inventa reclamaciones del piloto. Aplicar con respaldo y código coordinado; downgrade elimina datos de 6C7 y solo corresponde a bases desechables. `scripts/check_ars_migration.py` prueba upgrade, downgrade, reaplicación, preservación de una cita sintética y un ciclo de pago/reverso en PostgreSQL desechable.

Límites menores: un servicio y una ARS por cita, sin envío a portales ni importación automática de remesas; la aplicación es manual, sin crédito automático ni conciliación bancaria. Listados HTTP paginados a 100 y reportes agregados sin materialización; exportación PDF, BI avanzado y revisión visual con usuarios quedan pendientes. No se incluyen DGII/e-CF, fiscalización dominicana, Device Hub ni Cardiología específica.
