# Atlas Task Orchestrator V1: contrato, no ejecutor

Esta fase define cómo describir una microtarea en JSON y en un Issue. No crea Issues, no inicia Codex automáticamente, no hace deploy y no modifica la base de datos de Atlas.

El contrato está en [`task-contract.schema.json`](task-contract.schema.json). Se valida con PowerShell 7:

```powershell
pwsh -NoProfile -File .\scripts\atlas-task-validate.ps1 -Path .\ruta\tarea.json
pwsh -NoProfile -File .\scripts\test-atlas-task-orchestrator.ps1
```

El formulario «Atlas Task» de GitHub captura los campos de planificación. En V1 **no** convierte automáticamente un Issue a JSON; el contrato debe construirse y validarse explícitamente. No escribir secretos, credenciales ni datos de pacientes en Issues o contratos.

## Reglas principales

- `task_id` usa `ATLAS-XXXX`; `expected_base_sha` y `commit_sha` son SHA de 40 caracteres.
- `priority` admite `P0`–`P3`. `model` y `reasoning_level` son recomendaciones explícitas, no una selección automática.
- `depends_on` contiene pares `{task_id, status}` suministrados por quien prepara la tarea. El validador no consulta GitHub ni presume que esos estados estén actualizados; antes de ejecutar hay que verificarlos de nuevo. `blocks` enumera tareas posteriores bloqueadas por esta tarea.
- Una tarea `READY` requiere todas sus dependencias `COMPLETED`. `READY_FOR_EXECUTION=YES` significa solamente que el contrato es coherente; **no** concede autorización para ejecutar ni altera la cola.
- `COMPLETED` exige `result=PASS`, `commit_sha`, `github_sync=YES` y `completed_at`.
- `BLOCKED` exige una explicación en `result`, pero no exige commit.
- Con `REVIEW_REQUIRED`, un trabajo técnicamente terminado queda `WAITING_FOR_REVIEW` hasta que exista aprobación humana explícita (`review_approved=true`). No puede marcarse `COMPLETED` antes.
- `REVIEW_RECOMMENDED` permite `COMPLETED` y señala `USER_NOTIFICATION_RECOMMENDED=YES`.
- `AUTO_CONTINUE` señala `NEXT_TASK_ALLOWED=YES` solo tras completar y sincronizar, con dependencias satisfechas. Es un indicador, no un disparador automático en V1.
- Las rutas permitidas y prohibidas no pueden solaparse, incluso por prefijo; V1 no admite excepciones anidadas. Esto falla de forma conservadora.

Los estados son `QUEUED`, `READY`, `IN_PROGRESS`, `VALIDATING`, `BLOCKED`, `COMPLETED`, `FAILED` y `WAITING_FOR_REVIEW`. Los tipos iniciales son `DOCS`, `FRONTEND`, `BACKEND`, `AGENT`, `DATABASE`, `SECURITY`, `FINANCE`, `CLINICAL`, `PRINTING`, `INFRASTRUCTURE` y `CROSS_CUTTING`.
