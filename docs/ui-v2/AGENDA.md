# Agenda profesional — UI V2 Fase 4A

## Corrección visual móvil vigente — PR #33

El marco desktop usa altura flex disponible después de la Topbar compacta,
sin el cálculo fijo de 77px; conserva la cuadrícula semanal, eje horario, estados
azul/verde/teal/coral/slate y tarjetas delimitadas. No cambia endpoints ni reglas.

Por debajo de 1024px, Calendario y filtros revela/oculta el mismo panel sin
requests ni controles duplicados; inicia cerrado para priorizar citas. Cambiar
fecha lo vuelve a cerrar, conservando filtros. Por debajo de 640px, Semana usa
una única lista de citas reales agrupada por día, con hora, paciente, motivo,
especialidad y estado legibles. Desde 640px vuelve a la cuadrícula sin nuevas
consultas. No crea duración, hora final, disponibilidad ni slots.

En tablet/móvil, los paneles de Semana, Mes y Médicos reutilizan el contenido
existente dentro del Drawer Foundation. Lista/detalle/← Citas del día cambian en
el mismo Drawer, con scroll interno, cierre, backdrop, Escape y retorno de foco.
La vista Día mantiene su Modal emergente y no se migra al panel lateral.
En móvil, encabezado y tarjetas se compactan; Inicio en la barra inferior ofrece
el retorno al Dashboard, sin repetir ese botón en el encabezado. El final de la
lista permanece alcanzable por encima de la barra inferior.

Base: `feat/complete-care-context` en `eda6d7bdfb593d590f5fa469f393ba3a0a6f2d4c`.

## Alcance

La Agenda reemplaza la tabla como experiencia principal usando únicamente citas y
reglas ya expuestas por Atlas. `Appointments.tsx` coordina datos y mutaciones;
`components/agenda` separa navegación temporal, filtros, vistas, una tarjeta
compartida, panel contextual, badge de estado y formulario.

## Vistas y datos

- **Día** es la vista inicial. Solicita `GET /appointments?start=fecha&end=fecha`
  y presenta una agenda compacta `Hora | Cita`; seleccionar una cita abre un
  modal con botón de cierre, Escape, retorno de foco y cierre por backdrop.
- **Semana** hace una única solicitud para siete días y usa una cuadrícula con
  eje horario. La escala empieza y termina en horas realmente registradas; no
  representa duración, disponibilidad ni slots. Cada cita conserva hora,
  paciente, motivo, especialidad y estado en una tarjeta compacta con texto
  contenido y color semántico.
- **Mes** hace una única solicitud desde el primer hasta el último día del mes y
  presenta una cuadrícula de seis semanas. Cada celda conserva la misma altura:
  muestra hasta tres citas y `+N más`, sin crecer con la cantidad de registros.
- **Médicos** agrupa solo las citas ya visibles para el usuario en filas compactas
  con la misma tarjeta, color y estado textual. No afirma que un médico sin citas
  esté disponible.
- El mini calendario navega fechas y el botón Hoy restaura la fecha actual.
- Centro y médico proceden de `GET /appointments/scope-options`; especialidad y
  estado filtran el rango cargado. Los filtros no alteran autorización.

Al elegir un día en Mes, o `+N más`, se abre el panel derecho **Citas del día**
con solo las citas ya autorizadas y filtradas. Elegir una cita transforma ese
mismo panel en su detalle; `← Citas del día` regresa a la lista y cerrar libera
el espacio para el calendario. No se abre un segundo panel ni se realiza una
consulta por día. En Semana, el encabezado de cada día abre esa misma lista y
una tarjeta abre el detalle en el mismo panel; el retorno solo aparece después
de entrar por la lista. Médicos abre directamente el detalle en esa misma
superficie. Día conserva su modal para no desplazar la agenda al consultar una cita.

## Datos y acciones reales

Cada tarjeta muestra hora, paciente, motivo resumido, especialidad y estado;
el panel de detalle muestra paciente, fecha, hora, especialidad, estado,
centro, médico, motivo, observaciones y cobertura cuando corresponda. La
especialidad pertenece a la cita, por lo que una jornada puede mezclar
Cardiología y Medicina Interna para el mismo médico.

El panel reutiliza `PUT /appointments/{id}` para confirmar, cancelar, marcar no
asistió y reprogramar. Crear y editar conservan búsqueda protegida de paciente,
selección de centro, médico, especialidad y disponibilidad diaria. Iniciar
consulta solo aparece para quien tiene rol médico; la API mantiene la
verificación clínica.

## Roles, responsive y accesibilidad

