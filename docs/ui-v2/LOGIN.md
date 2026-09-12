# Login — UI V2 fase 1

La entrada real sin sesión de Atlas Consultorio usa ahora la fundación aprobada
en PR #25. Rama `frontend/ui-v2-login`, creada desde
`30f5efe429ed630da8a8806c5b67ce10ba00b48e` de `feat/complete-care-context`.

## Presentación y componentes

`LoginLayout` centra una tarjeta clínica de hasta 64rem sobre la superficie
secundaria. Desde 900px se divide en un panel clínico del 40% y un panel de acceso
del 60%. El primero combina Sky/Mint, «Cuidar también es innovar» y la identidad
temporal «A» en la parte inferior, con «Gestión médica simple, segura y confiable».
El formulario tiene un ancho máximo de 25rem y el título «Bienvenido a Atlas».
Se reutilizan tokens, tipografía, `Card`,
`FormField`, `Input`, `Button`, `IconButton`, `Alert` y `LoadingState` existentes.
El icono de visibilidad es un SVG local decorativo dentro de `IconButton`.
No se introduce otro sistema de componentes ni un logo definitivo.

El visual clínico es CSS original de esta corrección: cruz decorativa clara y
anillos sobre un degradado de tokens Atlas. No se introducen imágenes, recursos
remotos ni material de terceros; no requiere atribución/licencia de stock. Es
decorativo (`aria-hidden`) y no sustituye la marca temporal, que sigue separada
y reemplazable.

Por debajo de 900px, el panel se convierte en una cabecera compacta con la marca
y el lema, ocultando la ilustración y el texto de apoyo para priorizar el acceso.
La composición tiene una columna y márgenes seguros desde 320px; los campos y el
control de contraseña miden 44px de alto y el botón principal 48px. El login no
monta el sidebar ni el shell autenticado. `/__dev/ui-v2` sigue siendo el catálogo
de desarrollo independiente, excluido del bundle de producción.

## Autenticación real

Se inspeccionaron `App.tsx`, `services/api.ts`, los endpoints de autenticación,
sus esquemas y el arranque de identidad del backend. El contrato usa correo
electrónico y contraseña: JSON `{ email, password }` a `POST /api/v1/auth/login`,
seguido de `GET /api/v1/auth/me`. `services/login.ts` extrae esa secuencia de App
sin cambiar su significado. La aplicación solo acepta el usuario tras obtener
su perfil real; cualquier fallo limpia el bearer en memoria.

Se conservan Axios con `withCredentials`, el token de acceso en memoria, la cookie
de refresh gestionada por el servidor, restauración mediante `/auth/refresh`
y `/auth/me`, logout y navegación/roles del espacio autenticado. No se modifica
backend, almacenamiento de sesión ni autorizaciones. La contraseña tiene los
límites de 8 a 128 caracteres del esquema actual.

La restauración inicial muestra «Comprobando sesión…». El envío mantiene el
formulario visible con «Ingresando…», impide solicitudes duplicadas y bloquea
edición y visibilidad mientras espera. Tras éxito se limpia la contraseña y se
abre la aplicación operativa existente.

El backend devuelve el mismo 401 para credenciales inválidas y usuarios inactivos;
se conserva «Correo o contraseña incorrectos.». Otros rechazos y fallos de red
muestran «No fue posible iniciar sesión. Intente nuevamente.». No se presentan
detalles internos. Se elimina el antiguo `console.error` del login: los errores
Axios pueden contener la contraseña y los headers en su configuración.

## Accesibilidad

Etiquetas visibles asociadas mediante `FormField`, campos obligatorios, validación
nativa de email, autocompletado `username`/`current-password`, foco de la fundación
y envío con Enter. El orden es correo, contraseña, visibilidad y envío.
El botón de visibilidad tiene nombre dinámico y `aria-controls`; no envía el
formulario. Los errores usan `role="alert"` y el progreso `role="status"`.

## Pruebas y límites

`tests/login.test.mjs` añade 12 pruebas interactivas con React, Vite y jsdom 26.1.0,
una dependencia exclusiva de desarrollo. Cubren etiquetas, contraseña, validación,
secuencia login/perfil, bloqueo del envío, errores 401/403/500/red, fallo del perfil,
entrada operativa, restauración y logout. El adaptador HTTP de Axios se sustituye
solo en tests con datos ficticios; se ejecutan los componentes y servicios reales.
Las 9 pruebas previas de fundación siguen ejecutándose sin modificación.

La revisión de navegador usa la ruta real `/`, comprueba Enter, visibilidad,
error de conexión y anchos 320/375/768/1024/1440. El éxito de sesión se comprueba
con el adaptador de prueba y los tests reales del backend por separado; no se
afirma una prueba E2E de cookies contra una instalación clínica. No se realizó
auditoría con lector de pantalla ni matriz multinavegador.

Se difieren registro, recuperación de contraseña, MFA, SSO, recordar sesión,
selectores, onboarding, landing, logo definitivo, integración del shell y
rediseños de módulos operativos. No se agregaron accesos demo ni bypasses.

## Probar la entrada real

Con el backend y la base de datos configurados según README, en una copia local:

```sh
git fetch origin
git switch frontend/ui-v2-login
cd frontend
npm install
npm run dev -- --host localhost --port 5173 --strictPort
```

Abrir **http://localhost:5173/** sin sesión, o cerrar sesión desde la aplicación.
La API predeterminada es `http://localhost:8000/api/v1`; el CORS actual permite
`http://localhost:5173`. Usar ese host/puerto para probar autenticación real.
Si se configura `VITE_API_URL`, debe apuntar al backend correspondiente.
Usar una cuenta autorizada existente; esta fase no crea credenciales.

Las capturas entregadas se tomaron de la misma entrada `/` en el servidor visual
local `http://127.0.0.1:5184/`, sin sesión. Ese puerto no sustituye la configuración
de API/CORS indicada arriba. Los resultados ejecutados están en [VALIDATION.md](VALIDATION.md).
