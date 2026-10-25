# Visión de personalización de interfaz — Atlas Pérgamo

## Decisión de producto

**ATLAS PÉRGAMO DEBE PERMITIR QUE LOS ADMINISTRADORES/USUARIOS AUTORIZADOS PERSONALICEN LA DISTRIBUCIÓN DE LOS MÓDULOS Y SUS BLOQUES VISUALES SIN MODIFICAR CÓDIGO.**

La personalización será una capa declarativa de presentación. No es una forma de cambiar permisos, reglas de negocio, seguridad, procesos clínicos ni el significado de los estados.

## Alcance futuro

El framework podrá aplicarse progresivamente a Dashboard, Agenda, Finanzas, Pacientes, Reportes, Gestión de impresión, módulos clínicos y módulos futuros Atlas. Los módulos podrán exponer bloques identificables con IDs estables —por ejemplo, `agenda.contacts`, `agenda.arrivals`, `agenda.calendar`, `agenda.filters` y `agenda.schedule`— para que una preferencia de layout autorizada se aplique sin acoplarse al texto visible ni a selectores CSS frágiles.

Según el módulo y los límites aprobados, se podrá permitir:

- reordenar bloques, con controles accesibles de subir/bajar;
- elegir un orden de cuadrícula mediante presets y spans permitidos;
- colapsar/expandir paneles cuya función admita ocultación temporal;
- elegir entre layouts aprobados;
- guardar preferencias y restaurar la configuración predeterminada.

## Dos niveles de configuración

### Personalización del usuario

Cada usuario podrá organizar su propio espacio. Las preferencias personales solo se aplican a módulos y bloques que siguen autorizados en la sesión actual. Una preferencia nunca concede acceso. Cuando se revoca un permiso, el contenido correspondiente desaparece aunque su ID siga en la preferencia. Los módulos nuevos y permitidos se incorporan de forma segura al orden canónico si una preferencia anterior no los contiene.

### Configuración administrativa

En una fase posterior, administradores autorizados podrán definir layouts predeterminados, orden recomendado, bloques habilitados y, si se aprueba expresamente, valores predeterminados por rol o centro. Esta configuración establece defaults, no sustituye ni amplía los permisos.

## Límites de seguridad y funcionamiento

No se permitirá mover controles críticos a ubicaciones inseguras, ocultar alertas obligatorias, debilitar permisos, alterar flujos clínicos/financieros ni producir layouts inutilizables en tamaños reducidos. El layout debe seguir adaptándose a desktop, tablet y móvil.

No se guardarán coordenadas absolutas como `x=500, y=300`. Se persistirán descriptores lógicos validados: orden, grupos, spans permitidos, estado colapsado y preset de layout. El motor responsive resolverá la geometría final según el viewport.

## Estado de implementación

Esta visión no crea ni habilita persistencia. La Agenda actual usa `data-atlas-block-id` estable en sus principales bloques como preparación estructural, sin almacenar preferencias ni cambiar su lógica funcional. Antes de habilitar guardado habrá que aprobar el modelo de preferencias, su alcance por usuario/organización, validación de permisos, API y migración correspondientes. No se define ni se crea una revisión de base de datos en este documento.

En Agenda V2, `agenda.controls`, `agenda.contacts`, `agenda.arrivals`, `agenda.calendar`, `agenda.filters` y `agenda.schedule` permanecen en el orden semántico del documento. Los paneles operativos abiertos ocupan una fila completa y aumentan la altura del área desplazable; nunca se posicionan encima de la agenda. Cuando están cerrados, el calendario conserva su espacio de trabajo compacto. Estos IDs son ganchos de presentación, no permisos ni preferencias persistidas. Una futura personalización tendrá que preservar este orden seguro en móvil y la visibilidad obligatoria de las acciones y alertas críticas.