La API sigue determinando scope de Médico, Secretaría, Administrador y roles
combinados. Secretaría no recibe datos clínicos; Administración no recibe acceso
clínico por su rol administrativo. En escritorio Agenda ocupa el ancho útil tras
el shell: mini calendario, filtros y leyenda a la izquierda; calendario al centro;
y el panel derecho solo al seleccionar día o cita. La Agenda de Mes y las columnas
semanales contienen su propio scroll para aprovechar el viewport sin hacer crecer
la página. En tablet/móvil la composición pasa a una columna; el panel se sitúa
debajo del calendario con altura local limitada y las citas son tarjetas sin scroll
horizontal. Día usa un modal accesible y no recarga la Agenda al cerrarse; los
formularios conservan el mismo diálogo. Los detalles de Semana, Mes y Médicos no
dependen de un drawer ni de un modal.

## Límites de 4A

No se representan duración, intervalos, huecos disponibles, recesos, bloqueos,
tipo de cita, llegada, inicio/fin, historial de reprogramación ni estados nuevos.
La futura 4B necesita duración, disponibilidad horaria, bloqueos, prevención de
solapamiento y filtros/paginación backend. La 4C puede construir timeline
proporcional y agenda avanzada sobre esas capacidades.
## Correcciones pre-merge de PR #31

- La fecha seleccionada sigue a la cita guardada en las tres vistas. Un contador
  de refresco obliga a recargar incluso dentro de la misma semana. Drawer y
  tarjetas se reconcilian con la respuesta del rango vigente.
- Cada carga tiene una generación; las respuestas y errores anteriores se
  descartan. El contenido se oculta hasta que corresponde al rango actual y se
  vacía ante un fallo vigente.
- Los permisos visuales comparten `appointmentRules`. El backend sigue siendo
  la autoridad final. Médico puro no cambia paciente, centro ni médico desde la
  edición; la especialidad se conserva editable antes de consulta/cobertura,
  según el contrato actual.
- Cobertura protege contexto y especialidad. Secretaría sin rol Admin conserva
  la edición de fecha/hora cuando no hay historia clínica. Los datos de la cita
  no incluyen el intervalo de cobertura: la API valida el nuevo horario y sus
  errores aparecen en el diálogo activo. No se amplían scopes.
- Una historia iniciada impide ofrecer reprogramación, cancelación, no_show y
  eliminación. Atender requiere usuario activo, rol Médico y `doctor_id` propio,
  incluso para Médico+Admin y Médico+Secretaría.
- Los filtros reconcilian médico y especialidad al cambiar centro, médico y
  opciones de alcance. Médicos homónimos se agrupan por ID.
- Los cinco estados conservan texto y color en todas las vistas. Médicos permite
  columnas menores de 17rem en pantallas estrechas. Los controles de búsqueda
  tienen campos, IDs y etiquetas independientes; Agenda no anida otro `main`.
- Eliminar reutiliza la confirmación y `DELETE /appointments/{id}` anteriores,
  para citas no finalizadas, sin historia y sin cobertura. La nota adicional
  reutiliza `ClinicalHistoryPanel` con `initialAddendumHistoryId` y el endpoint
  existente; solo se ofrece al médico autor activo de una consulta completada.

### Deudas preexistentes conservadas

- Backend da precedencia a Secretaría sobre Médico en el alcance de Agenda;
  esta PR no cambia esa precedencia ni promete una unión completa de scopes.
- Las opciones de alcance pueden omitir al suplente de una cita transferida
  visible por autorización sobre el médico original. No se añaden opciones
  administrativas ampliando permisos desde frontend.
- Hoy usa la zona del navegador; la configuración del equipo debe coincidir con
  America/Santo_Domingo. Una política explícita para equipos de otras zonas queda
  pendiente y no forma parte de los MINOR seleccionados para esta corrección.
- `scope-options` se recarga con el rango. Un caché separado puede evaluarse si
  las mediciones lo justifican.

Los límites de 4A y las funcionalidades reservadas para 4B/4C no cambian.

## Identidad global de estados — misión 3C, PR #33

Appointment conserva exactamente cinco estados. Una única hoja
components/agenda/appointment-status.css define fondo, borde y texto para
AppointmentStatusBadge, tarjetas de Día/Semana/Mes/Médicos y leyenda; Dashboard
reutiliza el mismo badge. Este mapping sustituye la dirección anterior:

| Backend | Texto | Identidad |
| --- | --- | --- |
| scheduled | Programada | Azul |
| confirmed | Confirmada | Verde |
| completed | Completada | Teal/turquesa |
| cancelled | Cancelada | Coral/rojo |
| no_show | No asistió | Slate fuerte |

El color siempre acompaña el texto. Contraste texto/fondo >=4.5:1 en los cinco
estados. No se añaden estados, duraciones, horarios finales ni disponibilidad.
La estructura y lógica de carga de Agenda permanecen sin cambios.
