# Atlas Document Designer V1

## Inventario previo

Los PDF clínicos existentes continúan en sus rutas y renderizadores actuales:
resumen de consulta y orden de estudios solicitados (`clinical_history.py`), receta
(`prescriptions.py`), órdenes de laboratorio y estudios (`clinical_orders.py`),
evaluación preoperatoria y examen físico (`clinical_patient_documents.py`), y
vista previa de formularios (`clinical_forms.py`). Los reportes de citas usan
`reports.py`. No se reemplazan ni se convierten versiones clínicas firmadas.
Finanzas ya tenía factura, cobro y cierre como registros, pero no PDF de factura,
recibo ni cierre. ARS, remesas, conciliación, CxC, aging, estados de cuenta y
otros reportes quedan inventariados como futuros tipos del catálogo; no se
prometen como PDF en V1.

## Arquitectura

`DocumentTemplate` identifica un tipo y alcance estable (organización, centro o
médico en centro). `DocumentTemplateVersion` guarda la configuración de
presentación inmutable al publicarse; un borrador por plantilla. Una nueva
publicación archiva la anterior y una edición posterior crea otra versión.
`DocumentTemplateAudit` registra creación, edición, publicación y acciones PDF.
La revisión `0066_document_designer` añade solo estas tres tablas, sin backfill
ni alterar importes. Su migración se valida en PostgreSQL temporal; no debe
aplicarse a la base oficial 0065 durante esta fase.

El orden de resolución es médico > centro > organización > Atlas predeterminada.
La interfaz V1 permite configurar organización y centro; el backend valida el
alcance médico y queda preparado para una futura interfaz. Solo se renderiza la
última versión publicada. Un borrador nunca cambia PDF emitidos desde el
perfil vigente. El catálogo clínico registra los PDF preexistentes sin
rediseñarlos.

El flujo financiero es `registro real → datos documentales → versión publicada
o default → renderer → PDF`. El renderizador no calcula saldos ni crea
movimientos: toma importes de facturas, cobros y cierres y usa los totales
canónicos de Caja. La factura es interna y no se presenta como comprobante
fiscal. Campos no registrados, como una referencia de transferencia o
descuentos/impuestos desglosados, no se inventan. Para tarjeta se usa la
prestadora y el lote que sí están registrados.

El PDF admite Carta/A4, orientación, márgenes, tipografía, logo y datos
institucionales, encabezado/secciones, color o solo negro con grises suaves y
ahorro de tinta. El preview HTML muestra datos sintéticos, y el PDF de muestra
usa el mismo renderer que los documentos reales. Las acciones Ver, Descargar,
Imprimir y Reimprimir permanecen separadas; imprimir usa el navegador y no
dispara impresión automática al cobrar/facturar/cerrar. Ninguna reimpresión
modifica Caja, saldo, pago ni factura.

## Seguridad y límites V1

Los permisos separados son `documents:view`, `documents:pdf`,
`documents:print`, `documents:reprint`, `documents:manage` y
`documents:publish`. La administración recibe gestión/publicación, secretaría
solo lectura/PDF/impresión/reimpresión y médico no recibe permisos documentales
financieros por defecto. Además se exigen permisos y alcance financiero de
centro existentes. La sesión tenant filtra plantillas, versiones, auditorías y
registros financieros; conocer un ID ajeno no da acceso.

La UI definitiva es un solo módulo, Administración → Personalización →
Documentos, con modo normal y acceso interno al Diseñador avanzado. Este último
es foundation, no editor libre. Quedan pendientes el editor por bloques,
variantes POS 80/58 mm, media carta, gestión de firma profesional en PDF
financiero, más tipos ARS/reportes y un agente de impresión local.
