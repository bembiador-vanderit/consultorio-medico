# Pre-pilot Integrated Validation / Staging

Fecha: 2026-09-28

Base validada: `feat/complete-care-context` en `0f1d54e`

Entorno: Docker Compose local desechable, PostgreSQL 16, datos exclusivamente sintéticos

Resultado: **PASS — listo para pre-piloto controlado**

## Resumen ejecutivo

6C3–6C7 funcionan juntas en el recorrido integrado probado. No se encontraron defectos críticos ni altos. El aislamiento entre organizaciones se comprobó en HTTP, persistencia, navegación y auditoría; Caja mantuvo separados los cobros del paciente y los montos esperados de ARS; los reversos conservaron trazabilidad; los estados clínicos no cambiaron por operaciones financieras.

Se encontraron dos defectos UX menores: las tablas ARS no distinguían visualmente una carga en curso de una lista realmente vacía y la pantalla administrativa global no usaba la superficie visual Atlas. Se corrigieron con estados explícitos de carga/ausencia y con los componentes, fondo, tarjetas y comportamiento responsive actuales. No justificaron una rama de hardening ni bloquean el piloto.

No se desplegó a producción. `main` permaneció en `b31a0ff`. Cardiología 6C2B/6C2C, Device Hub, DGII/e-CF y nuevas integraciones ARS quedaron fuera del alcance.

## Matriz de validación

| Escenario | Resultado | Evidencia principal |
|---|---|---|
| PR #53 abierto, limpio y CI verde antes de integrar | PASS | CI `36210003857`; 376 backend, 301 frontend; merge `0f1d54e` hacia `feat/complete-care-context`. |
| Stack completo con PostgreSQL y datos controlados | PASS | Proyecto Compose `atlas-prepilot`, PostgreSQL 16, backend y frontend en puertos separados; seed rechaza una base distinta de `atlas_prepilot`. |
| Dos organizaciones reales en la misma base | PASS | Atlas A por `localhost`, Atlas B por `127.0.0.1`, centros, usuarios, pacientes, ARS y citas sintéticos independientes. |
| Admin de organización, secretaria, médico y platform admin | PASS | Admin recorrió administración y Finanzas; secretaria accedió a cobros pero no ARS; médico no accedió a Caja/ARS; platform admin necesitó membresía y rol local. |
| Horario dentro/fuera, expiración, excepción y día bloqueado | PASS | `test_access_schedules.py`: denegación sin fuga de datos, cierre exacto de jornada, refresh sin ampliación, excepción temporal, bloqueo prioritario y auditoría. |
| Aislamiento cross-tenant: pacientes, usuarios, ARS, seguros, Caja, reclamaciones y auditoría | PASS | HTTP real rechazó IDs/centros del otro tenant; suites de organización, Seguros, Caja y ARS verificaron lecturas, escrituras y referencias cruzadas. |
| Paciente particular: parcial, saldo, pago posterior y cierre | PASS | En cada tenant: factura DOP 1,500; pago mixto 500; saldo 1,000; pago posterior; reverso/reaplicación; cierre auditable. |
| Paciente asegurado: plan, cobertura, autorización y copago | PASS | Cobertura DOP 1,500 separó DOP 500 de paciente y DOP 1,000 ARS; Caja no incluyó el monto ARS. |
| Reclamación, glosa, corrección, reenvío y cobro ARS | PASS | En cada tenant: reclamación 1,000; glosa 200; corrección a 1,000; reenvío; remesa y aplicaciones 400 + 600. |
| Pago ARS parcial/completo, reverso, conciliación y aging | PASS | Tras revertir una aplicación quedó DOP 600 pagado y DOP 400 pendiente; conciliación y aging 0–30 coincidieron con CxC. |
| Pagos mixtos y reversos auditables | PASS | Efectivo, tarjeta y transferencia; reversos conservaron movimiento original y generaron eventos/auditoría. |
| Cierre de caja con diferencia | PASS | Sin observación devolvió 422; con observación cerró y registró diferencia de DOP -1,100 en ambos tenants. |
| Estados clínicos y financieros desacoplados | PASS | La regresión 6C6 conserva `appointment.status=completed` durante facturación; reclamaciones/remesas no escriben estados clínicos. |
| Platform admin en tenant y contexto global | PASS | En tenant B solo mostró Atlas B y módulos locales; `/platform/organizations` fue 404. En `platform.localhost` mostró solo el inventario de Atlas A y Atlas B, sin módulos clínicos. |
| UI, responsive, tema y navegación | PASS | Revisión manual de escritorio y vista compacta: Seguridad, contexto tenant/plataforma, Horarios, Seguros/ARS, Caja/Facturación y las cuatro vistas ARS. Tema, fondo, cabecera, sidebar y navegación móvil fueron consistentes. |
| Suite, build y migraciones PostgreSQL | PASS | 376/376 backend; 301/301 frontend; build Vite; upgrade, downgrade y reaplicación; preservación 6C4C/6C5/6C6/6C7; concurrencia PostgreSQL. |

