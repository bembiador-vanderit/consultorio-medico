# Personalización de usuario V1 — persistencia preparada

## Estado de activación

La revisión `0070_user_preferences` está preparada y validada en PostgreSQL temporal. **No está aplicada a la base oficial**, que debe permanecer en `0069_print_job_contract` hasta una microfase de activación separada. El target permanente de arranque tampoco cambia en esta fase.

Antes de activar 0070, la API de preferencias responde 503 con un mensaje específico; la interfaz muestra defaults y avisa que no pudo sincronizar. No afirma que los cambios hayan quedado guardados.

## Contrato

`user_preferences` mantiene una fila 1:1 por `users.id`, con FK y unicidad. Guarda exclusivamente `gestion_menu_order`, `dashboard_widget_order`, `accent_theme` y marcas de tiempo. Las listas contienen IDs técnicos conocidos, nunca etiquetas, coordenadas, CSS ni datos clínicos. El acento está limitado a `classic`, `blue`, `turquoise`, `clinical-green`, `indigo` y `violet`. La revisión no realiza backfill ni modifica usuarios históricos.

`GET /api/v1/me/preferences` devuelve defaults canónicos sin insertar una fila cuando no existe. `PUT /api/v1/me/preferences` valida IDs, duplicados, tamaño y acento, y guarda por el `current_user` del token; no acepta `user_id` en el cuerpo. Repetir el mismo PUT no altera `updated_at`. La preferencia es global al usuario y lo sigue entre sesiones y clientes.

## Menú y Dashboard

Los IDs de Gestión provienen de `frontend/src/navigation/navigation.ts`. El Dashboard cataloga acciones rápidas, indicadores y paneles que ya existen en `frontend/src/components/dashboard/dashboardModel.ts`. Se puede reordenar cada grupo con botones Subir/Bajar, también en móvil; el layout responsive mantiene los grupos y resuelve columnas según el ancho. No se introducen widgets ficticios ni posicionamiento absoluto.

Al aplicar una preferencia, cada cliente filtra primero por roles/permisos reales y después normaliza el orden: ignora IDs no visibles u obsoletos, conserva el orden válido y agrega widgets nuevos visibles al final. La preferencia no concede acceso; el backend continúa aplicando autorización a cada recurso. El tema solo cambia tokens de acento, no los tokens semánticos de error, warning, éxito ni estados clínicos/financieros.

La pantalla **Herramientas → Personalización → Mi espacio de trabajo** carga las preferencias de la cuenta, permite editar y previsualizar de inmediato, y guarda explícitamente. Incluye restablecimiento individual de Navegación, Dashboard y Apariencia, además de Restablecer todo. `localStorage` no es fuente de verdad.

El diseño mantiene los IDs y límites definidos en [Visión de personalización de interfaz](ui-personalization-vision.md). Extenderlo a otros módulos requiere aprobación y contratos propios; 0070 no implementa un diseñador universal de layouts.
