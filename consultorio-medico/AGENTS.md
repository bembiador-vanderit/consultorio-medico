# AGENTS.md — Consultorio Médico

## 1. Propósito

Este repositorio contiene un sistema profesional de gestión para consultorios médicos, inicialmente orientado a cardiología.

Objetivos:
- pacientes y expedientes clínicos;
- agenda y citas;
- consultas;
- signos vitales;
- recetas;
- estudios médicos;
- usuarios, roles y permisos;
- reportes;
- auditoría y respaldos;
- futura evolución a multi-doctor, multi-consultorio y SaaS.

El proyecto debe construirse con calidad de producto comercial desde el inicio.

## 2. Regla principal para Codex

Antes de modificar código:
1. Inspeccionar el repositorio y su estructura.
2. Leer README.md, AGENTS.md y documentación existente.
3. Identificar qué funciona actualmente.
4. No sobrescribir funcionalidad existente sin justificarlo.
5. Hacer cambios pequeños y verificables.
6. Ejecutar pruebas o verificaciones después de cambios relevantes.
7. Documentar decisiones arquitectónicas importantes.

No asumir que un archivo está vacío o que una funcionalidad no existe sin comprobarlo.

## 3. Idioma

La interfaz y documentación funcional deben estar principalmente en español. El código puede usar nombres técnicos en inglés cuando mejore la consistencia.

## 4. Stack oficial

### Frontend
- React
- Vite
- TypeScript cuando sea viable
- Tailwind CSS
- React Router
- Axios

### Backend
- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

### Base de datos
- PostgreSQL

### Infraestructura
- Docker
- Docker Compose
- Nginx cuando corresponda

### Control de versiones
- Git
- GitHub

## 5. Arquitectura

Frontend React
    |
    v
REST API
    |
    v
FastAPI
    |
    v
PostgreSQL

El frontend nunca debe acceder directamente a PostgreSQL.

Separar rutas HTTP, modelos ORM, lógica de negocio y componentes visuales.

## 6. Estructura esperada

