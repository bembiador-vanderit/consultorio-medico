# Dashboards por rol — UI V2 fase 3

Base: `feat/complete-care-context` en
`1e8ee60f5d3fe5833f711818b03e6b449d2adf3a`.

## Objetivo y estructura

Atlas conserva un único Dashboard dentro del App Shell operativo. La página
compone una bienvenida, tarjetas de métricas reales, agenda del día,
notificaciones y acciones rápidas. Los bloques se agregan según los roles del
usuario; no hay aplicaciones ni shells separados por rol.

`Dashboard.tsx` coordina las cargas y estados. `components/dashboard` mantiene
las tarjetas reutilizables y la matriz declarativa de acciones/resúmenes por rol.
La visibilidad mejora el descubrimiento; las rutas y datos siguen protegidos por
el backend.

## Datos reales reutilizados

| Dato | Endpoint | Usuarios que lo solicitan |
| --- | --- | --- |
| Pacientes disponibles | `GET /patients/count` | Usuarios autenticados |
| Agenda de hoy | `GET /appointments?start=YYYY-MM-DD&end=YYYY-MM-DD` | Usuarios autenticados, con scope del backend |
| Notificaciones | `POST /follow-ups/notifications/sync`, `GET /follow-ups/notifications?unread_only=true` | Usuarios autenticados |
| Seguimientos pendientes | `GET /follow-ups` | Médico; el endpoint devuelve únicamente los propios |
| Usuarios y centros activos | `GET /users`, `GET /centers` | Administrador |

El Dashboard no calcula tendencias, porcentajes, gráficos ni estadísticas
clínicas que la API no proporcione. Tampoco se muestra una métrica de especialidad
ni existe una especialidad activa global.

## Composición por rol

- **Médico:** jornada clínica, especialidades del perfil, seguimientos propios,
  agenda en su alcance, notificaciones y accesos a Agenda, Pacientes, Reportes,
  Seguimientos, Disponibilidad y Cobertura.
- **Secretaría:** operación de agenda, pacientes y citas permitidos por sus
  centros/médicos, notificaciones y accesos a Agenda, Pacientes, Reportes y
  Cobertura. No se solicitan ni presentan historias, diagnósticos, recetas,
  notas clínicas ni seguimientos.
- **Administrador:** administración operativa, usuarios y centros activos,
  agenda en el alcance que determine el backend, notificaciones y accesos a
  Agenda, Pacientes, Reportes, Usuarios y centros. Administrar no añade bloques
  de historia clínica.
- **Roles combinados:** se unen los resúmenes y acciones por identificador, por
  lo que no hay tarjetas o accesos duplicados. Los endpoints siguen aplicando la
  autorización y scopes del backend.

Para médicos con más de una especialidad se presentan todas las
`specialty_names` del perfil separadas por «·». Es información de perfil, no un
selector ni un contexto para nuevas citas o consultas.

## Estados, responsive y accesibilidad

Cada fuente secundaria mantiene carga, vacío y error propios. Por ejemplo, si
falla la agenda del día, el Dashboard explica el error y conserva sus otras
acciones y bloques disponibles. Las tarjetas usan grid de una columna en móvil,
dos desde `sm` y hasta tres columnas en escritorio; la lista de agenda permite
envolver contenido sin provocar overflow horizontal.

La página conserva un `h2` principal, secciones con `h3`, botones reales para
las acciones, nombres accesibles, foco visible y mensajes `role=status` o
`role=alert` para carga y error. El Drawer, skip link, topbar y Sidebar de Fase
2 permanecen sin rediseño.

## Aplazado

No forman parte de esta fase: Consultation UI V2, selector de especialidad
global, nuevos permisos o endpoints, analítica clínica, IA, billing, ARS,
personalización, drag/drop, temas y cambios a Login o App Shell.

## Prueba local

```sh
git fetch origin
git switch frontend/ui-v2-role-dashboards
cd frontend
pnpm test
pnpm run build
pnpm run dev -- --host localhost --port 5173 --strictPort
```

Con el backend configurado conforme a `README.md`, iniciar sesión con Médico,
Secretaría, Administrador y una cuenta Médico + Administrador. Revisar acciones,
estado de agenda vacía, notificaciones, Drawer móvil y la restauración de sesión.
El catálogo de desarrollo continúa en `/__dev/ui-v2`.
