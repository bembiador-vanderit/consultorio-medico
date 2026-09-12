# Agenda profesional — UI V2 Fase 4A

Base: `feat/complete-care-context` en `eda6d7bdfb593d590f5fa469f393ba3a0a6f2d4c`.

## Alcance

La Agenda reemplaza la tabla como experiencia principal usando únicamente citas y
reglas ya expuestas por Atlas. `Appointments.tsx` coordina datos y mutaciones;
`components/agenda` separa navegación temporal, filtros, vistas, tarjetas,
drawer, badge de estado y formulario.

## Vistas y datos

- **Día** es la vista inicial. Solicita `GET /appointments?start=fecha&end=fecha`
  y presenta eventos por su hora registrada.
- **Semana** hace una única solicitud para siete días y agrupa sus resultados por
  día.
- **Médicos** agrupa solo las citas ya visibles para el usuario. No afirma que
  un médico sin citas esté disponible.
- El mini calendario navega fechas y el botón Hoy restaura la fecha actual.
- Centro y médico proceden de `GET /appointments/scope-options`; especialidad y
  estado filtran el rango cargado. Los filtros no alteran autorización.

No hay vista Mes en 4A: el endpoint aún no aporta paginación ni agregados
mensuales.

## Datos y acciones reales

Cada tarjeta y drawer muestra paciente, fecha, hora, especialidad, estado,
centro, médico, motivo, observaciones y cobertura cuando corresponda. La
especialidad pertenece a la cita, por lo que una jornada puede mezclar
Cardiología y Medicina Interna para el mismo médico.

El drawer reutiliza `PUT /appointments/{id}` para confirmar, cancelar, marcar no
asistió y reprogramar. Crear y editar conservan búsqueda protegida de paciente,
selección de centro, médico, especialidad y disponibilidad diaria. Iniciar
consulta solo aparece para quien tiene rol médico; la API mantiene la
verificación clínica.

## Roles, responsive y accesibilidad

La API sigue determinando scope de Médico, Secretaría, Administrador y roles
combinados. Secretaría no recibe datos clínicos; Administración no recibe acceso
clínico por su rol administrativo. La composición pasa de barra lateral y área
principal a una sola columna en tablet/móvil; las citas son tarjetas sin scroll
horizontal. El drawer usa el componente accesible compartido: foco inicial,
trampa de Tab, Escape, retorno de foco y etiquetas semánticas.

## Límites de 4A

No se representan duración, intervalos, huecos disponibles, recesos, bloqueos,
tipo de cita, llegada, inicio/fin, historial de reprogramación ni estados nuevos.
La futura 4B necesita duración, disponibilidad horaria, bloqueos, prevención de
solapamiento y filtros/paginación backend. La 4C puede construir timeline
proporcional, mes escalable y agenda avanzada sobre esas capacidades.