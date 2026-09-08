import React from "react";

export type BadgeStatus = "success" | "warning" | "danger" | "info" | "default";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  status?: BadgeStatus;
  children: React.ReactNode;
  className?: string;
}

const statusStyles: Record<BadgeStatus, string> = {
  success:
    "bg-[var(--atlas-success-light)] text-[var(--atlas-success-dark)] border border-[var(--atlas-success)]",
  warning:
    "bg-[var(--atlas-warning-light)] text-[var(--atlas-warning-dark)] border border-[var(--atlas-warning)]",
  danger:
    "bg-[var(--atlas-danger-light)] text-[var(--atlas-danger-dark)] border border-[var(--atlas-danger)]",
  info: "bg-[var(--atlas-info-light)] text-[var(--atlas-info-dark)] border border-[var(--atlas-info)]",
  default:
    "bg-[var(--atlas-surface-secondary)] text-[var(--atlas-text-secondary)] border border-[var(--atlas-border)]",
};

export function Badge({
  status = "default",
  children,
  className = "",
  ...props
}: BadgeProps) {
  const baseClasses =
    "inline-flex items-center px-3 py-1 rounded-[var(--radius-md)] text-xs font-semibold whitespace-nowrap";

  return (
    <span className={`${baseClasses} ${statusStyles[status]} ${className}`} {...props}>
      {children}
    </span>
  );
}