```text
consultorio-medico/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── routes/
│   ├── package.json
│   └── Dockerfile
├── database/
│   ├── migrations/
│   └── seeds/
├── docker/
├── docs/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

La estructura puede evolucionar si existe una razón técnica clara.

## 7. Seguridad y privacidad

El sistema manejará información médica sensible.

Nunca introducir en Git:
- pacientes reales;
- cédulas reales;
- teléfonos reales;
- diagnósticos reales;
- fotografías o estudios reales;
- contraseñas;
- tokens;
- claves API;
- archivos `.env` reales.

Usar datos ficticios para desarrollo y pruebas.

Nunca almacenar contraseñas en texto plano. Usar hashes seguros.

La autorización debe aplicarse en backend; no confiar solamente en restricciones del frontend.

## 8. Roles iniciales

### Administrador
Usuarios, configuración, permisos y reportes administrativos.

### Doctor
Pacientes, consultas, signos vitales, diagnósticos, recetas, estudios e historial.

### Secretaria
Pacientes y agenda, con acceso limitado a información clínica.

## 9. Datos médicos

El software es una herramienta de registro y gestión.

NO debe:
- diagnosticar automáticamente;
- recomendar tratamientos;
- indicar medicamentos;
- sustituir el criterio médico;
- presentar IA como decisión clínica.

Si se agrega IA en el futuro, debe ser asistencia para el profesional y dejar clara la responsabilidad del médico.

## 10. Modelo de datos

Contemplar como mínimo:
- usuarios;
- roles;
- permisos;
- pacientes;
- citas;
- consultas;
- signos vitales;
- diagnósticos;
- medicamentos;
- recetas;
- estudios;
- archivos;
- auditoría.

Usar claves foráneas, restricciones e índices apropiados.

No eliminar información clínica histórica mediante operaciones destructivas sin estrategia de auditoría.

## 11. Auditoría

Las operaciones importantes sobre información clínica deben permitir conocer:
- quién;
- qué operación;
- cuándo;
- sobre qué registro.

No registrar información clínica innecesaria en logs.

## 12. API

Las APIs deben:
- usar rutas consistentes;
- validar entradas con Pydantic;
- devolver códigos HTTP apropiados;
- manejar errores consistentemente;
- no exponer información interna;
- exigir autenticación donde corresponda.

Preferir `/api/v1/...` para versionado.

## 13. Frontend

La interfaz debe ser:
- limpia;
- profesional;
- rápida;
- responsive;
- adecuada para escritorio y tablet;
- accesible.

Navegación inicial:
- Dashboard
- Pacientes
- Agenda
- Consultas
- Estudios
- Recetas
- Reportes
- Configuración

El médico debe poder completar una consulta con pocos pasos.

## 14. Pacientes

Debe permitir:
- registrar;
- buscar;
- editar;
- consultar;
- visualizar historial;
- consultar citas;
- consultar estudios;
- consultar recetas.

Evitar cargar innecesariamente todos los pacientes.

## 15. Agenda

Debe permitir:
- calendario;
- crear/modificar/cancelar citas;
- confirmar citas;
- estados;
- asociación paciente-profesional.

Preparar la arquitectura para múltiples doctores y consultorios.

## 16. Consulta médica

Inicialmente:
- motivo;
- signos vitales;
- antecedentes relevantes;
- evaluación;
- diagnóstico;
- tratamiento indicado por el médico;
- observaciones;
- recetas;
- estudios.

Los campos especializados de cardiología deben validarse con el cardiólogo antes de implementarse.

## 17. Cardiología

Preparar soporte para:
- electrocardiograma;
- ecocardiograma;
- Holter;
- prueba de esfuerzo;
- otros estudios cardiovasculares.

No inventar protocolos o campos clínicos sin validación profesional.

## 18. Archivos y estudios

Los archivos médicos nunca deben almacenarse dentro del repositorio Git.

Separar metadatos del estudio y almacenamiento físico.

La capa de almacenamiento debe poder evolucionar a local, NAS o almacenamiento S3 compatible/cloud.

## 19. Docker

El proyecto debe ejecutarse con Docker.

Servicios iniciales:
- frontend;
- backend;
- postgres.

Usar volúmenes para datos persistentes.

## 20. Variables de entorno

Nunca colocar secretos en el código.

Usar `.env` localmente y `.env.example` como plantilla.

El `.env` real debe estar en `.gitignore`.

## 21. Pruebas

Prioridad:
1. autenticación;
2. permisos;
3. pacientes;
4. citas;
5. consultas;
6. recetas;
7. estudios.

Nunca usar información real en pruebas.

## 22. Calidad

Preferir:
- código simple;
- funciones pequeñas;
- responsabilidades claras;
- tipado;
- validación;
- nombres descriptivos;
- manejo explícito de errores.

Evitar:
- duplicación;
- funciones gigantes;
- lógica de negocio en componentes visuales;
- SQL disperso;
- dependencias innecesarias;
- secretos en código.

## 23. Git

Usar commits pequeños y descriptivos:

```text
feat: add patient registration
fix: validate appointment date
refactor: separate patient service
test: add patient repository tests
docs: update setup instructions
chore: update dependencies
```

No mezclar funcionalidades no relacionadas en un commit.

## 24. Roadmap

### Fase 0
Infraestructura, Docker, PostgreSQL, FastAPI, React, documentación y health check.

### Fase 1
Autenticación, usuarios, roles, permisos y sesiones.

### Fase 2
Pacientes, CRUD, búsqueda y expediente.

### Fase 3
Agenda, calendario, citas y estados.

### Fase 4
Consulta, signos vitales e historial.

### Fase 5
Recetas, medicamentos y PDF.

### Fase 6
Estudios y archivos.

### Fase 7
Reportes.

### Fase 8
Facturación.

### Fase 9
WhatsApp y automatizaciones.

### Fase 10
Multi-doctor, multi-consultorio y SaaS.

## 25. No sobreingeniería

Construir una base preparada para crecer, pero mantener el MVP sencillo.

No implementar IA, facturación compleja, integraciones bancarias, seguros o multi-clínica antes de necesitarlos.

## 26. Documentación

Mantener documentación técnica en `docs/`.

Actualizar README, API y documentación de instalación cuando corresponda.

## 27. Definición de terminado

Una tarea no está terminada solo porque compile.

Según corresponda debe incluir:
- implementación;
- validaciones;
- pruebas;
- manejo de errores;
- seguridad;
- documentación;
- funcionamiento con Docker;
- compatibilidad con la arquitectura.

Nunca afirmar que algo fue probado si no se ejecutó.

## 28. Comportamiento esperado de Codex

Actuar como desarrollador senior responsable del proyecto.

Antes de cambios importantes:
1. analizar;
2. explicar brevemente el enfoque;
3. implementar;
4. probar;
5. revisar;
6. documentar.

Si existe un problema arquitectónico importante, explicarlo antes de realizar cambios destructivos.

No eliminar datos, migraciones o funcionalidades para hacer pasar una prueba.

## 29. Prioridad

Cuando haya conflictos, priorizar:
1. seguridad y privacidad;
2. integridad de datos;
3. correctitud funcional;
4. mantenibilidad;
5. rendimiento;
6. experiencia de usuario;
7. velocidad.

## 30. Objetivo final

Construir un sistema médico profesional que pueda comenzar en un consultorio de cardiología y evolucionar hacia una plataforma comercial para otros consultorios sin reconstruir el sistema desde cero.

Este documento es una guía viva. Si una decisión posterior cambia estas reglas, actualizar AGENTS.md y documentar el motivo.