## Defectos y deudas

| ID | Severidad | Estado | Detalle |
|---|---|---|---|
| UX-PP-01 | Baja | Corregido | Reclamaciones, remesas, CxC y conciliación podían mostrar solo encabezados mientras cargaban. Ahora muestran “Cargando…” y un mensaje explícito cuando no hay registros. |
| UX-PP-02 | Baja | Corregido | El contexto administrativo global tenía una presentación aislada del tema Atlas. Ahora comparte fondo, tarjetas, tipografía, controles y adaptación móvil, manteniendo únicamente el inventario global. |
| DEBT-ARS-01 | Baja | Documentado | Entrada y aplicación de remesas siguen siendo manuales; no hay integración bancaria ni portal ARS. |
| DEBT-UX-01 | Baja | Documentado | Falta una sesión de revisión visual con usuarios reales del piloto. |
| DEBT-REPORT-01 | Baja | Documentado | PDF/impresión, exportaciones y BI avanzado permanecen fuera del alcance. |
| DEBT-LIST-01 | Baja | Documentado | Los listados usan paginación/límites operativos; no se hizo prueba de volumen de producción. |
| DEBT-PY-01 | Baja | Documentado | La suite pasa, pero reporta advertencias de deprecación heredadas, principalmente por `datetime.utcnow()` y dependencias. Conviene retirarlas antes de actualizar el runtime. |

No hubo pérdida, mezcla o exposición cross-tenant durante la validación. Los únicos tropiezos del laboratorio fueron de preparación: el primer fixture no incluyó la especialidad obligatoria de la cita y una variable local usó el dominio reservado `.test`, que el validador de email rechaza. Esa variable también inyectó un usuario bootstrap adicional en una primera ejecución de la suite. Se corrigió el fixture y se aisló la suite de las credenciales bootstrap; la repetición completa terminó con 376/376 pruebas. No eran defectos del producto.

## Evidencia ejecutada

- Flujo HTTP integrado: `backend/scripts/prepilot_http.py`, ejecutado una vez por tenant sobre el backend real y PostgreSQL.
- Migraciones y suite backend: `backend/scripts/prepilot_checks.py` sobre once bases PostgreSQL desechables con nombres protegidos.
- Datos sintéticos: `backend/scripts/prepilot_seed.py`; dos tenants, tres roles locales, platform admin, pacientes particular/asegurado, citas, plan y ARS.
- Frontend: build TypeScript/Vite y 301 pruebas de comportamiento, navegación, permisos, responsive y contexto.
- Evidencia visual: `prepilot-platform-context.png`, `prepilot-access-schedule.png` y `prepilot-ars-receivables.png` para contexto global, Horarios y CxC.

## Reproducción local

Use una copia limpia y una `.env` local con secretos aleatorios. Los siguientes valores estructurales reservan el laboratorio y evitan colisiones con una instalación habitual:

```dotenv
POSTGRES_DB=atlas_prepilot
POSTGRES_USER=atlas_stage
POSTGRES_PORT=55433
BACKEND_PORT=18001
FRONTEND_PORT=15173
INITIAL_ADMIN_EMAIL=bootstrap@example.com
TENANT_HOSTS_JSON={"localhost":"pilot","127.0.0.1":"second"}
PLATFORM_HOSTS_JSON=["platform.localhost"]
```

Defina además valores aleatorios para `POSTGRES_PASSWORD`, `DATABASE_URL`, `SECRET_KEY` e `INITIAL_ADMIN_PASSWORD`, manteniendo la misma contraseña de PostgreSQL en `DATABASE_URL`.

```powershell
docker compose -p atlas-prepilot -f docker-compose.yml -f compose.prepilot.yml up -d --build
docker compose -p atlas-prepilot exec -T backend python scripts/prepilot_seed.py
docker compose -p atlas-prepilot exec -T backend python scripts/prepilot_http.py
docker compose -p atlas-prepilot exec -T backend python scripts/prepilot_checks.py
docker compose -p atlas-prepilot exec -T frontend sh -c 'npm run build && node --test --test-concurrency=2 tests/*.test.mjs'
```

El seed y las comprobaciones se niegan a trabajar si la base principal no se llama `atlas_prepilot`. `prepilot_checks.py` recrea únicamente las bases desechables de CI enumeradas dentro de ese mismo contenedor.

## Recomendación

**No bloquear el pre-piloto controlado** después de integrar el PR de esta validación. Mantener monitoreo cercano de auditoría, cierres de caja, reversos, reclamaciones y diferencias durante los primeros casos simulados por usuarios. No usar esta recomendación como autorización de producción: despliegue, respaldo operativo y validación con usuarios son pasos separados.
