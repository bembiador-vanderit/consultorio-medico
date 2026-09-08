import React from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  children: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--atlas-primary)] text-white hover:bg-[var(--atlas-primary-hover)] active:bg-[var(--atlas-primary-active)] disabled:bg-[var(--atlas-disabled)] disabled:text-[var(--atlas-disabled-text)]",
  secondary:
    "bg-white border border-[var(--atlas-border)] text-[var(--atlas-text-primary)] hover:bg-[var(--atlas-surface-secondary)] disabled:bg-[var(--atlas-disabled-bg)] disabled:text-[var(--atlas-disabled-text)]",
  ghost:
    "bg-transparent text-[var(--atlas-primary)] hover:bg-[var(--atlas-mint)] hover:bg-opacity-30 disabled:text-[var(--atlas-disabled-text)]",
  danger:
    "bg-[var(--atlas-danger)] text-white hover:bg-[var(--atlas-danger-dark)] active:bg-[var(--atlas-danger-dark)] disabled:bg-[var(--atlas-disabled)] disabled:text-[var(--atlas-disabled-text)]",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs font-medium",
  md: "px-4 py-2 text-sm font-medium",
  lg: "px-6 py-3 text-base font-medium",
};

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled = false,
  className = "",
  children,
  ...props
}: ButtonProps) {
  const baseClasses =
    "inline-flex items-center justify-center rounded-[var(--radius-md)] transition-colors duration-[var(--transition-normal)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--atlas-focus-ring)] focus-visible:ring-offset-2 disabled:cursor-not-allowed";

  return (
    <button
      disabled={disabled || isLoading}
      className={`${baseClasses} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {isLoading ? (
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
      ) : (
        children
      )}
    </button>
  );
}
