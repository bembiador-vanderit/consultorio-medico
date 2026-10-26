# Capa de datos de Consultation

## Arquitectura y cliente clínico

`clinicalApi` concentra las rutas clínicas tipadas. Conserva `revision` y exige `expected_revision` al actualizar; los errores HTTP, incluido 409, llegan sin transformación genérica. Las mutaciones no reciben `AbortSignal`: abortar la espera del navegador no implica revertir una escritura ya recibida por el servidor.

## Bootstrap, dependencias y respuestas tardías

`useConsultationBootstrap` carga primero `Appointment -> ConsultationContext`; si encuentra historia activa, carga en paralelo signos vitales, diagnósticos, recetas y solicitudes. El catálogo depende de `specialty_id` del contexto. Las órdenes mantienen su ciclo episode-scoped propio.

Cada cambio de cita crea una generación y aborta sus GET anteriores. `AbortController` y el guard de generación son defensas independientes y complementarias: el primero solicita la cancelación de la red; el segundo impide publicar estado si una promesa que no respetó el aborto resuelve o falla tarde. Al desmontar, el controlador se aborta y el guard impide cualquier publicación posterior. Los `AbortError` esperados no se muestran como error clínico; un error de la generación activa sí se publica.

Antes, una consulta existente hacía aproximadamente 11 GET: contexto, catálogo de estudios, cuatro recursos del episodio y cuatro lecturas de órdenes/catálogos. Después son 10 cuando el catálogo de estudios ya está en memoria de la sesión; el episodio y sus recursos PHI nunca se cachean.

## Caché de catálogos, conteo y privacidad

La caché en memoria se limita a catálogos no PHI. Las claves reales son `studies:specialty:<specialty_id|none>:all:<boolean>` para estudios —por ejemplo, `studies:specialty:3:all:false`— y una única entrada global interna para `/laboratory-tests`. Comparte la promesa en vuelo entre consumidores, separa especialidad e `include_all`, y elimina entradas fallidas para permitir reintento. La carga fría, la reutilización caliente, la deduplicación concurrente, la expulsión tras fallo, el reintento y la separación de scopes tienen cobertura focused.

El conteo observado en las pruebas es: una consulta nueva con catálogo frío emite 3 GET iniciales (contexto, catálogo de estudios y sesión); una consulta existente con catálogo de estudios frío conserva 11 GET en total; con ese catálogo ya caliente emite 10 GET. La diferencia es una sola lectura de catálogo reutilizada; no se inventan ni se eliminan lecturas de datos del episodio. Los cuatro GET de órdenes/catálogos propios de la sección de órdenes siguen fuera del bootstrap.

No se cachean globalmente historias clínicas, signos vitales, diagnósticos, recetas, solicitudes, órdenes, pacientes ni ningún otro dato del episodio. Tampoco se registran payloads clínicos en consola.

## Errores, concurrencia y límites

Un 401/403/404/409/422/5xx conserva su detalle cuando el servidor lo entrega. No hay retry ni recarga automática ante 409; el formulario conserva los cambios locales y adopta una revisión únicamente en una respuesta exitosa. El cierre y las reglas append-only posteriores continúan siendo autoridad del backend.

## Validación y limitaciones conocidas

Las pruebas focused cubren el cliente clínico (revisión, `expected_revision`, 409 y señal de lectura), la caché y el bootstrap (A → B → respuesta o error tardío de A, desmontaje, error activo y `AbortError`). La suite frontend completa pasó con 165 de 165 pruebas. TypeScript y Vite también pasaron.

La caché vive únicamente durante la sesión JavaScript y no hace invalidación por tiempo; es adecuada para catálogos de lectura, no para datos clínicos. Esta fase no agrega autosave, estado dirty global, reintentos automáticos ni un endpoint nuevo de bootstrap. El servidor sigue resolviendo la concurrencia clínica, el cierre y las reglas post-cierre.

Phase 6B4 introduce el límite de `ConsultationWorkspace`, sin agregar autosave, estado dirty global, módulos visuales nuevos ni un endpoint de bootstrap.
