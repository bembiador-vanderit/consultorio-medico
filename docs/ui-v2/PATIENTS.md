# Pacientes — Atlas UI V2, fase 5

Base: `feat/complete-care-context` en `5012dfce894b63710745246d6d634c15b75bb078`, con las correcciones de seguridad/integridad de PR #32 ya incluidas.

## Workspace master/detail

Patients conserva su integración con App y la navegación por estado. PageHeader, Button, Card, FormField, Input, Select, Alert, EmptyState, LoadingState, Modal y Drawer pertenecen a la fundación vigente. El CSS de composición usa tokens Atlas y un acento azul para Agendar cita; incorpora tokens tonales violeta para Seguro y conserva la biblioteca de iconos existente.

La lista compacta sustituye la tabla de acciones. Cada registro es un botón con iniciales locales, nombre, edad calculada, nacimiento, teléfono y correo. El estado seleccionado usa texto, color, borde y aria-pressed. Enter/Espacio funcionan como botones nativos; el foco es visible. La ficha permite scroll local del resumen cuando hay datos extensos, conservando visibles las acciones.

Desktop mantiene lista y ficha lado a lado. La lista domina aproximadamente el 62% del área; la ficha ocupa aproximadamente 38%, con tracks minmax(0,1.65fr) / minmax(18rem,1fr). Al no seleccionar un paciente se muestra un estado vacío contextual. Nombre/contacto extensos se delimitan en las filas. En la ficha desktop, nombre de hasta tres líneas con title completo y contacto con ajuste de línea; en móvil, nombre completo. Las acciones se concentran debajo de los datos, sin navegar a otra página de ficha.

La corrección visual del mismo PR #33 incorpora cabeceras tonales, iconos de
acción y acentos azul/Sage/violeta usando tokens vigentes. El Shell de 224px y
Topbar compacta dejan más espacio útil; tablet reserva la barra inferior en su
altura disponible y la lista móvil conserva su margen final. Búsqueda, selección,
alta/edición, seguro y prueba de selección mantienen sus contratos y tests.

## Datos reales

La respuesta actual de GET /patients aporta id, first_name, last_name, date_of_birth, phone, email y created_at. El workspace muestra únicamente nombre, nacimiento y contacto, más iniciales/edad derivados localmente. No presenta created_at del adaptador de búsqueda como fecha real.

La edad no se almacena ni se envía. Se calcula desde DOB sin convertir fechas a UTC; considera si el cumpleaños ya pasó en el año actual. Un DOB inválido o futuro muestra “Edad no disponible”, sin inventar un valor.

No se añaden cédula, sexo, dirección, ocupación, estado civil, sangre, alergias, última visita, próxima cita, médico ni especialidad a la ficha. Seguro e historia no se deducen de la respuesta de pacientes.

## Búsqueda y ordenamiento

Una carga principal de GET /patients conserva query recortado y limit=100. La búsqueda es server-side por nombre, apellido o teléfono, conforme al endpoint actual. Buscar envía la consulta; Limpiar restablece el campo y vuelve a cargar sin query. La UI diferencia un registro vacío de una búsqueda sin resultados.

El selector de orden mantiene los cuatro campos anteriores: nombre, nacimiento, teléfono y correo, con ambos sentidos. Solo ordena el conjunto recibido; “Orden del servidor” conserva el orden backend. La UI informa registros mostrados y el límite, sin presentarlos como una métrica global.

Respuestas de consultas antiguas no reemplazan una búsqueda posterior. Error/rechazo backend elimina filas/ficha obsoletas y ofrece Reintentar. Seleccionar o cerrar ficha no recarga pacientes; cancelar formulario conserva consulta y selección. Tras guardar una edición se actualiza la ficha y se recarga la búsqueda aplicada.

## Acciones y roles

| Contexto | Acciones de ficha | Historia |
| --- | --- | --- |
| Doctor | Agendar cita, Editar, Seguro | Visible; endpoint sigue aplicando scope clínico |
| Secretary | Agendar cita, Editar, Seguro | No se monta ni consulta |
| Admin | Agendar cita, Editar, Seguro | No se monta ni consulta por ser admin |
| Multirol con doctor | Unión de acciones actuales | Mismo guard doctor; admin no amplía alcance clínico |

No se inventa un permiso frontend nuevo: se mantiene el guard actual y backend sigue siendo la frontera de autorización. Patient visibility scope, center scope, specialty y coverage no cambian.

Agendar cita utiliza el callback vigente hacia Agenda con el mismo paciente y su selection_token si existe. Crear un paciente desde doctor/secretary mantiene el alta seguida de primera cita. Admin conserva el refresco del listado tras crear. Elegir identidad existente conserva la prueba firmada y no crea un duplicado.

## Formularios y paneles existentes

PatientForm conserva alta, búsqueda de identidad exacta, validación, creación/edición, seguro, conflictos 409 y reutilización de selection_token. Se alinea con FormSection/FormField y Modal: etiquetas/IDs únicos, radios mutuamente excluyentes Sí/No, validación nativa, cabecera/cierre y pie de acciones disponibles, cuerpo con scroll local. El botón Guardar externo se asocia al formulario por su ID.

