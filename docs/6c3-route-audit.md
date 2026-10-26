# Inventario de rutas administrativas previo a 6C3

Extraído de las dependencias declaradas en el código de `4c669ba331b17e345c40990bbbe0b8e1a6ccdf47`. Es una fotografía previa a la implementación. Todas estas capacidades pertenecían a admin en bootstrap; ninguna escritura de esta tabla exigía reautenticación administrativa. El alcance era global para la instalación. Los controles de recursos clínicos se aplican adicionalmente en servicios.

| Método | Endpoint | Permiso backend | Archivo de rutas |
| --- | --- | --- | --- |
| GET | `/api/v1/centers` | `centers:manage` | `centers.py` |
| POST | `/api/v1/centers` | `centers:manage` | `centers.py` |
| PUT | `/api/v1/centers/{center_id}` | `centers:manage` | `centers.py` |
| POST | `/api/v1/centers/{center_id}/users` | `centers:manage` | `centers.py` |
| DELETE | `/api/v1/centers/{center_id}/users/{user_id}` | `centers:manage` | `centers.py` |
| GET | `/api/v1/clinical-catalog/specialties/admin` | `users:manage` | `clinical_catalog.py` |
| POST | `/api/v1/clinical-catalog/specialties` | `users:manage` | `clinical_catalog.py` |
| PATCH | `/api/v1/clinical-catalog/specialties/{specialty_id}` | `users:manage` | `clinical_catalog.py` |
| PUT | `/api/v1/clinical-catalog/specialties/{specialty_id}/status` | `users:manage` | `clinical_catalog.py` |
| PUT | `/api/v1/clinical-catalog/doctor-profile/{user_id}` | `users:manage` | `clinical_catalog.py` |
| GET | `/api/v1/clinical-history/audit-logs` | `users:manage` | `clinical_history.py` |
| POST | `/api/v1/insurance/companies` | `users:manage` | `insurance.py` |
| GET | `/api/v1/localities/all` | `centers:manage` | `localities.py` |
| POST | `/api/v1/localities` | `centers:manage` | `localities.py` |
| PUT | `/api/v1/localities/{locality_id}` | `centers:manage` | `localities.py` |
| PUT | `/api/v1/regional/settings` | `users:manage` | `regional.py` |
| GET | `/api/v1/users` | `users:manage` | `users.py` |
| POST | `/api/v1/users` | `users:manage` | `users.py` |
| PATCH | `/api/v1/users/{user_id}/profile` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/password` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/status` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/roles` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/specialties` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/centers` | `users:manage` | `users.py` |
| PUT | `/api/v1/users/{user_id}/secretary-scopes` | `users:manage` | `users.py` |

En 6C3, la dependencia compartida conserva la autorización de esta tabla y añade reautenticación y auditoría transaccional a sus escrituras. Las rutas nuevas están descritas en [el diseño y procedimiento 6C3](6c3-security-administration.md).
