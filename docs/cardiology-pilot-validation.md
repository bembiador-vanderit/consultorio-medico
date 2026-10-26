# Atlas Consultorio

## Piloto Cardiología

### Validación clínica previa a 6C2B

**Estado del documento:** hoja de trabajo. Ningún campo, orden, valor o módulo descrito aquí está aprobado por defecto.

| Marca | Significado |
|---|---|
| **PROPUESTO PARA VALIDACIÓN** | Candidato que debe discutirse con el cardiólogo del piloto. |
| **APROBADO POR EL CARDIÓLOGO** | Solo se marca después de registrar una decisión expresa del cardiólogo. |

Nombre del cardiólogo: ____________________  Fecha: __________  Versión revisada: __________

## Auditoría de Atlas antes de la validación

Esta auditoría describe la instalación de desarrollo al iniciar 6C2A. No contiene datos de pacientes.

- Cardiología está activa y tiene código técnico previsto `cardiology`.
- Existe un médico asignado a Cardiología en el entorno auditado.
- Su plantilla v1 publicada contiene, en orden, `core.anamnesis`, `core.vital-signs`, `core.diagnoses`, `core.prescriptions` y `core.clinical-orders`.
- La región anatómica existente es **Corazón**.
- Los estudios actualmente recomendados incluyen Electrocardiograma, Ecocardiograma, Holter 24 horas, MAPA 24 horas, Prueba de esfuerzo, Resonancia cardíaca y otras entradas canónicas generales. Esta lista debe mostrarse al cardiólogo; su presencia actual no equivale a aprobación clínica del piloto.
- El catálogo global de laboratorio contiene 321 pruebas en 16 categorías activas, incluida **Marcadores cardíacos**. Las preferencias de presentación por Cardiología siguen pendientes de validación.

Atlas ya cubre información que no debe duplicarse en un módulo cardiológico:

| Módulo core | Cobertura actual |
|---|---|
| Anamnesis | Motivo, enfermedad actual, antecedentes personales y familiares, alergias, medicamentos actuales, cirugías, enfermedades crónicas, hábitos y notas clínicas. |
| Signos vitales | Presión arterial, frecuencia cardíaca, frecuencia respiratoria, temperatura, saturación, peso y talla. |
| Diagnósticos | Descripción, código CIE-10 opcional y diagnóstico principal. |
| Recetas | Medicamento, presentación, dosis, vía, frecuencia, duración, cantidad e instrucciones registradas por el médico. |
| Órdenes clínicas | Laboratorios y estudios estructurados, notas, contexto del episodio, historial e impresión. |

## A. Flujo de consulta

**PROPUESTO PARA VALIDACIÓN**

1. ¿En qué orden realiza normalmente una consulta?
2. ¿Qué información revisa primero?
3. ¿Qué datos registra siempre?
4. ¿Qué datos registra solamente cuando aplican?
5. ¿Qué información necesita visible sin hacer scroll?
6. ¿Qué información pertenece exclusivamente a la consulta actual?
7. ¿Qué información necesita ver de forma longitudinal?

Secuencia para discutir, sin asumir que sea definitiva:

`Datos generales → Anamnesis → Signos vitales → Evaluación cardiovascular → Diagnósticos → Recetas → Estudios/órdenes`

**APROBADO POR EL CARDIÓLOGO**

Orden acordado: ________________________________________________________________

Datos siempre visibles: _________________________________________________________

Datos longitudinales: ___________________________________________________________

## B. Síntomas cardiovasculares

**PROPUESTO PARA VALIDACIÓN**

Revisar si se necesita registro estructurado de dolor o molestia torácica, disnea, palpitaciones, síncope, presíncope o mareo, ortopnea, disnea paroxística nocturna, edema, fatiga o intolerancia al ejercicio, claudicación, otros síntomas vasculares u otros.

Para cada síntoma seleccionado definir:

