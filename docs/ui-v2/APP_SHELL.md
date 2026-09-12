# App Shell operativo — UI V2 fase 2

Base: `feat/complete-care-context` en
`553af16c1ffab4c216defb0733035cb3f75c225c`. Esta fase conecta el App Shell
aprobado de UI V2 con la aplicación autenticada real. No rediseña los cuerpos
operativos de Dashboard, Agenda, Pacientes, Consulta, Seguimientos ni
Administración.

## Arquitectura

`App.tsx` conserva la restauración de sesión, login, logout, selección de
paciente/cita, guards clínicos y el estado `view` existente. Después de resolver
un usuario autenticado, entrega exactamente el mismo árbol de páginas a
`AtlasAppShell`.

El shell recibe la vista actual y un único callback de navegación; no introduce
un router paralelo. La consulta médica sigue siendo un subflujo de Agenda: cuando
está activa, Agenda mantiene el indicador de navegación. Navegar a Agenda desde
la sidebar limpia un paciente preseleccionado; el flujo Pacientes → Agendar cita
lo conserva. Así se mantiene el comportamiento operativo previo.

La superficie clara del workspace tiene máximo de 90rem, espaciado por tokens y
scroll horizontal solo para preservar tablas legacy anchas. El sidebar Navy es
persistente desde 1024px; topbar y workspace permanecen visibles y ningún contenido
queda bajo el marco. Las clases de compatibilidad están en
`layouts/operational-shell.css`; no modifican los cuerpos de las páginas.

## Sidebar y roles

Se reutiliza sin una segunda definición `navigation/navigation.ts`, que centraliza
vistas, etiquetas, iconos, grupos y el resolver de visibilidad. El resolver
refleja las condiciones que ya usaba `App.tsx`; la visibilidad sigue siendo solo
descubrimiento y el backend conserva toda autorización.

| Contexto | Destinos adicionales a Dashboard, Agenda, Reportes y Pacientes |
| --- | --- |
| Doctor | Seguimientos, Mi disponibilidad, Cobertura clínica |
| Secretaría | Cobertura clínica |
| Administrador | Usuarios y roles, Localidades y centros |
| Roles combinados | Unión de los destinos de cada rol |
| Rol desconocido | Solo los cuatro destinos generales, como antes |

La sidebar usa el Navy de `--atlas-navigation-*`, la marca temporal `A` y
`aria-current="page"` para el destino activo. El símbolo se mantiene separado del
nombre para reemplazarlo por el logo aprobado en el futuro. El selector Light/Navy,
su persistencia y cualquier tema global quedan diferidos.

## Topbar, notificaciones y logout

La topbar muestra solo datos reales del perfil: nombre y roles, especialidades si
la API las entrega, el slot de `NotificationBell` y el logout existente. No muestra
búsqueda, centro activo, perfiles, conmutadores ni contadores ficticios.

`NotificationBell` conserva su carga, polling, sincronización, marcado como leído
y acción de volver al Dashboard. La integración añade únicamente una clase de
anclaje para que su panel no se salga de la pantalla móvil; no cambia su lógica ni
endpoints. Logout continúa invocando `logoutSession`, limpia estado y muestra el
Login UI V2 aprobado.

## Móvil y accesibilidad

Por debajo de 1024px la sidebar persistente se oculta y la topbar ofrece el botón
«Abrir navegación». El mismo `Sidebar` se presenta dentro del `Drawer` de la
fundación: título enfocado al abrir, ciclo de Tab, Escape, cierre al elegir una
vista, foco devuelto al trigger y desbloqueo de scroll. Al volver a desktop el
drawer se cierra. Se conserva el skip link, landmarks `nav`/`main`, controles con
nombre accesible, foco visible y el estado activo que no depende solo del color.

Se revisaron 320, 375, 768, 1024 y 1440px. A 320px el panel operativo de
notificaciones cabe entre márgenes seguros; no se inspeccionó cada tabla legacy
en todos los anchos, porque su rediseño pertenece a fases posteriores.

## Alcance diferido

Esta fase no altera backend, autenticación, sesión, roles, scopes de pacientes,
reglas clínicas, especialidades ni plantillas clínicas. El shell es común e
independiente de la especialidad: no crea frontends/shells para Cardiología,
Medicina Interna, Pediatría ni futuras especialidades. La auditoría multiespecialidad
de solo lectura queda para la fase acordada antes de Consultation UI V2.

También quedan diferidos el rediseño de páginas, PageHeader/breadcrumbs reales,
logos finales, búsqueda global, perfil, selector de apariencia, drag/drop,
persistencia de workspace y un sistema de permisos nuevo.

## Probar localmente

```sh
git fetch origin
git switch frontend/ui-v2-app-shell
cd frontend
npm install
npm run dev -- --host localhost --port 5173 --strictPort
```

Con backend configurado conforme a `README.md`, abrir `http://localhost:5173/` e
iniciar con una cuenta existente. La API predeterminada es
`http://localhost:8000/api/v1` y el CORS actual permite
`http://localhost:5173`. Después de ingresar, probar sidebar, Agenda, una sección
permitida por el rol, campana, F5, logout y la navegación móvil. El catálogo de
desarrollo permanece en `http://localhost:5173/__dev/ui-v2`.
