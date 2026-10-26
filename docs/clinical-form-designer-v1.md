# Diseñador de formularios clínicos V1 (0056)

Esta fase prepara 0056; **no se aplica a la base oficial durante la implementación**. La interfaz nueva permanece oculta mientras `VITE_CLINICAL_FORM_DESIGNER_ENABLED` no sea `true`. La activación requiere migrar la base primero y fijar `ALEMBIC_TARGET_REVISION=0056_clinical_forms` en la configuración local apropiada.

## Separación de responsabilidades

- `clinical_form_templates`: identidad, tipo de documento, estado y versión publicada actual.
- `clinical_form_versions`: definición validada e inmutable después de publicar. Su JSON reúne páginas, secciones, campos y apariencia para que una publicación sea atómica. No contiene valores de pacientes.
- `clinical_form_assignments`: ámbito organización, centro, especialidad+centro o médico+centro. La clave normalizada evita duplicados incluso cuando algunos componentes de ámbito son nulos.
- Documentos 0055: mantienen su ciclo de vida, contenido, firma y auditoría. Los nuevos campos `template_id` y `template_version_id` son nulos para documentos anteriores (fallback explícito `legacy_0055`). Los documentos vinculados conservan la versión publicada elegida al crearse, incluso si después se publica otra versión o se retira la plantilla.
- `secretary_document_grants`: inicio de preoperatoria, inicio de examen físico y preparación administrativa independientes y desactivados por defecto. Además siguen aplicando `denied_permissions`, tenant, centro, alcance médico y prueba de selección de paciente.

La resolución para documentos nuevos es: médico+centro > especialidad+centro > centro > organización > formulario legado 0055. Entre varias especialidades aplicables del mismo nivel vence la asignación más reciente por ID; el administrador debe evitar esa ambigüedad. No se reescriben documentos anteriores al cambiar una asignación.

## Versiones y edición

Crear produce v1 borrador. Editar una versión publicada está prohibido: se crea un nuevo borrador a partir de la versión vigente. Publicar valida páginas, secciones, claves únicas, tipos, opciones, valores iniciales y vínculos Atlas permitidos. Retirar impide nuevas asignaciones; no altera documentos firmados. Duplicar crea otra identidad de plantilla con v1 borrador independiente. La publicación y la asignación generan auditoría administrativa.

Las páginas se numeran `1..N`, con tamaño A4 o Carta, orientación y márgenes propios. No existe propiedad clínica de “frente/reverso”; la impresión a doble cara se configura en la impresora. La vista previa usa exclusivamente identidades ficticias. El PDF de CEMER ocupa dos páginas Carta con la configuración inicial y valores normales. Si el contenido libre excede el área disponible, el renderizador rechaza el PDF en vez de recortar texto silenciosamente; el diseñador debe ajustar densidad, márgenes o páginas.

## Catálogo inicial

La acción administrativa “Crear evaluación CEMER” prepara un borrador de dos páginas con los rótulos corregidos HEPATITIS, OTROS, GLICEMIA y CREATININA. “Crear examen físico CEMER” prepara una plantilla independiente. PCB e IVY siguen siendo rótulos configurables, sin interpretación clínica. Las etiquetas pueden estar en mayúsculas sin transformar valores médicos. El administrador revisa, publica y asigna explícitamente cada plantilla; no se crean asignaciones ni documentos retroactivos.

## Captura y permisos

El ejecutor usa controles compactos según tipo: Sí/No, número, fecha/hora, selección o texto. El orden de Tab sigue página, sección y fila/columna; los vínculos Atlas son de solo lectura. Los campos con `editable_by=administrative` pueden prepararse únicamente con la concesión individual; los campos clínicos y la firma requieren médico autorizado. El backend valida todo otra vez; la UI no es autoridad. No se aceptan JavaScript, expresiones ni URLs remotas de plantilla. Los logos son PNG/JPEG en tamaño limitado dentro de la versión inmutable.

Un borrador versionado admite guardado parcial. Al completar, solo se exigen los campos marcados como requeridos en su versión de plantilla; el formulario legado 0055 conserva su validación mínima de contenido clínico. Un intento de editar un documento firmado se rechaza y registra como conflicto en la auditoría clínica, sin almacenar los valores rechazados.

## Limitaciones V1

- No hay tablas repetibles, escalas ni fórmulas clínicas arbitrarias.
- El PDF no controla dúplex físico; ofrece páginas numeradas. En el navegador se puede imprimir todo o elegir la página actual mediante las opciones del sistema de impresión.
- Un documento legado 0055 conserva su presentación anterior. No se “convierte” en secreto a una versión CEMER.
- El catálogo CEMER se instala como borrador por un administrador después de activar 0056; ninguna plantilla se instala automáticamente durante la migración.

## Composición responsive del runner V2

El renderer moderno y la vista previa comparten `ClinicalFormRunner`. Las coordenadas explícitas `row`, `column`, `width` y `colspan` conservan su prioridad, incluso en campos narrativos. El orden del DOM/Tab sigue fila, columna y orden de plantilla; no se usa `grid-auto-flow: dense` ni reordenación visual de controles.

La definición V1 no tiene coordenadas de sección. Solo cuando conserva los valores predeterminados sin diseñar, el runner deriva una composición por tipos: campos cortos compactos, narrativas consecutivas en pareja y narrativas aisladas a ancho completo. Dos secciones binarias consecutivas pueden compartir fila cuando el formulario dispone de 48 rem. Un bloque binario sin pareja puede situar sus notas al lado desde 44 rem. No depende del nombre del campo, centro o plantilla, ni modifica el JSON guardado.

Las container queries miden el espacio real de cada área, también dentro del modal o de una sección reducida. Desde 44 rem se aplican las 12 columnas y posiciones de escritorio; entre 32 y 44 rem los compactos usan hasta tres columnas y las parejas medianas conservan dos. Por debajo, los campos cortos siguen a dos columnas y las narrativas ocupan toda la fila. Áreas menores de 15 rem reducen los campos ordinarios a una columna; los bloques Sí/No usan ajuste automático y las etiquetas extensas toman una fila propia en áreas menores de 18 rem. Los botones conservan 44 px de alto mínimo y los sufijos de unidad no se parten.

Este ajuste es exclusivamente de presentación del renderer moderno. No altera plantillas, valores, persistencia, identidad de borradores, PDF, permisos ni la presentación legacy 0055.
