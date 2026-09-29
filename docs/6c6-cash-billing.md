# 6C6 — Caja / Facturación

## Base y alcance

Base `d04de23c62186a465abd48b38699940c4d0e3721`, merge de PR #51 hacia `feat/complete-care-context`. Se verificó PR abierto, mergeable y CI aprobada para `96a8ed2d84a9a4291aacdbab4238564e8fa2a8ff`; la integración exigió ese SHA. Rama `feat/6c6-cash-billing`. No se modifica main ni se despliega. Cardiología permanece pausada.

## Reglas operativas

- Una caja abierta por organización, centro y responsable. Dos cajeros pueden operar cajas separadas en el mismo centro. Una persona puede tener una por centro. Índice único parcial más bloqueo del centro serializan aperturas. El fondo inicial no es un cobro.
- El responsable opera su caja; un usuario con `finance:manage` puede supervisar otra caja del centro autorizado. Un cierre es definitivo: no se reabre ni edita. Para cobrar o devolver después, abrir otra caja. Las operaciones se registran en UTC; las consultas por día usan la zona de la organización. La interfaz muestra timestamps en la zona del dispositivo; el filtro inicial toma su fecha local.
- DOP exclusivamente. Importes decimales exactos de hasta 12 dígitos y 2 decimales; JSON usa cadenas. Ningún pago puede exceder el saldo. No se generan créditos, cambio de efectivo ni saldos a favor. Se registra el importe aplicado, no el billete entregado.
- Una operación puede contener efectivo, tarjeta, transferencia, cheque y otro, con una línea positiva por método. Su suma es el único cobro. No hay conexiones bancarias ni captura de números de tarjeta.
- Puede emitirse una factura pendiente sin caja; recibir pagos exige caja abierta. La creación con pago es atómica: si el pago falla, no queda factura nueva. Cobros posteriores se aplican al mismo documento y conservan su saldo e historial.
- Un servicio/concepto por factura. Una factura vigente por cita, reforzada por índice único. Sin cita, el operador registra un servicio particular y tarifa; no se deduce cobertura automáticamente del seguro del paciente. Para utilizar seguro, seleccionar una cita con cobertura 6C5. Pacientes nuevos siguen su registro/selección autorizada existente; Finanzas busca identidades ya visibles al usuario.
- Se copia la cobertura de la cita al facturar, incluidos importes, afiliación y autorización. La revisión debe coincidir con la que vio el cajero. El backend determina la parte ARS y el copago; el cliente no puede inventarlos. Una cobertura no DOP o una cita cancelada/ausente se rechazan.
- Cambiar 6C5 posteriormente no recalcula documentos emitidos. Para corregir una factura: revertir sus pagos, anularla con motivo, corregir cobertura y emitir otra. Una cita con cualquier historial financiero conserva paciente, médico y centro y no se elimina. El estado clínico y el estado financiero siguen independientes.
- El importe esperado de ARS **nunca** es ingreso de caja. Es la expectativa bruta copiada de 6C5, incluso si la autorización está pendiente; no es garantía de pago ni reclamación aprobada. La autorización no recalcula la cobertura automáticamente.
- El deducible, si existe, debe estar incluido por el operador en la obligación/copago del paciente de 6C5. No se crea otro cargo ni se calcula una política de deducible separada en esta fase.

## Modelo y estados

| Entidad | Contenido y propósito |
| --- | --- |
| `cash_registers` | Organización, centro, responsable, estado abierta/cerrada, fondo, notas, timestamps, usuario que cierra, contado, esperado y diferencia del cierre. |
| `financial_invoices` | Organización, centro, paciente y nombre histórico, cita/cobertura opcionales, fotografía de cobertura, concepto, total, parte ARS, obligación y pago neto del paciente, autor, fecha y anulación. |
| `cash_movements` | Organización, centro, caja, factura cuando aplica, tipo, monto positivo, componentes por método, actor, fecha, motivo y vínculo al cobro revertido. UUID de petición y huella del payload. |

Número interno `INT-{organización}-{id de factura con 8 dígitos}`: único, puede tener huecos; no es secuencia fiscal. `pending` = sin pagos y con saldo; `partial` = pago neto mayor que cero y saldo pendiente; `paid` = paciente saldado, aunque ARS continúe esperada; `void` = documento anulado. El saldo del paciente se calcula como obligación menos pagos netos, cero para documentos anulados. Los importes originales permanecen visibles en la factura anulada; su ARS esperada vigente es cero.

No hay UPDATE ni DELETE público de movimientos. Un reverso completo copia los métodos originales y disminuye el pago neto de la factura. Solo puede revertirse un cobro una vez; una restricción única lo respalda. Se exige motivo y caja abierta del mismo centro; puede ser una caja posterior. Se conserva íntegro el cierre original y la salida se registra en la caja actual. Reaplicar requiere un cobro nuevo con su UUID, contra el saldo reabierto. No se incluyen devoluciones parciales ni reemplazo del método del reverso. Los ajustes son entradas/salidas de **efectivo** con motivo; no liquidan facturas ni cambian saldos del paciente.

Efectivo esperado = fondo + cobros en efectivo − reversos en efectivo + ajustes de entrada − ajustes de salida. Diferencia = contado − esperado. Observación obligatoria si la diferencia no es cero. Tarjeta, transferencia, cheque y otro se muestran por separado y no alteran el efectivo esperado.

## Seguridad, permisos y concurrencia

Se reutilizan permisos efectivos y restricciones individuales 6C3, visibles en Seguridad:

