import React from "react";

export type AlertType = "success" | "warning" | "danger" | "info";

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: AlertType;
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
  className?: string;
}

const typeStyles: Record<AlertType, { bg: string; border: string; text: string; icon: string }> = {
  success: {
    bg: "bg-[var(--atlas-success-light)]",
    border: "border-[var(--atlas-success)]",
    text: "text-[var(--atlas-success-dark)]",
    icon: "✓",
  },
  warning: {
    bg: "bg-[var(--atlas-warning-light)]",
    border: "border-[var(--atlas-warning)]",
    text: "text-[var(--atlas-warning-dark)]",
    icon: "⚠",
  },
  danger: {
    bg: "bg-[var(--atlas-danger-light)]",
    border: "border-[var(--atlas-danger)]",
    text: "text-[var(--atlas-danger-dark)]",
    icon: "✕",
  },
  info: {
    bg: "bg-[var(--atlas-info-light)]",
    border: "border-[var(--atlas-info)]",
    text: "text-[var(--atlas-info-dark)]",
    icon: "ℹ",
  },
};

export function Alert({
  type = "info",
  title,
  children,
  onClose,
  className = "",
  ...props
}: AlertProps) {
  const styles = typeStyles[type];
  const baseClasses = `rounded-[var(--radius-md)] border p-4 ${styles.bg} ${styles.border} ${styles.text}`;

  return (
    <div className={`${baseClasses} ${className}`} role="alert" {...props}>
      <div className="flex items-start gap-3">
        <span className="flex-shrink-0 text-lg font-bold">{styles.icon}</span>
        <div className="flex-1">
          {title && <h3 className="font-semibold mb-1">{title}</h3>}
          <div className="text-sm">{children}</div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="flex-shrink-0 text-lg font-bold hover:opacity-70 transition-opacity"
            aria-label="Cerrar alerta"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
