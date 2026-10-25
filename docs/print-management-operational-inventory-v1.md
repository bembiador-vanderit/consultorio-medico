# Gestión de impresión — inventario operativo V1

La pantalla **Administración → Gestión de impresión** reutiliza `GET /api/v1/local-agents/registry` y el permiso `local_agents:view`. No crea trabajos ni modifica el registro.

El inventario principal cuenta y muestra solo impresoras con `available=true`. Los registros con `available=false` permanecen en PostgreSQL para trazabilidad, pero no aparecen ni se cuentan en esta vista. «Historial de impresión» es únicamente un marcador de posición; no consulta ni presenta esos registros como supuesto historial de trabajos.

El modelo actual no distingue inequívocamente una impresora retirada de una impresora activa temporalmente fuera de servicio. Por ello, **esta fase no infiere esa diferencia**: ambas quedan fuera del inventario operativo mientras `available=false`. Una política futura necesitará una señal explícita de ciclo de vida antes de presentar o gestionar esos casos por separado. El estado de conexión de la estación se muestra independientemente de `available`.