| Síntoma | ¿Se registra? | Forma: presencia / estado / texto / detalles | Obligatorio, opcional o condicional | Notas |
|---|---|---|---|---|
| Dolor o molestia torácica | | | | |
| Disnea | | | | |
| Palpitaciones | | | | |
| Síncope | | | | |
| Presíncope o mareo | | | | |
| Ortopnea | | | | |
| Disnea paroxística nocturna | | | | |
| Edema | | | | |
| Fatiga o intolerancia al ejercicio | | | | |
| Claudicación u otro síntoma vascular | | | | |
| Otro | | | | |

**APROBADO POR EL CARDIÓLOGO:** pendiente.

## C. Antecedentes y riesgo cardiovascular

**PROPUESTO PARA VALIDACIÓN**

Revisar si Atlas debe estructurar hipertensión, diabetes, dislipidemia, tabaquismo, antecedentes familiares cardiovasculares, enfermedad coronaria previa, infarto previo, insuficiencia cardíaca, arritmias, enfermedad valvular, enfermedad vascular periférica, ACV/AIT, cardiopatía congénita u otros.

Revisar por separado procedimientos y dispositivos: angioplastia o stent, bypass, ablación, cirugía valvular, marcapasos, desfibrilador implantable u otros.

Preguntas:

- ¿Qué datos ya quedan suficientemente cubiertos por la anamnesis core?
- ¿Cuáles requieren estructura para seguimiento longitudinal?
- ¿Se necesita fecha, tipo, institución, dispositivo u otro detalle? No definirlo hasta recibir respuesta.
- ¿Qué datos pertenecen al paciente y cuáles al episodio?

**APROBADO POR EL CARDIÓLOGO:** pendiente. Esta lista no se convertirá en columnas de base de datos sin aprobación.

## D. Examen cardiovascular

**PROPUESTO PARA VALIDACIÓN**

Discutir el uso real de ritmo, ruidos cardíacos, soplos, pulsos periféricos, edema, yugulares, examen pulmonar relacionado y hallazgos cardiovasculares adicionales.

Para cada elemento indicar si debe ser estructurado, texto libre o una combinación. Registrar también cuándo aplica y si debe verse longitudinalmente.

**APROBADO POR EL CARDIÓLOGO:** pendiente. No se han definido valores ni escalas.

## E. Clasificaciones

**PROPUESTO PARA VALIDACIÓN**

- ¿Utiliza NYHA en el flujo habitual? ¿En qué pacientes y momento?
- ¿Utiliza alguna clasificación de angina? ¿Cuál?
- ¿Utiliza otras escalas cardiovasculares?
- Si se aprueba una clasificación, ¿el médico seleccionará manualmente la clase y dejará una nota justificativa?

**APROBADO POR EL CARDIÓLOGO:** pendiente.

Atlas no inferirá diagnósticos ni clases automáticamente. Ninguna escala se implementará o calculará sin aprobación específica.

## F. Electrocardiograma

**PROPUESTO PARA VALIDACIÓN**

1. ¿Atlas debe registrar solamente el informe o interpretación redactado por el médico?
2. ¿Debe capturar mediciones manuales? ¿Cuáles exactamente?
3. ¿Debe adjuntar PDF o imagen?
4. ¿Puede existir más de un ECG por consulta?
5. ¿Necesita comparar ECG anteriores?
6. ¿Qué equipo y software usa actualmente?
7. ¿Exporta PDF, imagen, XML, DICOM, SCP-ECG u otro formato?
8. ¿Qué información debe aparecer en el PDF de consulta y en el historial?

**APROBADO POR EL CARDIÓLOGO:** pendiente. No existe integración de dispositivo ni interpretación automática en 6C2A.

## G. Holter y MAPA

**PROPUESTO PARA VALIDACIÓN**

Completar por separado para cada equipo:

| Pregunta | Holter | MAPA |
|---|---|---|
| Marca y modelo | | |
| Software utilizado | | |
| Formato exportado | | |
| Genera PDF | | |
| Entrega datos crudos | | |
| Tipo de reportes | | |
| Conexión USB o red | | |
| Puede generar múltiples archivos | | |

Flujo deseado para validar:

- equipo → software del fabricante → Atlas importa el resultado; o
- equipo → Atlas directamente.

