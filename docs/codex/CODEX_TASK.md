# Tarea actual para Codex

## Objetivo único

Preparar un informe de “listo/no listo para merge” de PR #4 en su HEAD actual, concentrado en el flujo de consulta clínica que une contexto de cita, diagnósticos, recetas y estudios solicitados. No fusionar PR #4.

## Base obligatoria

Trabajar sobre `feat/complete-care-context` o sobre una rama nueva creada desde `e4122dec10c743e5bc63ad3883a3e0366079ca2b`. Antes de comenzar, confirmar que el HEAD no cambió; si cambió, actualizar `CURRENT_STATE.md` y volver a establecer el corte.

## Alcance

1. Revisar autorización backend de las rutas de historia clínica, diagnósticos, recetas y estudios solicitados para administrador, doctor y secretaria.
2. Verificar relaciones y borrado entre cita, historia clínica, receta, diagnóstico y estudio solicitado.
3. Ejecutar la cadena Alembic desde una base vacía y reportar `alembic heads` y `alembic current`.
4. Ejecutar las pruebas backend y la compilación frontend.
5. Realizar una prueba funcional dirigida: abrir una cita, guardar consulta, agregar/editar/eliminar receta, agregar/eliminar estudio y confirmar que los datos se recargan correctamente.
6. Documentar hallazgos con severidad, archivo y evidencia. Si no hay bloqueadores, emitir una recomendación explícita de preparación para merge.

## Fuera de alcance

- Hacer merge, cerrar o modificar PR #4.
- Añadir módulos o funcionalidades nuevas.
- Refactorizar por estilo.
- Reescribir migraciones ya publicadas.
- Cambiar infraestructura, dependencias o secretos.
- Corregir hallazgos sin autorización posterior; esta tarea es de validación y diagnóstico.

## Criterios de terminado

- Cada verificación indica comando/flujo, resultado y evidencia.
- Se distingue entre bloqueadores, riesgos no bloqueantes y deuda documental.
- Se confirma explícitamente el estado de recetas y estudios solicitados.
- Se deja una conclusión binaria: `LISTO PARA MERGE` o `NO LISTO PARA MERGE`, con razones.
- No se realizan cambios funcionales ni merge.