| Capacidad | Rol inicial | Alcance |
| --- | --- | --- |
| `finance:read` | Admin, secretaría | Cajas, documentos, balances y movimientos de los centros autorizados. |
| `finance:collect` | Admin, secretaría | Apertura/cierre, emisión de documentos y aplicación de pagos; requiere lectura. |
| `finance:manage` | Admin | Ajustes, reversos, anulaciones y supervisión de otras cajas; requiere lectura. |

Doctor solo no recibe ninguna capacidad financiera. Admin accede a centros de su organización; otros usuarios solo a centros activos asignados. La lectura financiera es una capacidad de centro, no una extensión de acceso clínico: incluye sus saldos y documentos, sin historias clínicas. La emisión mantiene además el alcance existente de identidad y de cita/médico. La autoridad de plataforma no concede acceso por sí sola. Las capacidades pueden revocarse individualmente en Seguridad mediante el flujo protegido existente.

Todas las entidades son `TenantOwned`: sesiones ligadas al host filtran consultas y validan organización en escrituras/FKs. El cliente no suministra organization_id. Se valida centro en cada recurso y coherencia paciente/cita/centro/caja. No hay RLS frente a SQL privilegiado externo, igual que 6C4.

Bloqueos PostgreSQL: caja antes de cita/factura; todas las operaciones de caja comparten ese bloqueo con el cierre. El bloqueo de factura serializa pagos de distintas cajas y los reversos/anulaciones. UUID más huella y autor permiten repetir exactamente una petición sin cobrar dos veces, incluso después de cerrar la caja; reutilizarla con otros datos devuelve 409. La UI conserva la confirmación y su UUID para reintentar tras un fallo. Para operaciones sin cita, una nueva referencia es un servicio nuevo: antes de recrear un formulario tras pérdida de conexión, consultar Facturación.

Auditoría transaccional en `security_audits`: apertura, cierre, emisión, pago, reverso, ajuste y anulación con actor, organización, centro y entidad. Los movimientos mantienen motivo, método e importe original; la factura conserva fotografía histórica. No se copian datos sensibles de afiliación a los logs de seguridad. La auditoría de aplicación no es un registro inviolable frente a administradores de base.

## API y UI

Prefijo `/api/v1/finance`:

- `GET /centers`, `/patients?q=&center_id=`, `/appointments?center_id=&patient_id=`, `/preview`: selección y contexto mínimo administrativo.
- `GET/POST /registers`, `GET /registers/{id}`, `POST /registers/{id}/close`, `/adjustments`.
- `GET/POST /invoices`, `GET /invoices/{id}`, `POST /invoices/{id}/payments`, `/void`.
- `GET /movements`, `POST /movements/{id}/reverse`, `GET /summary`.
- Listas de documentos y movimientos con offset/limit (máximo 100). Pendientes con `pending=true`. Día interpretado en la zona organizacional. Facturas y saldos acumulados no se limitan al día del resumen.

Finanzas reutiliza shell, formularios, tarjetas y colores Atlas. Incluye Caja, Facturación, Movimientos del día y Cuentas pendientes de pacientes. Nuevo cobro permite elegir paciente/cita, ver cobertura, distribuir pago y confirmar. El detalle financiero muestra documento y todos los movimientos; supervisores pueden revertir/anular con motivo. No depende del cierre clínico.

## Migración y validación

`0038_cash_billing` posterior a `0037_insurance_coverage`: tres tablas aditivas, FKs, checks, índices y capacidades. No genera documentos/cobros ni modifica historias del piloto. Aplicar `alembic upgrade head` con respaldo y actualización coordinada del código cuando se autorice despliegue. Downgrade solo en bases desechables: elimina la información financiera de esta fase; no es recuperación del piloto.

`check_finance_migration.py` exige PostgreSQL vacío, prepara cobertura 6C5 sintética, verifica preservación y ausencia de cobros inventados, downgrade a 0037 y reaplicación. La CI ejecuta además las migraciones anteriores y regresiones completas. `test_finance_6c6.py` cubre contratos y aislamiento HTTP; `test_finance_concurrency.py` requiere `FINANCE_POSTGRES_URL` apuntando exclusivamente a `finance_concurrency_test`. Pruebas de UI en `finance.test.mjs`, mediante DOM simulado.

Validación local: 367 pruebas backend completas, sin omitidas, incluyendo cuatro nuevas carreras PostgreSQL; después, 15/15 casos HTTP financieros con dos regresiones adicionales de permisos y zona horaria. Frontend completo 297/297, sin omitidas, con 12 casos de Finanzas. Compilación TypeScript/Vite correcta. El script de migración verificó además un cobro mixto parcial y cierre sobre el esquema realmente migrado. La CI del PR repite las suites finales, migraciones y build.

## Límites y 6C7

Fuera de alcance: reclamaciones ARS, CxC formal de aseguradoras, liquidación/conciliación de pagos ARS, remesas/lotes, DGII/e-CF/NCF, impuestos, descuentos, integración bancaria, contabilidad de doble partida, múltiples conceptos por documento, divisas, Device Hub y Cardiología específica. 6C7 deberá consumir el importe y la fotografía de cobertura, introducir el ciclo de reclamación y su propio historial sin registrar montos ARS como pagos de paciente.

Deuda menor: últimas 100 cajas en selector (incluye abiertas primero; sin búsqueda de cierres antiguos), hasta 100 citas recientes por paciente, agregados calculados a partir de movimientos y búsqueda de pacientes por nombre limitada a 20 resultados. Sin exportación PDF/impresión dedicada. UUIDs pendientes no sobreviven al cierre del navegador; consultar Facturación antes de recrear una operación. La revisión visual y de accesibilidad completa del piloto queda para validación con usuarios.
