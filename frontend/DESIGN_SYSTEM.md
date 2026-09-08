# Atlas Design System - Phase 1

Infraestructura de componentes UI para **Consultorio Médico** construida con Tailwind CSS 4 y variables CSS nativas.

## 📋 Contenidos

- [Tokens de Diseño](#tokens-de-diseño)
- [Componentes Base](#componentes-base)
- [Instalación](#instalación)
- [Uso](#uso)
- [Colores](#colores)

## 🎨 Tokens de Diseño

### Ubicación
`frontend/src/styles/design-tokens.css`

Todos los tokens están definidos como **CSS custom properties** centralizadas:

```css
:root {
  --atlas-primary: #0066cc;
  --atlas-secondary: #6b7280;
  --atlas-success: #10b981;
  --atlas-warning: #f59e0b;
  --atlas-danger: #ef4444;
  --atlas-info: #3b82f6;
  /* ... más tokens */
}
```

### Categorías de Tokens

#### Colores Semánticos
- `--atlas-primary` - Acción principal
- `--atlas-secondary` - Acción secundaria
- `--atlas-success` - Estados exitosos
- `--atlas-warning` - Estados de alerta
- `--atlas-danger` - Estados críticos
- `--atlas-info` - Información general

#### Colores de Superficie
- `--atlas-background` - Fondo principal
- `--atlas-surface` - Superficies elevadas (Cards)
- `--atlas-surface-secondary` - Superficies secundarias
- `--atlas-border` - Bordes

#### Tipografía
- `--font-family-base` - Fuente principal (Inter)
- `--font-size-xs` - 12px
- `--font-size-sm` - 14px
- `--font-size-base` - 16px
- `--font-size-lg` - 18px

#### Espaciado
- `--spacing-xs` - 4px
- `--spacing-sm` - 8px
- `--spacing-md` - 16px
- `--spacing-lg` - 24px
- `--spacing-xl` - 32px

#### Bordes
- `--radius-sm` - 4px
- `--radius-md` - 8px
- `--radius-lg` - 12px

#### Sombras
- `--atlas-shadow-sm` - Sombra pequeña
- `--atlas-shadow-md` - Sombra media
- `--atlas-shadow-lg` - Sombra grande

#### Transiciones
- `--transition-fast` - 100ms
- `--transition-normal` - 200ms
- `--transition-slow` - 300ms

#### Z-Index
- `--z-dropdown` - 1000
- `--z-modal` - 1050
- `--z-tooltip` - 1100

## 🧩 Componentes Base

### Button
Botón reutilizable con variantes y tamaños.

**Props:**
- `variant` - `"primary" | "secondary" | "ghost" | "danger"` (default: `"primary"`)
- `size` - `"sm" | "md" | "lg"` (default: `"md"`)
- `isLoading` - `boolean` (default: `false`)
- `disabled` - `boolean` (default: `false`)

**Ejemplo:**
```tsx
import { Button } from "@/components/ui";

<Button variant="primary" size="md">
  Click me
</Button>

<Button variant="danger" isLoading>
  Eliminando...
</Button>
```

### Card
Contenedor elevado con bordes y sombra.

**Props:**
- Acepta props HTML estándar (`className`, etc.)

**Ejemplo:**
```tsx
import { Card } from "@/components/ui";

<Card>
  <h2>Título</h2>
  <p>Contenido...</p>
</Card>
```

### Badge
Etiqueta de estado compacta.

**Props:**
- `status` - `"success" | "warning" | "danger" | "info" | "default"` (default: `"default"`)

**Ejemplo:**
```tsx
import { Badge } from "@/components/ui";

<Badge status="success">Activo</Badge>
<Badge status="danger">Crítico</Badge>
```

### Alert
Mensaje de alerta con tipo y cierre.

**Props:**
- `type` - `"success" | "warning" | "danger" | "info"` (default: `"info"`)
- `title` - `string` (opcional)
- `onClose` - `() => void` (opcional)

**Ejemplo:**
```tsx
import { Alert } from "@/components/ui";

<Alert type="success" title="Éxito">
  La operación se completó correctamente.
</Alert>
```

### FormField
Contenedor para campos de formulario con validación.

**Props:**
- `label` - `string` (opcional)
- `error` - `string` (opcional, muestra error)
- `helperText` - `string` (opcional)
- `required` - `boolean` (default: `false`)

**Ejemplo:**
```tsx
import { FormField, TextInput } from "@/components/ui";

<FormField label="Email" required error="Email es requerido">
  <TextInput type="email" placeholder="ejemplo@mail.com" />
</FormField>
```

### TextInput
Campo de entrada de texto con validación.

**Props:**
- `error` - `boolean` (default: `false`)
- Acepta props HTML estándar (`type`, `placeholder`, etc.)

**Ejemplo:**
```tsx
<TextInput 
  type="email" 
  placeholder="tu@email.com" 
  error={hasError}
/>
```

### TextArea
Área de texto con validación.

**Props:**
- `error` - `boolean` (default: `false`)
- Acepta props HTML estándar (`rows`, `placeholder`, etc.)

**Ejemplo:**
```tsx
<TextArea 
  placeholder="Escribe aquí..." 
  rows={4}
/>
```

### Select
Selector desplegable con opciones.

**Props:**
- `options` - `Array<{ value: string; label: string }>`
- `error` - `boolean` (default: `false`)

**Ejemplo:**
```tsx
<Select
  options={[
    { value: "opt1", label: "Opción 1" },
    { value: "opt2", label: "Opción 2" },
  ]}
/>
```

### Checkbox
Casilla de verificación.

**Props:**
- `label` - `string` (opcional)
- Acepta props HTML estándar

**Ejemplo:**
```tsx
<Checkbox label="Aceptar términos" />
```

## 📦 Instalación

Los componentes ya están instalados en:
```
frontend/src/components/ui/
```

## 🚀 Uso

### Importar componentes individuales
```tsx
import { Button, Card, Badge } from "@/components/ui";
```

### Importar desde componentes
```tsx
import { DesignSystemShowcase } from "@/components/DesignSystemShowcase";
```

## 🎨 Paleta de Colores

| Token | Color | Uso |
|-------|-------|-----|
| `--atlas-primary` | #0066cc | Acciones principales |
| `--atlas-secondary` | #6b7280 | Acciones secundarias |
| `--atlas-success` | #10b981 | Estados exitosos |
| `--atlas-warning` | #f59e0b | Alertas |
| `--atlas-danger` | #ef4444 | Errores críticos |
| `--atlas-info` | #3b82f6 | Información |
| `--atlas-mint` | #a7f3d0 | Hover ghost buttons |
| `--atlas-background` | #ffffff | Fondo principal |
| `--atlas-surface` | #f9fafb | Superficies |

## 🔧 Estructura de Archivos

```
frontend/src/
├── styles/
│   └── design-tokens.css      # Variables CSS centralizadas
├── components/
│   ├── ui/
│   │   ├── Button.tsx          # Componente Button
│   │   ├── Card.tsx            # Componente Card
│   │   ├── Badge.tsx           # Componente Badge
│   │   ├── Alert.tsx           # Componente Alert
│   │   ├── FormField.tsx       # Suite de formularios
│   │   └── index.ts            # Barrel export
│   ├── DesignSystemShowcase.tsx # Showcase de todos los componentes
│   └── ...
├── index.css                   # CSS global con importaciones
└── ...
```

## 📝 Notas

- **CSS-First**: Tailwind 4 con `@tailwindcss/vite`, sin `tailwind.config.ts`
- **Variables CSS**: Todos los tokens usan `var(--atlas-*)` para fácil customización
- **TypeScript**: Componentes totalmente tipados
- **Accesibilidad**: Soporte focus-visible y roles ARIA
- **Responsive**: Compilados para funcionar en todas las resoluciones

## 🚀 Next Phase (Fase 2)

- Componentes complejos (Modal, Dropdown, Tabs, etc.)
- Sistema de temas
- Storybook integration
- Test coverage

---

**Rama**: `frontend/design-system-phase-1`
**Estado**: ✅ Completo
