# Atlas Sync Guard V1

Guardia local de Git para la rama de trabajo de Atlas Pérgamo. No es un GitHub Action ni activa migraciones. El validador lee el estado del repositorio, consulta el remoto y aplica pruebas según las rutas modificadas. El sincronizador solo actúa después de que el validador pase; nunca hace pull, merge, rebase ni force-push.

Desde `C:\AtlasPergamo`:

```powershell
.\scripts\atlas-validate.ps1
.\scripts\atlas-sync.ps1 -Message "feat(example): description"
.\scripts\atlas-sync.ps1 -Message "feat(example): description" -DryRun
.\scripts\test-atlas-sync.ps1
```

`-DryRun` valida, pero no stagea, confirma ni publica. La primera activación real del sincronizador requiere una tarea separada; no usarlo para confirmar su propia implementación durante esta microfase.

## Bloqueos

- Repositorio equivocado, HEAD detached, `main`, rama fuera del patrón o upstream distinto de `origin/<rama>`.
- Archivos prohibidos o secretos obvios en candidatos o staged; archivos binarios no revisables también se detienen.
- El remoto está por delante, falla el fetch, hay errores de whitespace, o no existe exactamente un Alembic head.
- Base oficial y target de arranque incoherentes cuando la instancia oficial está disponible. Si se propone una nueva migración, la base puede seguir en el target anterior; la guardia **no** ejecuta `alembic upgrade`.
- Pruebas del perfil fallidas o imposibles de ejecutar. Si no hay foco seguro, se amplía la regresión.

## Perfiles

`DOCS_ONLY` comprueba vínculos locales; `FRONTEND`, `BACKEND` y `AGENT` corren las respectivas suites y build/compile; `MIGRATION` añade revisión Alembic y pruebas backend; `SECURITY` ejecuta pruebas de la guardia y regresión ampliada; `CROSS_CUTTING` ejecuta suites completas. Las comprobaciones de seguridad, diff, rama y remoto se aplican en todos los perfiles.

La sincronización usa `git add -A` solo después del examen de candidatos. Revalida staged antes del commit. Si la publicación falla después de crear el commit, informa `COMMIT_CREATED=YES` y `GITHUB_SYNC=NO`; no intenta reescribir historia ni resolver conflictos automáticamente. El mensaje de commit debe proporcionarse explícitamente.