**APROBADO POR EL CARDIÓLOGO:** pendiente. No se implementa integración en 6C2A.

## H. Ecocardiograma

**PROPUESTO PARA VALIDACIÓN**

¿Atlas debe solamente solicitarlo, registrar informe, almacenar medidas estructuradas, adjuntar archivo o PDF, o considerar integración futura con el equipo?

Medidas realmente utilizadas y su procedencia: ___________________________________

**APROBADO POR EL CARDIÓLOGO:** pendiente. No se proponen medidas ecocardiográficas.

## I. Prueba de esfuerzo

**PROPUESTO PARA VALIDACIÓN**

Definir si Atlas debe manejar solicitud, informe, archivo, datos estructurados o integración futura. Identificar el equipo y formatos actuales.

**APROBADO POR EL CARDIÓLOGO:** pendiente. No se implementan protocolos.

## J. Estudios y laboratorios

**PROPUESTO PARA VALIDACIÓN**

Durante la sesión se debe mostrar el catálogo vigente de Atlas, no reconstruirlo desde memoria. Preguntar:

- ¿Qué estudios y laboratorios desea visibles primero?
- ¿Cuáles no utiliza?
- ¿Cuáles faltan?
- ¿Cuáles deben aparecer como recomendados para Cardiología?
- ¿La recomendación depende del médico, del centro o de otra condición?

Decisiones: _____________________________________________________________________

**APROBADO POR EL CARDIÓLOGO:** pendiente. El catálogo y sus recomendaciones no cambian en 6C2A.

## K. PDF e historial

**PROPUESTO PARA VALIDACIÓN**

Definir qué información cardiovascular debe aparecer en:

| Salida | Información requerida | Orden | Observaciones |
|---|---|---|---|
| Resumen de consulta PDF | | | |
| Historial longitudinal | | | |
| Ficha de consulta anterior | | | |
| Impresión para paciente | | | |
| Impresión para otro médico | | | |

**APROBADO POR EL CARDIÓLOGO:** pendiente.

## L. Obligatoriedad y ciclo de vida

Para cada campo que se apruebe posteriormente se debe completar esta ficha antes de 6C2B:

| Campo aprobado | Requerido / opcional / condicional | Editable / solo lectura / derivado | Longitudinal / episodio | Condición y notas | Aprobado |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

No se implementará un campo cuya obligatoriedad, pertenencia y ciclo de vida no estén definidos.

## M. Orden final aprobado

La siguiente secuencia es únicamente un ejemplo de arquitectura.

**NO APROBADO — EJEMPLO DE ARQUITECTURA**

| Módulo | Orden | Obligatorio | Notas | Aprobado |
|---|---:|---|---|---|
| `core.anamnesis` | | | | No |
| `core.vital-signs` | | | | No |
| `cardiology.assessment` | | | | No |
| `cardiology.ecg` | | | | No |
| `core.diagnoses` | | | | No |
| `core.prescriptions` | | | | No |
| `core.clinical-orders` | | | | No |

Orden definitivo acordado:

| Módulo | Orden | Obligatorio | Notas | Aprobado |
|---|---:|---|---|---|
| | | | | |
| | | | | |
| | | | | |

## Propuesta técnica para discutir después de la validación

Una opción futura es un `CardiologyAssessment` uno-a-uno con `ClinicalHistory`, porque la evaluación podría representar un registro especializado por episodio. Un `Electrocardiogram` podría ser uno-a-muchos con `ClinicalHistory` si el flujo confirma que puede haber varios ECG en una consulta.

Esto todavía no es una decisión de implementación. Holter, MAPA, ecocardiograma y prueba de esfuerzo necesitan un diseño que distinga informe, metadatos y archivos, y que no acople Atlas a un equipo antes de conocer marca, software y formatos reales.

## Cierre de la validación

Campos o módulos aprobados expresamente: _________________________________________

Campos rechazados o pospuestos: __________________________________________________

Decisiones que requieren otra sesión: ____________________________________________

Firma o confirmación del cardiólogo: ____________________  Fecha: _________________