En edición, seguro intacto se omite del payload. Cambiar seguro envía objeto explícito; seleccionar No envía false explícito. Si falla la carga de seguro, se muestra advertencia y se impide modificar sus controles, permitiendo editar identidad con seguro omitido. No se convierte un fallo de lectura en desactivación. Esta adaptación usa la semántica backend de PR #32, sin cambiar contrato ni endpoints.

PatientInsurancePanel conserva consultas bajo demanda, agregar/desactivar afiliación y administración de ARS solo por admin. Sus filas se presentan como cards para evitar tabla ancha en móvil. Se conservan afiliado, plan y estados reales, incluido Principal; desactivación mantiene la confirmación y el DELETE anteriores. Modal proporciona cierre, Escape y retorno de foco; no se reconstruye la arquitectura de seguros.

ClinicalHistoryPanel conserva su lógica y endpoints. Solo desde Patients se utiliza su modo embedded dentro de Modal, sin un segundo overlay fijo. Los usos anteriores en Agenda mantienen la presentación previa. No se rediseñan consulta, órdenes, PDFs, especialidades ni timeline clínico.

## Responsive y accesibilidad

- Desde 1024px: master/detail junto al Sidebar. El marco de Pacientes ocupa el espacio restante del viewport según la altura real de Topbar, sin límite general de ancho ni margen central grande. Lista y ficha desplazan internamente.
- Entre 1024 y 1365px: contacto pasa debajo de la identidad para conservar un ancho útil. Agendar e Historia clínica ocupan el ancho de la ficha; Editar/Seguro comparten fila para mantener densidad y accesibilidad.
- Menos de 1024px: lista de ancho completo y ficha dentro del Drawer contextual de la fundación, con cierre visible, backdrop, Escape y foco restaurado. El detalle se conserva en estado al cerrar. Desde 640px, también la lista tablet aprovecha la altura restante del marco con scroll local.
- Menos de 640px: cards compactas, búsqueda/botones apilados, selector accesible y formulario de una columna. Se permite scroll vertical natural de la lista móvil; no depende de scroll horizontal.
- Formulario de 320px: cuerpo con scroll local y pie/cierre disponibles, sin tabla ni campos de ancho fijo.

Modal/Drawer reutilizan dialog nativo, fondo inerte, foco inicial, ciclo de Tab y scroll lock compartido para overlays anidados. Cancelar/cerrar vuelve a la ficha o registro que abrió el módulo cuando ese elemento continúa montado. El drawer cierra al pasar a desktop y la ficha permanece seleccionada.

## Acceso por localhost y por IP

La API del navegador usa `/api/v1` en el mismo origen del frontend. Por tanto, abrir Atlas por `localhost` conserva llamadas a localhost y abrirlo por la IP de la PC conserva esa IP. Vite dev/preview reenvían la ruta al backend; Docker Compose configura únicamente el frontend con `API_PROXY_TARGET=http://backend:8000`. Vite local fuera de Docker utiliza por defecto `http://localhost:8000`, configurable con API_PROXY_TARGET.

No se cambia CORS, autenticación ni permisos backend. La configuración explícita VITE_API_URL sigue disponible para despliegues con API separada; ese modo requiere la política CORS correspondiente. En un despliegue estático distinto de Vite, el servidor web debe reenviar `/api/v1` al backend.

localhost y la IP son orígenes de navegador distintos: cada dirección mantiene su propia sesión; ambas operan sobre el mismo backend. La prueba en navegador de la IP se realiza desde la misma PC, sin certificar firewall o conectividad desde otro dispositivo.

## Performance y deuda futura

No hay N+1: render/selección del listado no consultan seguros, citas ni historias por paciente. Seguro carga solo el paciente pulsado y el catálogo de compañías; historia carga solo el paciente seleccionado cuando un doctor pide la acción. Las consultas clínicas internas existentes siguen limitadas al flujo de historia solicitado.

FUTURE: server-side pagination, sorting server-side y revisión de escalabilidad para 1k/10k pacientes. El límite de 100 permanece explícito; el orden local no se presenta como orden global. No se añade paginación backend.

La prueba de selección conserva su expiración/alcance de PR #32. No se introduce renovación automática, MPI, merge de pacientes, nuevos campos demográficos ni datos simulados en producción.

La revisión visual usa datos ficticios y API interceptada en navegador; valida composición/interacción y cantidad de requests del frontend, sin certificar permisos contra una base operativa. Los tests de contrato y la autorización backend existente siguen siendo necesarios.

## Polish final — misión 3C, PR #33

La identidad prioriza avatar y nombre completo con caption discreto, edad y
nacimiento desktop. Información personal y Contacto se agrupan; teléfono y
correo aprovechan todo el ancho, con overflow-wrap:anywhere. Desktop usa dos
filas de acciones; móvil conserva Agendar cita e Historia clínica a todo el
ancho y Editar/Seguro en dos columnas, con targets de 44px y guard médico intacto.
Agendar cita es azul, Historia sage, Seguro violeta suave y Editar outline.
El encabezado estático del Drawer recibe foco sin dibujar un borde alrededor
del título; los controles interactivos conservan su indicador de foco.
